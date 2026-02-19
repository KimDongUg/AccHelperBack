"""Chat service with RAG (vector search + LLM) and keyword fallback."""

import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import CHAT_MODEL, OPENAI_API_KEY, RAG_MIN_SCORE, RAG_TOP_K
from app.models.prompt_template import PromptTemplate
from app.models.qa_knowledge import QaKnowledge
from app.services.embedding_service import generate_embedding

logger = logging.getLogger("acchelper")

KOREAN_PARTICLES = re.compile(
    r"(은|는|이|가|을|를|의|에|에서|로|으로|와|과|도|만|부터|까지|라|이라|요|인가요|인가|하나요|할까요|인지|한가요|되나요|어떻게|무엇|뭐|어떤)$"
)

FALLBACK_MESSAGE = (
    "죄송합니다. 해당 질문에 대한 답변을 찾지 못했습니다. "
    "다른 키워드로 다시 질문해 주시거나, 관리사무소에 문의해 주세요."
)

DEFAULT_SYSTEM_PROMPT = """당신은 아파트 관리 도우미 챗봇입니다. 아래 규칙을 반드시 따르세요:

1. 제공된 근거(Evidence) 내용만을 기반으로 답변하세요.
2. 근거에서 답을 찾을 수 없으면 "해당 내용은 확인이 필요합니다. 관리사무소에 문의해 주세요."라고 답하세요.
3. 친절하고 간결한 한국어로 답변하세요.
4. 답변에 근거 번호를 포함하지 마세요."""


@dataclass
class RAGResult:
    answer: str
    used_rag: bool = False
    evidence_ids: list[int] = field(default_factory=list)
    tokens_used: int = 0
    avg_similarity: float = 0.0


# ─── Keyword search (fallback) ───


def normalize_text(text_str: str) -> str:
    text_str = text_str.strip().lower()
    text_str = re.sub(r"[?!.,;:~\s]+", " ", text_str)
    return text_str.strip()


def strip_particles(token: str) -> str:
    prev = ""
    while prev != token:
        prev = token
        token = KOREAN_PARTICLES.sub("", token)
    return token


def tokenize(text_str: str) -> list[str]:
    normalized = normalize_text(text_str)
    tokens = normalized.split()
    result = []
    for token in tokens:
        stripped = strip_particles(token)
        if len(stripped) >= 2:
            result.append(stripped)
    return result


def search_qa(
    db: Session, question: str, category: str | None = None, company_id: int = 1
) -> tuple[str, str | None, int | None, float | None]:
    """Keyword-based QA search. Returns (answer, category, qa_id, confidence_score)."""
    query = db.query(QaKnowledge).filter(QaKnowledge.is_active == True)
    if company_id != 0:
        query = query.filter(QaKnowledge.company_id == company_id)
    if category and category != "전체":
        query = query.filter(QaKnowledge.category == category)

    qa_list = query.all()
    if not qa_list:
        return FALLBACK_MESSAGE, None, None, None

    tokens = tokenize(question)
    normalized_question = normalize_text(question)

    best_score = 0
    best_qa = None

    for qa in qa_list:
        score = 0
        qa_question_lower = qa.question.lower()
        qa_keywords_lower = qa.keywords.lower() if qa.keywords else ""
        qa_answer_lower = qa.answer.lower()

        if normalized_question in qa_question_lower:
            score += 5

        for token in tokens:
            if token in qa_question_lower:
                score += 3
            if token in qa_keywords_lower:
                score += 2
            if token in qa_answer_lower:
                score += 1

        if score > best_score:
            best_score = score
            best_qa = qa

    if best_score == 0 or best_qa is None:
        return FALLBACK_MESSAGE, None, None, 0.0

    max_possible = 5 + len(tokens) * 6
    confidence = min(best_score / max(max_possible, 1), 1.0)

    return best_qa.answer, best_qa.category, best_qa.qa_id, round(confidence, 3)


