"""민원게시판 API."""

import math
import logging
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import SECRET_KEY
from app.database import get_db
from app.dependencies import require_admin, optional_admin
from app.models.complaint import Complaint
from app.models.complaint_person import ComplaintPerson
from app.services.alert_service import trigger_complaint_alert

MARKET_JWT_SECRET = SECRET_KEY + "_market"

logger = logging.getLogger("acchelper")
router = APIRouter(prefix="/api/complaints", tags=["complaints"])

PAGE_SIZE = 20


# ── Schemas ───────────────────────────────────────────────────────────────────

class ComplaintCreate(BaseModel):
    company_id: int
    dong: str = Field(..., max_length=20)
    ho: str = Field(..., max_length=20)
    name: str = Field(..., max_length=100)
    phone: str = Field(default="", max_length=30)
    title: str = Field(..., max_length=255)
    content: str = Field(..., max_length=3000)
    image1_url: Optional[str] = Field(default=None, max_length=500)
    image2_url: Optional[str] = Field(default=None, max_length=500)


class ReplyCreate(BaseModel):
    content: str = Field(..., max_length=3000)


class ComplaintUpdate(BaseModel):
    name: str = Field(..., max_length=100)
    title: str = Field(..., max_length=255)
    content: str = Field(..., max_length=3000)


