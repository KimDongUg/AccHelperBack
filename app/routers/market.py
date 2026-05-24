"""우리아파트 당근 — 입주민 중고거래 커뮤니티 API."""

import math
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy import or_
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import SECRET_KEY, UPLOAD_DIR
from app.database import get_db
from app.dependencies import require_admin
from app.models.market import (
    ApartmentResident, MarketPost, MarketImage, MarketComment, MarketReport
)
from app.services.image_upload import save_image

logger = logging.getLogger("acchelper")
router = APIRouter(prefix="/api/market", tags=["market"])

MARKET_JWT_SECRET = SECRET_KEY + "_market"
MARKET_JWT_EXPIRE_HOURS = 72
ALLOWED_STATUSES = {"판매중", "예약중", "거래완료"}


# ── JWT helpers ───────────────────────────────────────────────────────────────

def _create_market_token(building: str, unit: str, name: str) -> str:
    payload = {
        "building": building,
        "unit": unit,
        "name": name,
        "verified": True,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=MARKET_JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, MARKET_JWT_SECRET, algorithm="HS256")


def _decode_market_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, MARKET_JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def _get_market_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not token:
        token = request.cookies.get("market_token", "")
    payload = _decode_market_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="입주민 인증이 필요합니다.")
    return payload


def _get_market_user_optional(request: Request) -> Optional[dict]:
    """인증 없이도 허용 — 목록 등 공개 엔드포인트용."""
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    if not token:
        token = request.cookies.get("market_token", "")
    return _decode_market_token(token) if token else None


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


# ── 시간 포맷 ─────────────────────────────────────────────────────────────────

