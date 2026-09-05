from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models.notice import Notice
from app.schemas.notice import (
    NoticeCreate,
    NoticeListResponse,
    NoticePublicDetail,
    NoticePublicItem,
    NoticePublicListResponse,
    NoticeResponse,
    NoticeUpdate,
)
from app.utils import now_kst

router = APIRouter(prefix="/api/notices", tags=["notices"])


# --- Public endpoints (no auth) — 입주민용 공지사항 목록/상세 ---

@router.get("/public/list", response_model=NoticePublicListResponse)
def list_public_notices(
    company_id: int = Query(...),
    db: Session = Depends(get_db),
):
    items = (
        db.query(Notice)
        .filter(Notice.company_id == company_id)
        .order_by(Notice.created_at.desc())
        .all()
    )
    return NoticePublicListResponse(
        items=[NoticePublicItem.model_validate(n) for n in items]
    )


@router.get("/public/{notice_id}", response_model=NoticePublicDetail)
def get_public_notice(
    notice_id: int,
    company_id: int = Query(...),
    db: Session = Depends(get_db),
):
    notice = (
        db.query(Notice)
        .filter(Notice.id == notice_id, Notice.company_id == company_id)
        .first()
    )
    if not notice:
        raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다.")
    return NoticePublicDetail.model_validate(notice)


# --- Admin endpoints ---

@router.get("", response_model=NoticeListResponse)
def list_notices(
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    items = (
        db.query(Notice)
        .filter(Notice.company_id == admin["company_id"])
        .order_by(Notice.created_at.desc())
        .all()
    )
    return NoticeListResponse(items=[NoticeResponse.model_validate(n) for n in items])


@router.post("", response_model=NoticeResponse, status_code=201)
def create_notice(
    data: NoticeCreate,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    company_id = admin["company_id"]

    if data.is_active:
        db.query(Notice).filter(Notice.company_id == company_id).update(
            {Notice.is_active: False}, synchronize_session="fetch"
        )

    notice = Notice(
        company_id=company_id,
        text=data.text.strip(),
        text_link=data.text_link.strip() if data.text_link else None,
        is_active=data.is_active,
    )
    db.add(notice)
    db.commit()
    db.refresh(notice)
    return NoticeResponse.model_validate(notice)


@router.put("/{notice_id}", response_model=NoticeResponse)
def update_notice(
    notice_id: int,
    data: NoticeUpdate,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    company_id = admin["company_id"]
    notice = (
        db.query(Notice)
        .filter(Notice.id == notice_id, Notice.company_id == company_id)
        .first()
    )
    if not notice:
        raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다.")

    if data.is_active:
        db.query(Notice).filter(
            Notice.company_id == company_id, Notice.id != notice_id
        ).update({Notice.is_active: False}, synchronize_session="fetch")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(notice, key, value.strip() if isinstance(value, str) else value)
    notice.updated_at = now_kst()

    db.commit()
    db.refresh(notice)
    return NoticeResponse.model_validate(notice)


@router.delete("/{notice_id}")
def delete_notice(
    notice_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    company_id = admin["company_id"]
    notice = (
        db.query(Notice)
        .filter(Notice.id == notice_id, Notice.company_id == company_id)
        .first()
    )
    if not notice:
        raise HTTPException(status_code=404, detail="공지사항을 찾을 수 없습니다.")

    db.delete(notice)
    db.commit()
    return {"success": True}
