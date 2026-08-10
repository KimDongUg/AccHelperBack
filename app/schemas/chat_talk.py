from datetime import datetime

from pydantic import BaseModel, Field


class ChatMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class ChatMessageOut(BaseModel):
    id: int
    sender_type: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatThreadOut(BaseModel):
    id: int
    status: str
    dong: str
    ho: str
    resident_name: str
    claimed_admin_id: int | None = None
    claimed_admin_name: str | None = None
    created_at: datetime
    last_message_at: datetime
    messages: list[ChatMessageOut] = []


class ChatThreadListItem(BaseModel):
    id: int
    dong: str
    ho: str
    resident_name: str
    status: str
    claimed_admin_id: int | None = None
    claimed_admin_name: str | None = None
    unread_count: int
    last_message_at: datetime
    last_message_preview: str


class ChatThreadListResponse(BaseModel):
    items: list[ChatThreadListItem]
    page: int
    pages: int
    total: int


class ThreadStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(open|closed)$")


class AvailabilityResponse(BaseModel):
    available: bool
    reason: str
    message: str
