"""민원게시판 API."""

import math
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, optional_admin
from app.models.complaint import Complaint
from app.models.complaint_person import ComplaintPerson
from app.services.alert_service import trigger_complaint_alert

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


@router.get("/{complaint_id}")
def get_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    admin: dict | None = Depends(optional_admin),
):
    c = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="민원글을 찾을 수 없습니다.")

    is_admin = admin is not None and admin.get("company_id") == c.company_id

    if c.is_deleted:
        return {
            "id": c.id,
            "is_deleted": True,
            "delete_reason": c.delete_reason,
            "writer": _writer_display(c.dong, c.ho),
            "writer_name": c.writer_name if is_admin else None,
            "writer_phone": c.writer_phone if is_admin else None,
            "title": "(삭제된 글)",
            "content": "",
            "time_ago": _time_ago(c.created_at),
            "reply": None,
        }

    return {
        "id": c.id,
        "is_deleted": False,
        "writer": _writer_display(c.dong, c.ho),
        "writer_name": c.writer_name if is_admin else None,
        "writer_phone": c.writer_phone if is_admin else None,
        "title": c.title,
        "content": c.content,
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
