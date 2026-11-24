"""1:1 톡 API — 입주민 ↔ 관리자 대화."""

import logging
import math

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import RATE_LIMIT_CHAT_TALK_SEND
from app.database import get_db
from app.dependencies import require_admin_with_scope
from app.models.admin_user import AdminUser
from app.models.chat_thread import ChatMessage, ChatThread
from app.models.market import ApartmentResident
from app.rate_limit import limiter
from app.routers.market import _get_market_user, _get_market_user_optional
from app.utils import now_kst
from app.schemas.chat_talk import (
    AvailabilityResponse,
    ChatMessageCreate,
    ChatMessageOut,
    ChatThreadListItem,
    ChatThreadListResponse,
    ChatThreadOut,
    ResidentThreadListItem,
    ThreadStatusUpdate,
)
from app.services.business_hours import get_availability, is_business_hours
from app.services.alert_service import trigger_chat_talk_admin_alert, trigger_chat_talk_reply_alert

logger = logging.getLogger("acchelper")
router = APIRouter(prefix="/api/chat-talk", tags=["chat-talk"])

PAGE_SIZE = 20


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_or_create_open_thread(db: Session, company_id: int, dong: str, ho: str, resident_name: str) -> ChatThread:
    thread = (
        db.query(ChatThread)
        .filter(
            ChatThread.company_id == company_id,
            ChatThread.dong == dong,
            ChatThread.ho == ho,
            ChatThread.status == "open",
        )
        .order_by(ChatThread.created_at.desc())
        .first()
    )
    if thread:
        return thread

    resident_phone = None
    resident = (
        db.query(ApartmentResident)
        .filter(
            ApartmentResident.building == dong,
            ApartmentResident.unit_number == ho,
        )
        .first()
    )
    if resident:
        resident_phone = resident.resident_phone

    thread = ChatThread(
        company_id=company_id,
        dong=dong,
        ho=ho,
        resident_name=resident_name,
        resident_phone=resident_phone,
        status="open",
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread


async def _save_chat_image(file: UploadFile) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일이 없습니다.")
    file_bytes = await file.read()
    try:
        from app.services.image_upload import save_image
        filename = save_image(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 프론트(Vercel)가 /uploads/*를 백엔드로 프록시하므로 상대경로로 반환
    return {"url": f"/uploads/{filename}"}


def _message_preview(msg: ChatMessage | None) -> str:
    if not msg:
        return ""
    content = msg.content or ""
    if not content.strip() and msg.image_url:
        return "📷 사진"
    return content[:60] + "…" if len(content) > 60 else content


def _admin_name_map(db: Session, admin_ids: set[int]) -> dict[int, str]:
    if not admin_ids:
        return {}
    admins = db.query(AdminUser).filter(AdminUser.user_id.in_(admin_ids)).all()
    return {a.user_id: (a.full_name or a.email) for a in admins}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/availability", response_model=AvailabilityResponse)
def availability(request: Request, company_id: int | None = None, db: Session = Depends(get_db)):
    """1:1 톡 / 관리실 문자 링크가 공유하는 가용성(영업시간) 조회 — 인증 불필요.

    로그인 상태면 세션(market_token)의 company_id를 신뢰하고, 아직 로그인 전이면
    (예: 랜딩페이지의 샘플회사 데모 안내) 쿼리파라미터 company_id를 사용한다.
    """
    user = _get_market_user_optional(request)
    resolved_company_id = (user or {}).get("company_id") or company_id
    return get_availability(db, company_id=resolved_company_id)


def _resident_identity(request: Request) -> tuple[int, str, str, str]:
    """입주민 토큰에서 (company_id, 동, 호, 이름) 추출 — 없으면 401."""
    user = _get_market_user(request)
    company_id = user.get("company_id")
    dong = user.get("building")
    ho = user.get("unit")
    if not company_id or not dong or not ho:
        raise HTTPException(status_code=401, detail="입주민 인증이 필요합니다.")
    return company_id, dong, ho, (user.get("name") or "")


def _resident_thread_out(db: Session, thread: ChatThread) -> ChatThreadOut:
    """입주민용 스레드 상세 — 관리자가 보낸 미확인 메시지를 읽음 처리한 뒤 반환."""
    # 카카오톡처럼 입주민이 대화창을 열면 관리자 메시지의 "1"이 사라짐
    db.execute(
        text(
            "UPDATE chat_messages SET read_at = :now "
            "WHERE thread_id = :tid AND sender_type = 'admin' AND read_at IS NULL"
        ),
        {"now": now_kst(), "tid": thread.id},
    )
    db.commit()

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id == thread.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    name_map = _admin_name_map(db, {thread.claimed_admin_id} if thread.claimed_admin_id else set())

    return ChatThreadOut(
        id=thread.id,
        status=thread.status,
        dong=thread.dong,
        ho=thread.ho,
        resident_name=thread.resident_name,
        claimed_admin_id=thread.claimed_admin_id,
        claimed_admin_name=name_map.get(thread.claimed_admin_id) if thread.claimed_admin_id else None,
        created_at=thread.created_at,
        last_message_at=thread.last_message_at,
        messages=[ChatMessageOut.model_validate(m) for m in messages],
    )


@router.get("/thread", response_model=ChatThreadOut)
def get_my_thread(request: Request, db: Session = Depends(get_db)):
    """입주민 본인의 가장 최근 스레드 조회 (읽기는 영업시간 무관 항상 허용)."""
    company_id, dong, ho, _name = _resident_identity(request)

    thread = (
        db.query(ChatThread)
        .filter(
            ChatThread.company_id == company_id,
            ChatThread.dong == dong,
            ChatThread.ho == ho,
        )
        .order_by(ChatThread.created_at.desc())
        .first()
    )
    if not thread:
        raise HTTPException(status_code=404, detail="아직 시작된 대화가 없습니다.")
    return _resident_thread_out(db, thread)


@router.get("/threads", response_model=list[ResidentThreadListItem])
def list_my_threads(request: Request, db: Session = Depends(get_db)):
    """'톡 대화 확인' — 인증한 입주민(회사·동·호·이름 일치)의 대화 목록, 최신순.
    이름+전화번호는 로그인(/api/market/login) 시 입주민 명부와 대조해 이미 검증됨."""
    company_id, dong, ho, name = _resident_identity(request)

    threads = (
        db.query(ChatThread)
        .filter(
            ChatThread.company_id == company_id,
            ChatThread.dong == dong,
            ChatThread.ho == ho,
            ChatThread.resident_name == name,
        )
        .order_by(ChatThread.last_message_at.desc())
        .all()
    )
    items = []
    for t in threads:
        last_msg = (
            db.query(ChatMessage)
            .filter(ChatMessage.thread_id == t.id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        unread = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.thread_id == t.id,
                ChatMessage.sender_type == "admin",
                ChatMessage.read_at.is_(None),
            )
            .count()
        )
        items.append(ResidentThreadListItem(
            id=t.id,
            status=t.status,
            created_at=t.created_at,
            last_message_at=t.last_message_at,
            last_message_preview=_message_preview(last_msg),
            unread_count=unread,
        ))
    return items


@router.get("/threads/{thread_id}", response_model=ChatThreadOut)
def get_my_thread_by_id(thread_id: int, request: Request, db: Session = Depends(get_db)):
    """'톡 대화 확인' 상세 — 본인(회사·동·호·이름 일치) 대화만 열람 가능."""
    company_id, dong, ho, name = _resident_identity(request)

    thread = (
        db.query(ChatThread)
        .filter(
            ChatThread.id == thread_id,
            ChatThread.company_id == company_id,
            ChatThread.dong == dong,
            ChatThread.ho == ho,
            ChatThread.resident_name == name,
        )
        .first()
    )
    if not thread:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    return _resident_thread_out(db, thread)


@router.post("/thread/images", status_code=201)
@limiter.limit(RATE_LIMIT_CHAT_TALK_SEND)
async def upload_resident_image(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """입주민 사진 업로드 — 영업시간 내에만 허용. 반환된 url을 메시지 전송 시 image_url로 사용."""
    user = _get_market_user(request)
    company_id = user.get("company_id")
    if not company_id or not user.get("building") or not user.get("unit"):
        raise HTTPException(status_code=401, detail="입주민 인증이 필요합니다.")

    available, _reason = is_business_hours(db, company_id=company_id)
    if not available:
        from app.services.business_hours import UNAVAILABLE_MESSAGE
        raise HTTPException(status_code=403, detail=UNAVAILABLE_MESSAGE)

    return await _save_chat_image(file)


@router.post("/thread/messages", status_code=201)
@limiter.limit(RATE_LIMIT_CHAT_TALK_SEND)
def send_resident_message(
    body: ChatMessageCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """입주민이 메시지 전송 — 영업시간 내에만 허용."""
    user = _get_market_user(request)
    company_id = user.get("company_id")
    dong = user.get("building")
    ho = user.get("unit")
    name = user.get("name")
    if not company_id or not dong or not ho:
        raise HTTPException(status_code=401, detail="입주민 인증이 필요합니다.")

    available, _reason = is_business_hours(db, company_id=company_id)
    if not available:
        from app.services.business_hours import UNAVAILABLE_MESSAGE
        raise HTTPException(status_code=403, detail=UNAVAILABLE_MESSAGE)

    thread = _get_or_create_open_thread(db, company_id, dong, ho, name or "입주민")

    is_first_message = (
        db.query(ChatMessage).filter(ChatMessage.thread_id == thread.id).count() == 0
    )

    msg = ChatMessage(
        thread_id=thread.id,
        sender_type="resident",
        content=body.content.strip(),
        image_url=body.image_url,
    )
    db.add(msg)
    thread.last_message_at = now_kst()
    db.commit()
    db.refresh(msg)

    if is_first_message:
        background_tasks.add_task(trigger_chat_talk_admin_alert, thread.id)

    return {"ok": True, "thread_id": thread.id, "message_id": msg.id}


@router.get("/admin/threads", response_model=ChatThreadListResponse)
def list_admin_threads(
    page: int = 1,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin_with_scope),
):
    company_id = admin["company_id"]
    base_q = db.query(ChatThread).filter(ChatThread.company_id == company_id)
    total = base_q.count()

    # 미배정(claimed_admin_id IS NULL) 우선, 그 다음 최근 메시지순
    items = (
        base_q.order_by(
            ChatThread.claimed_admin_id.is_(None).desc(),
            ChatThread.last_message_at.desc(),
        )
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )

    admin_ids = {t.claimed_admin_id for t in items if t.claimed_admin_id}
    name_map = _admin_name_map(db, admin_ids)

    result_items = []
    for t in items:
        unread_count = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.thread_id == t.id,
                ChatMessage.sender_type == "resident",
                ChatMessage.read_at.is_(None),
            )
            .count()
        )
        last_msg = (
            db.query(ChatMessage)
            .filter(ChatMessage.thread_id == t.id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        preview = _message_preview(last_msg)
        result_items.append(ChatThreadListItem(
            id=t.id,
            dong=t.dong,
            ho=t.ho,
            resident_name=t.resident_name,
            status=t.status,
            claimed_admin_id=t.claimed_admin_id,
            claimed_admin_name=name_map.get(t.claimed_admin_id) if t.claimed_admin_id else None,
            unread_count=unread_count,
            last_message_at=t.last_message_at,
            last_message_preview=preview,
        ))

    return ChatThreadListResponse(
        items=result_items,
        page=page,
        pages=math.ceil(total / PAGE_SIZE) if total else 1,
        total=total,
    )


@router.get("/admin/threads/{thread_id}", response_model=ChatThreadOut)
def get_admin_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin_with_scope),
):
    thread = db.query(ChatThread).filter(
        ChatThread.id == thread_id,
        ChatThread.company_id == admin["company_id"],
    ).first()
    if not thread:
        raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")

    # 먼저 여는 관리자가 자동 배정 (race-safe: claimed_admin_id IS NULL 조건부 UPDATE)
    db.execute(
        text(
            "UPDATE chat_threads SET claimed_admin_id = :aid, claimed_at = :now "
            "WHERE id = :tid AND claimed_admin_id IS NULL"
        ),
        {"aid": admin["user_id"], "now": now_kst(), "tid": thread_id},
    )
    # 입주민이 보낸 미확인 메시지 읽음 처리
    db.execute(
        text(
            "UPDATE chat_messages SET read_at = :now "
            "WHERE thread_id = :tid AND sender_type = 'resident' AND read_at IS NULL"
        ),
        {"now": now_kst(), "tid": thread_id},
    )
    db.commit()
    db.refresh(thread)

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id == thread.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    name_map = _admin_name_map(db, {thread.claimed_admin_id} if thread.claimed_admin_id else set())

    return ChatThreadOut(
        id=thread.id,
        status=thread.status,
        dong=thread.dong,
        ho=thread.ho,
        resident_name=thread.resident_name,
        claimed_admin_id=thread.claimed_admin_id,
        claimed_admin_name=name_map.get(thread.claimed_admin_id) if thread.claimed_admin_id else None,
        created_at=thread.created_at,
        last_message_at=thread.last_message_at,
        messages=[ChatMessageOut.model_validate(m) for m in messages],
    )


@router.post("/admin/threads/{thread_id}/images", status_code=201)
async def upload_admin_image(
    thread_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin_with_scope),
):
    """관리자 사진 업로드 — 반환된 url을 답장 전송 시 image_url로 사용."""
    thread = db.query(ChatThread).filter(
        ChatThread.id == thread_id,
        ChatThread.company_id == admin["company_id"],
    ).first()
    if not thread:
        raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")
    return await _save_chat_image(file)


@router.post("/admin/threads/{thread_id}/messages", status_code=201)
def send_admin_message(
    thread_id: int,
    body: ChatMessageCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin_with_scope),
):
    """관리자 답장 — 영업시간 제한 없음(언제든 답장 가능)."""
    thread = db.query(ChatThread).filter(
        ChatThread.id == thread_id,
        ChatThread.company_id == admin["company_id"],
    ).first()
    if not thread:
        raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")

    if thread.claimed_admin_id is None:
        thread.claimed_admin_id = admin["user_id"]
        thread.claimed_at = now_kst()

    is_first_admin_reply = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id == thread.id, ChatMessage.sender_type == "admin")
        .count()
        == 0
    )

    msg = ChatMessage(
        thread_id=thread.id,
        sender_type="admin",
        sender_admin_id=admin["user_id"],
        content=body.content.strip(),
        image_url=body.image_url,
    )
    db.add(msg)
    thread.last_message_at = now_kst()
    db.commit()
    db.refresh(msg)

    if is_first_admin_reply:
        background_tasks.add_task(trigger_chat_talk_reply_alert, thread.id)

    return {"ok": True, "message_id": msg.id}


@router.patch("/admin/threads/{thread_id}/status")
def update_thread_status(
    thread_id: int,
    body: ThreadStatusUpdate,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin_with_scope),
):
    thread = db.query(ChatThread).filter(
        ChatThread.id == thread_id,
        ChatThread.company_id == admin["company_id"],
    ).first()
    if not thread:
        raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")

    thread.status = body.status
    db.commit()
    return {"ok": True}
