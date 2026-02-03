from datetime import datetime

from pydantic import BaseModel


class QaCreate(BaseModel):
    company_id: int | None = None  # super_admin only; None → session company_id
    category: str
    question: str
    answer: str
    keywords: str = ""
    is_active: bool = True


class QaUpdate(BaseModel):
    company_id: int | None = None  # super_admin only
    category: str | None = None
    question: str | None = None
    answer: str | None = None
    keywords: str | None = None
    is_active: bool | None = None


class QaResponse(BaseModel):
    qa_id: int
    company_id: int
    category: str
    question: str
    answer: str
    keywords: str
    is_active: bool
    created_by: int | None = None
    updated_by: int | None = None
    view_count: int = 0
    used_count: int = 0
    created_at: datetime
    updated_at: datetime
    company_name: str | None = None

    model_config = {"from_attributes": True}


class QaListResponse(BaseModel):
    items: list[QaResponse]
    total: int
    page: int
    pages: int
