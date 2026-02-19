"""Prompt template management for RAG system prompt customization."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models.prompt_template import PromptTemplate
from app.services.chat_service import DEFAULT_SYSTEM_PROMPT

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


class PromptCreate(BaseModel):
    name: str = "default"
    system_prompt: str


class PromptUpdate(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    is_active: bool | None = None


class PromptResponse(BaseModel):
    id: int
    company_id: int
    name: str
    system_prompt: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[PromptResponse])
def list_prompts(
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """List all prompt templates for the company."""
    company_id = user["company_id"]
    query = db.query(PromptTemplate)
    if company_id != 0:
        query = query.filter(PromptTemplate.company_id == company_id)
    return query.order_by(PromptTemplate.id).all()


@router.get("/default-prompt")
def get_default_prompt(user: dict = Depends(require_admin)):
    """Get the default system prompt template."""
    return {"system_prompt": DEFAULT_SYSTEM_PROMPT}


@router.post("", response_model=PromptResponse, status_code=201)
def create_prompt(
    data: PromptCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """Create a new prompt template."""
    company_id = user["company_id"]
    if company_id == 0:
        raise HTTPException(status_code=400, detail="회사를 선택해 주세요.")

    template = PromptTemplate(
        company_id=company_id,
        name=data.name,
        system_prompt=data.system_prompt,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.put("/{prompt_id}", response_model=PromptResponse)
def update_prompt(
    prompt_id: int,
    data: PromptUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """Update a prompt template."""
    company_id = user["company_id"]
    query = db.query(PromptTemplate).filter(PromptTemplate.id == prompt_id)
    if company_id != 0:
        query = query.filter(PromptTemplate.company_id == company_id)
    template = query.first()
    if not template:
        raise HTTPException(status_code=404, detail="프롬프트를 찾을 수 없습니다.")

    if data.name is not None:
        template.name = data.name
    if data.system_prompt is not None:
        template.system_prompt = data.system_prompt
    if data.is_active is not None:
        template.is_active = data.is_active
    template.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(template)
    return template


@router.delete("/{prompt_id}")
def delete_prompt(
    prompt_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """Delete a prompt template."""
    company_id = user["company_id"]
    query = db.query(PromptTemplate).filter(PromptTemplate.id == prompt_id)
    if company_id != 0:
        query = query.filter(PromptTemplate.company_id == company_id)
    template = query.first()
    if not template:
        raise HTTPException(status_code=404, detail="프롬프트를 찾을 수 없습니다.")

    db.delete(template)
    db.commit()
    return {"success": True, "message": "프롬프트가 삭제되었습니다."}