# ─── RAG search (vector + LLM) ───


def _get_system_prompt(db: Session, company_id: int) -> str:
    """Get company-specific system prompt or default."""
    try:
        template = (
            db.query(PromptTemplate)
            .filter(
                PromptTemplate.company_id == company_id,
                PromptTemplate.is_active == True,
            )
            .first()
        )
        if template:
            return template.system_prompt
    except Exception:
        pass
    return DEFAULT_SYSTEM_PROMPT


def search_qa_rag(db: Session, question: str, company_id: int) -> RAGResult:
    """RAG-based search: embed question → vector similarity → LLM generation."""

    # If no OpenAI key, fall back to keyword search
    if not OPENAI_API_KEY:
        answer, category, qa_id, confidence = search_qa(db, question, None, company_id)
        return RAGResult(
            answer=answer,
            used_rag=False,
            evidence_ids=[qa_id] if qa_id else [],
        )

    # 1. Generate question embedding
    q_embedding = generate_embedding(question)
    if q_embedding is None:
        answer, category, qa_id, confidence = search_qa(db, question, None, company_id)
        return RAGResult(
            answer=answer,
            used_rag=False,
            evidence_ids=[qa_id] if qa_id else [],
        )

    # 2. Vector similarity search via pgvector
    try:
        embedding_str = "[" + ",".join(str(x) for x in q_embedding) + "]"

        sql = text("""
            SELECT e.qa_id, e.embedding_text,
                   1 - (e.embedding <=> :embedding::vector) AS similarity
            FROM qa_embeddings e
            JOIN qa_knowledge q ON q.qa_id = e.qa_id
            WHERE e.company_id = :company_id
              AND q.is_active = true
              AND 1 - (e.embedding <=> :embedding::vector) >= :min_score
            ORDER BY similarity DESC
            LIMIT :top_k
        """)

        results = db.execute(sql, {
            "embedding": embedding_str,
            "company_id": company_id,
            "min_score": RAG_MIN_SCORE,
            "top_k": RAG_TOP_K,
        }).fetchall()

    except Exception as e:
        logger.warning("Vector search failed, falling back to keyword: %s", e)
        answer, category, qa_id, confidence = search_qa(db, question, None, company_id)
        return RAGResult(
            answer=answer,
            used_rag=False,
            evidence_ids=[qa_id] if qa_id else [],
        )

    if not results:
        # No similar results found — try keyword fallback
        answer, category, qa_id, confidence = search_qa(db, question, None, company_id)
        return RAGResult(
            answer=answer,
            used_rag=False,
            evidence_ids=[qa_id] if qa_id else [],
        )

    # 3. Build context from evidence
    evidence_ids = [row[0] for row in results]
    similarities = [float(row[2]) for row in results]
    avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0

    evidence_texts = []
    for i, row in enumerate(results, 1):
        evidence_texts.append(f"[근거 {i}] {row[1]}")
    context = "\n\n".join(evidence_texts)

    # 4. Generate answer with LLM
    system_prompt = _get_system_prompt(db, company_id)

    user_message = f"""질문: {question}

근거:
{context}"""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=1000,
        )

        answer = response.choices[0].message.content.strip()
        tokens_used = response.usage.total_tokens if response.usage else 0

        return RAGResult(
            answer=answer,
            used_rag=True,
            evidence_ids=evidence_ids,
            tokens_used=tokens_used,
            avg_similarity=round(avg_similarity, 4),
        )

    except Exception as e:
        logger.error("LLM generation failed: %s", e)
        # Fallback: return the best evidence text directly
        best_qa = db.query(QaKnowledge).filter(QaKnowledge.qa_id == evidence_ids[0]).first()
        if best_qa:
            return RAGResult(
                answer=best_qa.answer,
                used_rag=False,
                evidence_ids=evidence_ids,
                avg_similarity=round(avg_similarity, 4),
            )

        return RAGResult(answer=FALLBACK_MESSAGE, used_rag=False)
