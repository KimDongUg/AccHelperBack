"""OpenAI embedding generation and QA embedding management."""

import logging

from sqlalchemy.orm import Session

from app.config import EMBEDDING_MODEL, OPENAI_API_KEY
from app.models.qa_embedding import QaEmbedding
from app.models.qa_knowledge import QaKnowledge

logger = logging.getLogger("acchelper")

_client = None


def _get_openai_client():
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            return None
        try:
            from openai import OpenAI
            _client = OpenAI(api_key=OPENAI_API_KEY)
        except Exception as e:
            logger.warning("Failed to initialize OpenAI client: %s", e)
            return None
    return _client


def generate_embedding(text: str) -> list[float] | None:
    """Generate embedding vector using OpenAI API. Returns None if API key is missing."""
    client = _get_openai_client()
    if not client:
        logger.debug("OpenAI API key not configured, skipping embedding generation")
        return None

    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error("Embedding generation failed: %s", e)
        return None


def build_embedding_text(qa: QaKnowledge) -> str:
    """Build the text to embed from a QA entry."""
    parts = []
    if qa.category:
        parts.append(f"[{qa.category}]")
    parts.append(qa.question)
    if hasattr(qa, "aliases") and qa.aliases:
        parts.append(f"동의어: {qa.aliases}")
    parts.append(qa.answer)
    if hasattr(qa, "tags") and qa.tags:
        parts.append(f"태그: {qa.tags}")
    if qa.keywords:
        parts.append(f"키워드: {qa.keywords}")
    return " ".join(parts)


def upsert_qa_embedding(db: Session, qa: QaKnowledge) -> bool:
    """Generate embedding for a QA item and upsert into qa_embeddings. Returns True on success."""
    embedding_text = build_embedding_text(qa)
    vector = generate_embedding(embedding_text)

    if vector is None:
        return False

    existing = db.query(QaEmbedding).filter(QaEmbedding.qa_id == qa.qa_id).first()
    if existing:
        existing.embedding_text = embedding_text
        existing.embedding = vector
        existing.company_id = qa.company_id
    else:
        emb = QaEmbedding(
            qa_id=qa.qa_id,
            company_id=qa.company_id,
            embedding_text=embedding_text,
            embedding=vector,
        )
        db.add(emb)

    db.flush()
    logger.info("Embedding upserted for qa_id=%d", qa.qa_id)
    return True


def delete_qa_embedding(db: Session, qa_id: int):
    """Delete embedding for a QA item."""
    db.query(QaEmbedding).filter(QaEmbedding.qa_id == qa_id).delete()
    db.flush()


def bulk_rebuild_embeddings(db: Session, company_id: int | None = None) -> dict:
    """Rebuild embeddings for all active QA items. Returns stats."""
    query = db.query(QaKnowledge).filter(QaKnowledge.is_active == True)
    if company_id:
        query = query.filter(QaKnowledge.company_id == company_id)

    qa_list = query.all()
    success = 0
    failed = 0

    for qa in qa_list:
        if upsert_qa_embedding(db, qa):
            success += 1
        else:
            failed += 1

    db.commit()
    return {"total": len(qa_list), "success": success, "failed": failed}
