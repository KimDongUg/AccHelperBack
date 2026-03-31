"""
솔라피(Solapi) 카카오 알림톡 발송 서비스
- REST API 직접 호출 (httpx sync)
- HMAC-SHA256 인증 방식 사용
"""

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone

import httpx

from app import config

logger = logging.getLogger(__name__)

SOLAPI_SEND_URL = "https://api.solapi.com/messages/v4/send"


def _make_auth_header() -> str:
    """솔라피 HMAC 인증 헤더 생성"""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    salt = uuid.uuid4().hex
    data = f"date={date}&salt={salt}"
    sig = hmac.new(
        config.SOLAPI_API_SECRET.encode(),
        data.encode(),
        hashlib.sha256,
    ).hexdigest()
    return (
        f"HMAC-SHA256 apiKey={config.SOLAPI_API_KEY}, "
        f"date={date}, salt={salt}, signature={sig}"
    )


def send_unanswered_alimtalk(
    to: str,
    apt_name: str,
    question: str,
    time: str,
    url: str,
) -> bool:
    """
    미답변 알림톡 발송
    Returns True if success, False if failed
    """
    payload = {
        "message": {
            "to": to.replace("-", ""),
            "kakaoOptions": {
                "pfId": config.SOLAPI_PF_ID,
                "templateId": config.SOLAPI_TEMPLATE_ID,
                "variables": {
                    "#{apt_name}": apt_name,
                    "#{question}": question,
                    "#{time}": time,
                    "#{url}": url,
                },
            },
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": _make_auth_header(),
    }

    with httpx.Client(timeout=10.0) as client:
        resp = client.post(SOLAPI_SEND_URL, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.error("[Solapi] %s %s | payload=%s", resp.status_code, resp.text, payload)
        resp.raise_for_status()
        return True