class DeleteRequest(BaseModel):
    reason: str = Field(default="민원글이 아니어서 삭제 되었습니다!", max_length=500)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _time_ago(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    diff = (now - aware).total_seconds()
    if diff < 60:
        return "방금 전"
    if diff < 3600:
        return f"{int(diff / 60)}분 전"
    if diff < 86400:
        return f"{int(diff / 3600)}시간 전"
    return f"{int(diff / 86400)}일 전"


def _writer_display(dong: str, ho: str) -> str:
    return f"{dong} {ho}"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/upload-image")
async def upload_complaint_image(
    request: Request,
    file: UploadFile = File(...),
):
    """민원 이미지 업로드 — 인증 불필요, 5MB 이하, jpg/png/gif/webp"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일이 없습니다.")
    file_bytes = await file.read()
    try:
        from app.services.image_upload import save_image
        filename = save_image(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    base_url = str(request.base_url).rstrip("/")
    return {"url": f"{base_url}/uploads/{filename}"}


@router.get("/debug/{complaint_id}")
def debug_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """임시 디버그: DB 실제 저장 값 확인"""
    c = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="없음")
    persons = db.query(ComplaintPerson).filter(
        ComplaintPerson.company_id == c.company_id
    ).all()
    return {
        "complaint": {
            "id": c.id,
            "company_id": c.company_id,
            "dong": repr(c.dong),
            "ho": repr(c.ho),
            "writer_name": repr(c.writer_name),
            "writer_phone": repr(c.writer_phone),
        },
        "complaint_persons": [
            {"dong": repr(p.dong), "ho": repr(p.ho), "name": repr(p.name), "phone": repr(p.phone)}
            for p in persons
        ],
    }


@router.get("/persons")
def list_complaint_persons(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", description="동/호수·이름·전화번호 검색"),
    sort: str = Query("last_complained_at", description="정렬 기준 컬럼"),
    order: str = Query("desc", description="asc / desc"),
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """민원인 목록 조회 (관리자 전용)."""
    company_id = admin["company_id"]

    q = db.query(ComplaintPerson).filter(ComplaintPerson.company_id == company_id)

    if search:
        like = f"%{search}%"
        from sqlalchemy import or_
        q = q.filter(or_(
            ComplaintPerson.dong.ilike(like),
            ComplaintPerson.ho.ilike(like),
            ComplaintPerson.name.ilike(like),
            ComplaintPerson.phone.ilike(like),
        ))

    # 정렬
    sort_col = {
        "last_complained_at": ComplaintPerson.last_complained_at,
        "first_complained_at": ComplaintPerson.first_complained_at,
        "complaint_count": ComplaintPerson.complaint_count,
        "dong": ComplaintPerson.dong,
    }.get(sort, ComplaintPerson.last_complained_at)
    if order == "asc":
        q = q.order_by(sort_col.asc())
    else:
        q = q.order_by(sort_col.desc())

    total = q.count()
    items = q.offset((page - 1) * size).limit(size).all()

    def _fmt(dt):
        if not dt:
            return ""
        aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        return aware.strftime("%Y-%m-%d %H:%M")

    return {
        "total": total,
        "pages": math.ceil(total / size) if total else 1,
        "page": page,
        "items": [
            {
                "id": p.id,
                "dong": p.dong,
                "ho": p.ho,
                "name": p.name,
                "phone": p.phone or "-",
                "complaint_count": p.complaint_count or 1,
                "first_complained_at": _fmt(p.first_complained_at),
                "last_complained_at": _fmt(p.last_complained_at),
            }
            for p in items
        ],
    }


@router.get("")
def list_complaints(
    company_id: int = Query(...),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    base_q = db.query(Complaint).filter(Complaint.company_id == company_id)
    total = base_q.count()
    items = (
        base_q.order_by(Complaint.created_at.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )

    return {
        "total": total,
        "pages": math.ceil(total / PAGE_SIZE) if total else 1,
        "page": page,
        "items": [
            {
                "id": c.id,
                "writer": _writer_display(c.dong, c.ho),
                "title": c.title if not c.is_deleted else "(삭제된 글)",
                "preview": (c.content[:60] + "…" if len(c.content) > 60 else c.content) if not c.is_deleted else "",
                "time_ago": _time_ago(c.created_at),
                "has_reply": bool(c.reply_content),
                "is_deleted": c.is_deleted,
                "delete_reason": c.delete_reason if c.is_deleted else None,
            }
            for c in items
        ],
    }


@router.post("", status_code=201)
def create_complaint(
    body: ComplaintCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    c = Complaint(
        company_id=body.company_id,
        dong=body.dong.strip(),
        ho=body.ho.strip(),
        writer_name=body.name.strip(),
        writer_phone=body.phone.strip() if body.phone else None,
        privacy_agreed_at=datetime.now(timezone.utc),  # 개인정보 동의 시각 서버 기록
        title=body.title.strip(),
        content=body.content.strip(),
        image1_url=body.image1_url or None,
        image2_url=body.image2_url or None,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    logger.info("Complaint created: id=%d company_id=%d", c.id, c.company_id)

    # ── 민원인 테이블 자동 등록 (동일인 있으면 카운트·최근일만 갱신) ─────────
    _upsert_complaint_person(db, body)

    background_tasks.add_task(trigger_complaint_alert, c.id)
    return {"complaint_id": c.id}


def _upsert_complaint_person(db: Session, body: ComplaintCreate):
    """민원인 테이블에 등록. 동일인(company+dong+ho+name+phone)이 있으면 갱신, 없으면 신규 등록."""
    dong = body.dong.strip()
    ho = body.ho.strip()
    name = body.name.strip()
    phone = body.phone.strip() if body.phone else None

    person = db.query(ComplaintPerson).filter(
        ComplaintPerson.company_id == body.company_id,
        ComplaintPerson.dong == dong,
        ComplaintPerson.ho == ho,
        ComplaintPerson.name == name,
        ComplaintPerson.phone == phone,
    ).first()

    now = datetime.now(timezone.utc)
    if person:
        # 동일인 — 최근 민원일·건수만 갱신
        person.last_complained_at = now
        person.complaint_count = (person.complaint_count or 0) + 1
        logger.info("ComplaintPerson updated: id=%d count=%d", person.id, person.complaint_count)
    else:
        # 신규 민원인 등록
        person = ComplaintPerson(
            company_id=body.company_id,
            dong=dong,
            ho=ho,
            name=name,
            phone=phone,
            first_complained_at=now,
            last_complained_at=now,
            complaint_count=1,
        )
        db.add(person)
        logger.info("ComplaintPerson registered: company_id=%d dong=%s ho=%s", body.company_id, dong, ho)

    db.commit()


def _require_resident_or_admin(
    request: Request,
    admin: dict | None = Depends(optional_admin),
) -> dict | None:
    """관리자 또는 입주민(market JWT) 둘 중 하나만 있으면 허용."""
    if admin is not None:
        return admin
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not token:
        token = request.cookies.get("market_token", "")
    if token:
        try:
            payload = jwt.decode(token, MARKET_JWT_SECRET, algorithms=["HS256"])
            if payload.get("verified"):
                return None  # 입주민 — admin 아님
        except jwt.PyJWTError:
            pass
    raise HTTPException(status_code=401, detail="입주민 인증이 필요합니다.")


@router.get("/{complaint_id}")
def get_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    admin: dict | None = Depends(_require_resident_or_admin),
):
    c = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="민원글을 찾을 수 없습니다.")

    is_admin = admin is not None and admin.get("company_id") == c.company_id

    # complaints.writer_phone 이 NULL인 경우 complaint_persons 에서 fallback 조회
    writer_phone = c.writer_phone
    if is_admin and not writer_phone:
        person = db.query(ComplaintPerson).filter(
            ComplaintPerson.company_id == c.company_id,
            ComplaintPerson.dong == c.dong,
            ComplaintPerson.ho == c.ho,
            ComplaintPerson.name == c.writer_name,
        ).first()
        if person:
            writer_phone = person.phone

    if c.is_deleted:
        return {
            "id": c.id,
            "is_admin": is_admin,
            "is_deleted": True,
            "delete_reason": c.delete_reason,
            "writer": _writer_display(c.dong, c.ho),
            "writer_name": c.writer_name if is_admin else None,
            "writer_phone": writer_phone if is_admin else None,
            "title": "(삭제된 글)",
            "content": "",
            "time_ago": _time_ago(c.created_at),
            "reply": None,
        }

    return {
        "id": c.id,
        "is_admin": is_admin,
        "is_deleted": False,
        "writer": _writer_display(c.dong, c.ho),
        "writer_name": c.writer_name if is_admin else None,
        "writer_phone": writer_phone if is_admin else None,
        "title": c.title,
        "content": c.content,
        "image1_url": c.image1_url,
        "image2_url": c.image2_url,
        "time_ago": _time_ago(c.created_at),
        "reply": {
            "content": c.reply_content,
            "time_ago": _time_ago(c.replied_at),
        } if c.reply_content else None,
    }


@router.patch("/{complaint_id}")
def update_complaint(
    complaint_id: int,
    body: ComplaintUpdate,
    db: Session = Depends(get_db),
):
    c = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="민원글을 찾을 수 없습니다.")
    if c.is_deleted:
        raise HTTPException(status_code=400, detail="삭제된 글은 수정할 수 없습니다.")
    if c.writer_name != body.name.strip():
        raise HTTPException(status_code=403, detail="이름이 일치하지 않습니다.")

    c.title = body.title.strip()
    c.content = body.content.strip()
    db.commit()
    return {"ok": True}


@router.post("/{complaint_id}/reply")
def reply_complaint(
    complaint_id: int,
    body: ReplyCreate,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    c = db.query(Complaint).filter(
        Complaint.id == complaint_id,
        Complaint.company_id == admin["company_id"],
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="민원글을 찾을 수 없습니다.")
    if c.is_deleted:
        raise HTTPException(status_code=400, detail="삭제된 글에는 답변할 수 없습니다.")

    c.reply_content = body.content.strip()
    c.replied_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.delete("/{complaint_id}/reply")
def delete_reply(
    complaint_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """관리자 답변 삭제."""
    c = db.query(Complaint).filter(
        Complaint.id == complaint_id,
        Complaint.company_id == admin["company_id"],
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="민원글을 찾을 수 없습니다.")
    if not c.reply_content:
        raise HTTPException(status_code=404, detail="삭제할 답변이 없습니다.")

    c.reply_content = None
    c.replied_at = None
    db.commit()
    logger.info("Reply deleted: complaint_id=%d by admin=%d", complaint_id, admin["user_id"])
    return {"ok": True}


@router.delete("/{complaint_id}")
def delete_complaint(
    complaint_id: int,
    body: DeleteRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    c = db.query(Complaint).filter(
        Complaint.id == complaint_id,
        Complaint.company_id == admin["company_id"],
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="민원글을 찾을 수 없습니다.")

    c.is_deleted = True
    c.delete_reason = body.reason.strip()
    c.deleted_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Complaint deleted: id=%d by admin=%d reason=%s", c.id, admin["user_id"], c.delete_reason)
    return {"ok": True}