def _time_ago(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = datetime.now(timezone.utc) - dt
    s = diff.total_seconds()
    if s < 60:
        return "방금 전"
    if s < 3600:
        return f"{int(s // 60)}분 전"
    if s < 86400:
        return f"{int(s // 3600)}시간 전"
    return f"{int(s // 86400)}일 전"


def _post_to_dict(post: MarketPost, images: list, comment_count: int = 0) -> dict:
    thumbnail = images[0].image_url if images else None
    return {
        "id": post.id,
        "category": post.category,
        "title": post.title,
        "content": post.content,
        "price": post.price,
        "status": post.status,
        "writer_unit": post.writer_unit,
        "time_ago": _time_ago(post.created_at),
        "created_at": post.created_at.isoformat(),
        "thumbnail": thumbnail,
        "images": [img.image_url for img in images],
        "comment_count": comment_count,
    }


# ── 입주민 인증 ───────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    building: str = "1동"
    unit_number: str
    name: str
    phone: str
    company_id: Optional[int] = None


@router.post("/login")
def market_login(req: LoginRequest, db: Session = Depends(get_db)):
    phone_norm = _normalize_phone(req.phone)

    resident = (
        db.query(ApartmentResident)
        .filter(
            ApartmentResident.building == req.building,
            ApartmentResident.unit_number == req.unit_number,
        )
        .first()
    )

    if resident:
        # 기존 입주민: 이름 + 전화번호 검증
        resident_match = (
            resident.resident_name == req.name
            and _normalize_phone(resident.resident_phone or "") == phone_norm
        )
        owner_match = (
            resident.owner_name == req.name
            and _normalize_phone(resident.owner_phone or "") == phone_norm
        )
        # 자가등록 입주민은 이름+전화번호로만 검증
        self_match = (
            resident.is_self_registered
            and resident.resident_name == req.name
            and _normalize_phone(resident.resident_phone or "") == phone_norm
        )

        if not (resident_match or owner_match or self_match):
            raise HTTPException(
                status_code=401,
                detail="입주민 정보가 일치하지 않습니다. 관리비 등록 정보와 동일하게 입력해주세요.",
            )
        is_new = False
    else:
        # 미등록 입주민: 자동 등록 (관리자 확인 대기)
        resident = ApartmentResident(
            building=req.building,
            unit_number=req.unit_number,
            resident_name=req.name,
            resident_phone=req.phone,
            company_id=req.company_id,
            is_self_registered=True,
            is_verified=False,
        )
        db.add(resident)
        db.commit()
        db.refresh(resident)
        logger.info(
            "입주민 자동등록: building=%s unit=%s name=%s company_id=%s",
            req.building, req.unit_number, req.name, req.company_id,
        )
        is_new = True

    token = _create_market_token(req.building, req.unit_number, req.name)
    return {
        "success": True,
        "token": token,
        "unit": req.unit_number,
        "building": req.building,
        "is_new_registration": is_new,
    }


# ── 관리자: 입주민 관리 ───────────────────────────────────────────────────────

@router.get("/admin/residents")
def list_residents(
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """당근회원 목록 — 인증한 입주민 전체 (자가등록 + ERP 등록).
    company_id 미설정(NULL) 레코드도 포함 (이전 버전 데이터 호환).
    """
    residents = (
        db.query(ApartmentResident)
        .filter(
            or_(
                ApartmentResident.company_id == admin["company_id"],
                ApartmentResident.company_id == None,   # noqa: E711
            )
        )
        .order_by(ApartmentResident.registered_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "building": r.building,
            "unit_number": r.unit_number,
            "name": r.resident_name,
            "phone": r.resident_phone,
            "is_self_registered": r.is_self_registered,
            "is_verified": r.is_verified,
            "registered_at": r.registered_at.isoformat() if r.registered_at else None,
        }
        for r in residents
    ]


@router.patch("/admin/residents/{resident_id}/verify")
def verify_resident(
    resident_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """입주민 승인"""
    r = db.query(ApartmentResident).filter(
        ApartmentResident.id == resident_id,
        ApartmentResident.company_id == admin["company_id"],
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="입주민을 찾을 수 없습니다.")
    r.is_verified = True
    db.commit()
    return {"ok": True}


@router.delete("/admin/residents/{resident_id}")
def delete_resident(
    resident_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """입주민 삭제 (허위 등록 처리)"""
    r = db.query(ApartmentResident).filter(
        ApartmentResident.id == resident_id,
        ApartmentResident.company_id == admin["company_id"],
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="입주민을 찾을 수 없습니다.")
    db.delete(r)
    db.commit()
    logger.info("입주민 삭제: id=%d by admin=%d", resident_id, admin["user_id"])
    return {"ok": True}


# ── 게시글 목록 ───────────────────────────────────────────────────────────────

@router.get("/posts")
def list_posts(
    category: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(_get_market_user_optional),
):
    q = db.query(MarketPost).filter(MarketPost.is_hidden == False)
    if category and category != "전체":
        q = q.filter(MarketPost.category == category)
    total = q.count()
    posts = q.order_by(MarketPost.created_at.desc()).offset((page - 1) * size).limit(size).all()

    items = []
    for p in posts:
        images = db.query(MarketImage).filter(MarketImage.post_id == p.id).all()
        cnt = db.query(MarketComment).filter(MarketComment.post_id == p.id).count()
        items.append(_post_to_dict(p, images, cnt))

    return {"total": total, "page": page, "size": size, "items": items}


# ── 게시글 작성 ───────────────────────────────────────────────────────────────

@router.post("/posts")
async def create_post(
    title: str = Form(...),
    content: str = Form(...),
    category: str = Form(...),
    price: int = Form(0),
    images: list[UploadFile] = File(default=[]),
    user: dict = Depends(_get_market_user),
    db: Session = Depends(get_db),
):
    if len(images) > 3:
        raise HTTPException(status_code=400, detail="이미지는 최대 3장까지 업로드 가능합니다.")

    post = MarketPost(
        category=category,
        title=title,
        content=content,
        price=price,
        writer_building=user["building"],
        writer_unit=user["unit"],
    )
    db.add(post)
    db.flush()

    saved_images = []
    for img in images:
        if not img.filename:
            continue
        file_bytes = await img.read()
        if not file_bytes:
            continue
        try:
            filename = save_image(file_bytes, img.filename)
            url = f"/uploads/{filename}"
            db.add(MarketImage(post_id=post.id, image_url=url))
            saved_images.append(url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    db.commit()
    db.refresh(post)
    return {"success": True, "post_id": post.id}


# ── 게시글 상세 ───────────────────────────────────────────────────────────────

@router.get("/posts/{post_id}")
def get_post(
    post_id: int,
    user: dict = Depends(_get_market_user),
    db: Session = Depends(get_db),
):
    post = db.query(MarketPost).filter(
        MarketPost.id == post_id, MarketPost.is_hidden == False
    ).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    images = db.query(MarketImage).filter(MarketImage.post_id == post_id).all()
    comments = db.query(MarketComment).filter(
        MarketComment.post_id == post_id
    ).order_by(MarketComment.created_at.asc()).all()

    comment_list = [
        {
            "id": c.id,
            "writer_unit": c.writer_unit,
            "content": c.content,
            "time_ago": _time_ago(c.created_at),
        }
        for c in comments
    ]

    data = _post_to_dict(post, images, len(comments))
    data["comments"] = comment_list
    data["is_owner"] = (post.writer_unit == user["unit"])
    return data


# ── 게시글 수정 ───────────────────────────────────────────────────────────────

class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    price: Optional[int] = None
    category: Optional[str] = None


@router.patch("/posts/{post_id}")
def update_post(
    post_id: int,
    body: PostUpdate,
    user: dict = Depends(_get_market_user),
    db: Session = Depends(get_db),
):
    post = _get_own_post(post_id, user, db)
    if body.title is not None:
        post.title = body.title
    if body.content is not None:
        post.content = body.content
    if body.price is not None:
        post.price = body.price
    if body.category is not None:
        post.category = body.category
    db.commit()
    return {"success": True}


# ── 게시글 삭제 ───────────────────────────────────────────────────────────────

@router.delete("/posts/{post_id}")
def delete_post(
    post_id: int,
    user: dict = Depends(_get_market_user),
    db: Session = Depends(get_db),
):
    post = _get_own_post(post_id, user, db)
    db.delete(post)
    db.commit()
    return {"success": True}


# ── 거래 상태 변경 ────────────────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: str


@router.patch("/posts/{post_id}/status")
def update_status(
    post_id: int,
    body: StatusUpdate,
    user: dict = Depends(_get_market_user),
    db: Session = Depends(get_db),
):
    if body.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 상태입니다. ({', '.join(ALLOWED_STATUSES)})")
    post = _get_own_post(post_id, user, db)
    post.status = body.status
    db.commit()
    return {"success": True, "status": post.status}


# ── 댓글 작성 ─────────────────────────────────────────────────────────────────

class CommentCreate(BaseModel):
    post_id: int
    content: str


@router.post("/comments")
def create_comment(
    body: CommentCreate,
    user: dict = Depends(_get_market_user),
    db: Session = Depends(get_db),
):
    post = db.query(MarketPost).filter(
        MarketPost.id == body.post_id, MarketPost.is_hidden == False
    ).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    comment = MarketComment(
        post_id=body.post_id,
        writer_unit=user["unit"],
        content=body.content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return {
        "success": True,
        "comment": {
            "id": comment.id,
            "writer_unit": comment.writer_unit,
            "content": comment.content,
            "time_ago": "방금 전",
        },
    }


# ── 신고 ──────────────────────────────────────────────────────────────────────

class ReportCreate(BaseModel):
    reason: str


@router.post("/posts/{post_id}/report")
def report_post(
    post_id: int,
    body: ReportCreate,
    user: dict = Depends(_get_market_user),
    db: Session = Depends(get_db),
):
    post = db.query(MarketPost).filter(MarketPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

    report = MarketReport(
        post_id=post_id,
        reporter_unit=user["unit"],
        reason=body.reason,
    )
    db.add(report)
    db.commit()
    return {"success": True}


# ── 관리자: 게시글 관리 ───────────────────────────────────────────────────────

@router.get("/admin/posts")
def admin_list_posts(
    page: int = 1,
    size: int = 20,
    category: Optional[str] = None,
    hidden: Optional[bool] = None,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """관리자용 전체 게시글 목록 (숨김 포함)."""
    q = db.query(MarketPost)
    if hidden is not None:
        q = q.filter(MarketPost.is_hidden == hidden)
    if category:
        q = q.filter(MarketPost.category == category)
    total = q.count()
    posts = q.order_by(MarketPost.created_at.desc()).offset((page - 1) * size).limit(size).all()

    items = []
    for p in posts:
        images = db.query(MarketImage).filter(MarketImage.post_id == p.id).all()
        cnt = db.query(MarketComment).filter(MarketComment.post_id == p.id).count()
        report_cnt = db.query(MarketReport).filter(MarketReport.post_id == p.id).count()

        # 입주민 정보 (이름·전화번호)
        resident = db.query(ApartmentResident).filter(
            ApartmentResident.building == p.writer_building,
            ApartmentResident.unit_number == p.writer_unit,
        ).first()
        writer_name = resident.resident_name if resident else None
        writer_phone = resident.resident_phone if resident else None

        d = _post_to_dict(p, images, cnt)
        d["writer_building"] = p.writer_building
        d["writer_name"] = writer_name
        d["writer_phone"] = writer_phone
        d["is_hidden"] = p.is_hidden
        d["hidden_reason"] = p.hidden_reason
        d["report_count"] = report_cnt
        items.append(d)

    return {
        "total": total,
        "page": page,
        "pages": math.ceil(total / size) if total else 1,
        "items": items,
    }


class AdminHideBody(BaseModel):
    hidden: bool
    reason: Optional[str] = None


@router.patch("/admin/posts/{post_id}/hide")
def admin_hide_post(
    post_id: int,
    body: AdminHideBody,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """게시글 숨김 / 복원 (사유 포함)."""
    post = db.query(MarketPost).filter(MarketPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    post.is_hidden = body.hidden
    post.hidden_reason = body.reason if body.hidden else None
    db.commit()
    return {"ok": True}


@router.delete("/admin/posts/{post_id}")
def admin_delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """관리자 게시글 영구 삭제."""
    post = db.query(MarketPost).filter(MarketPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    db.delete(post)
    db.commit()
    return {"ok": True}


# ── helper ────────────────────────────────────────────────────────────────────

def _get_own_post(post_id: int, user: dict, db: Session) -> MarketPost:
    post = db.query(MarketPost).filter(MarketPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
    if post.writer_unit != user["unit"]:
        raise HTTPException(status_code=403, detail="작성자만 변경할 수 있습니다.")
    return post
