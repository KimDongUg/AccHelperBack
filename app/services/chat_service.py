import re

from sqlalchemy.orm import Session

from app.models.qa_knowledge import QaKnowledge

KOREAN_PARTICLES = re.compile(
    r"(은|는|이|가|을|를|의|에|에서|로|으로|와|과|도|만|부터|까지|라|이라|요|인가요|인가|하나요|할까요|인지|한가요|되나요|어떻게|무엇|뭐|어떤)$"
)

FALLBACK_MESSAGE = (
    "죄송합니다. 해당 질문에 대한 답변을 찾지 못했습니다. "
    "다른 키워드로 다시 질문해 주시거나, 관리자에게 문의해 주세요."
)


def normalize_text(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[?!.,;:~\s]+", " ", text)
    return text.strip()


def strip_particles(token: str) -> str:
    prev = ""
    while prev != token:
        prev = token
        token = KOREAN_PARTICLES.sub("", token)
    return token


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    tokens = normalized.split()
    result = []
    for token in tokens:
        stripped = strip_particles(token)
        if len(stripped) >= 2:
            result.append(stripped)
    return result


def search_qa(
    db: Session, question: str, category: str | None = None
) -> tuple[str, str | None, int | None]:
    query = db.query(QaKnowledge).filter(QaKnowledge.is_active == True)
    if category and category != "전체":
        query = query.filter(QaKnowledge.category == category)

    qa_list = query.all()
    if not qa_list:
        return FALLBACK_MESSAGE, None, None

    tokens = tokenize(question)
    normalized_question = normalize_text(question)

    best_score = 0
    best_qa = None

    for qa in qa_list:
        score = 0
        qa_question_lower = qa.question.lower()
        qa_keywords_lower = qa.keywords.lower() if qa.keywords else ""
        qa_answer_lower = qa.answer.lower()

        # Full substring match
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
        return FALLBACK_MESSAGE, None, None

    return best_qa.answer, best_qa.category, best_qa.qa_id
