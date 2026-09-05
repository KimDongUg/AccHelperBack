from datetime import datetime

from pydantic import BaseModel


class NoticeCreate(BaseModel):
    text: str
    text_link: str | None = None
    is_active: bool = False


class NoticeUpdate(BaseModel):
    text: str | None = None
    text_link: str | None = None
    is_active: bool | None = None


class NoticeResponse(BaseModel):
    id: int
    text: str
    text_link: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoticeListResponse(BaseModel):
    items: list[NoticeResponse]


class NoticePublicItem(BaseModel):
    id: int
    text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class NoticePublicListResponse(BaseModel):
    items: list[NoticePublicItem]


class NoticePublicDetail(BaseModel):
    id: int
    text: str
    text_link: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
