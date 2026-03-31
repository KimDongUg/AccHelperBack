"""
미답변 질문 알림톡 트리거 서비스
- 중복 발송 방지 (alert_count 체크)
- 관리자 필터링 (receive_unanswered_alert=True, is_active=True)
- 예외 처리 (관리자 없음, 전화번호 없음, 발송 실패)
"""

import logging
from datetime import datetime, timedelta, timezone

from app import config

KST = timezone(timedelta(hours=9))
from app.database import SessionLocal
from app.models.admin_user import AdminUser
from app.models.company import Company
from app.models.unanswered_question import UnansweredQuestion
from app.services.solapi_service import send_unanswered_alimtalk

logger = logging.getLogger(__name__)


def _build_admin_url(company_id: int, question_id: int) -> str:
    return (
        f"{config.ADMIN_BASE_URL}/admin.html"
        f"?company={company_id}&questionId={question_id}"
    )


def _format_time(dt: datetime) -> str:
    kst_dt = dt.replace(tzinfo=timezone.utc).astimezone(KST)
    return kst_dt.strftime("%Y-%m-%d %H:%M")


def trigger_unanswered_alert(question_id: int) -> None:
    """
    미답변 질문 알림톡 트리거 (BackgroundTasks에서 호출)
    - 자체 DB 세션 생성 (백그라운드 태스크이므로)
    - 중복 방지: alert_count > 0이면 skip
    """
    db = SessionLocal()
    try:
        # 1. 질문 조회
        question = db.query(UnansweredQuestion).get(question_id)
        if not question or question.alert_count > 0:
            return

        # 2. 아파트(회사)명 조회
        company = db.query(Company).filter(
            Company.company_id == question.company_id
        ).first()
        apt_name = company.company_name if company else "관리자"

        # 3. 알림 수신 관리자 목록 조회
        admins = db.query(AdminUser).filter(
            AdminUser.company_id == question.company_id,
            AdminUser.receive_unanswered_alert == True,
            AdminUser.is_active == True,
        ).all()

        if not admins:
            logger.warning(
                "[Alert] 알림 수신 관리자 없음 | company_id=%s", question.company_id
            )
            return

        # 4. 각 관리자에게 알림톡 발송
        admin_url = _build_admin_url(question.company_id, question.id)
        success_count = 0

        for admin in admins:
            if not admin.phone:
                logger.warning(
                    "[Alert] 전화번호 없음 | admin_id=%s → skip", admin.user_id
                )
                continue
            try:
                send_unanswered_alimtalk(
                    to=admin.phone,
                    apt_name=apt_name,
                    question=question.question,
                    time=_format_time(question.created_at),
                    url=admin_url,
                )
                success_count += 1
                logger.info(
                    "[Alert] 알림톡 발송 성공 | admin=%s | phone=%s",
                    admin.full_name or admin.email,
                    admin.phone,
                )
            except Exception as e:
                logger.error(
                    "[Alert] 알림톡 발송 실패 | admin_id=%s | %s", admin.user_id, e
                )

        # 5. 발송 기록 업데이트 (1명이라도 성공 시)
        if success_count > 0:
            question.alert_count = 1
            question.alert_sent_at = datetime.utcnow()
            db.commit()

    except Exception as e:
        logger.error(
            "[Alert] trigger_unanswered_alert 오류 | question_id=%s | %s",
            question_id, e,
        )
    finally:
        db.close()
