from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ChatMessageCreate(BaseModel):
    """텍스트/사진 중 최소 하나는 있어야 함. image_url은 1:1 톡 업로드 API가 돌려준
    /uploads/{파일명} 형태만 허용 (외부 URL 삽입 방지)."""
    content: str = Field("", max_length=2000)
    image_url: str | None = Field(None, max_length=500, pattern=r"^/uploads/[0-9a-f]{32}\.(jpg|jpeg|png|gif|webp)$")

    @model_validator(mode="after")
    def _require_content_or_image(self):
        if not self.content.strip() and not self.image_url:
            raise ValueError("메시지 내용 또는 사진이 필요합니다.")
        return self


class ChatMessageOut(BaseModel):
    id: int
    sender_type: str
    content: str
    image_url: str | None = None
    created_at: datetime
    alimtalk_sent: bool | None = None
    read_at: datetime | None = None

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
