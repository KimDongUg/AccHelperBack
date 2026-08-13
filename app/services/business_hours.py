"""1:1 톡 영업시간 판정 서비스.

평일 09:00~18:00, 점심시간(12:00~13:30) 제외, 주말/법정공휴일 제외.
공휴일은 공공데이터포털(data.go.kr) "한국천문연구원_특일 정보" API 중
getRestDeInfo(공휴일 정보, 대체공휴일 포함 실제 휴일 여부 isHoliday=Y 기준)를
연 단위로 캐싱해서 사용한다.

주의: API 응답 포맷(JSON 구조, 단일 결과 시 dict vs list)은 실제
HOLIDAY_API_SERVICE_KEY 발급 후 라이브 호출로 검증이 필요한 1차 초안이다.
"""

import logging
import time
from datetime import datetime

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import HOLIDAY_API_SERVICE_KEY
from app.utils import now_kst

logger = logging.getLogger("acchelper")

WORK_START = (9, 0)
WORK_END = (18, 0)
LUNCH_START = (12, 0)
LUNCH_END = (13, 30)

UNAVAILABLE_MESSAGE = (
    "현재 상담 가능 시간이 아닙니다. "
    "평일 09:00~18:00(점심시간 12:00~13:30 제외, 주말·공휴일 제외)에 다시 이용해 주세요."
)

HOLIDAY_API_URL = "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"

# 공휴일 API 장애 시 매 요청마다 재호출하지 않도록 프로세스 내 쿨다운(초)
_HOLIDAY_FETCH_COOLDOWN_SEC = 3600
_last_fetch_attempt: dict[int, float] = {}  # {year: epoch_seconds}


def _fetch_holidays_from_api(year: int) -> list[dict]:
    """공공데이터포털에서 해당 연도의 법정공휴일 목록을 가져온다.

    실패 시(키 미설정, 네트워크 오류, 응답 파싱 실패 등) 빈 리스트를 반환한다
    (fail-open — 상위 호출부가 "평일로 간주"하고 톡을 계속 허용하도록).
    """
    if not HOLIDAY_API_SERVICE_KEY:
        return []

    holidays: list[dict] = []
    try:
        with httpx.Client(timeout=10) as client:
            for month in range(1, 13):
                resp = client.get(
                    HOLIDAY_API_URL,
                    params={
                        "serviceKey": HOLIDAY_API_SERVICE_KEY,
                        "solYear": str(year),
                        "solMonth": f"{month:02d}",
                        "numOfRows": "100",
                        "_type": "json",
                    },
                )
                resp.raise_for_status()
                body = resp.json().get("response", {}).get("body", {})
                items = (body.get("items") or {}).get("item") or []
                if isinstance(items, dict):
                    items = [items]
                for item in items:
                    if item.get("isHoliday") != "Y":
                        continue
                    holidays.append({
                        "locdate": str(item.get("locdate", "")),
                        "name": item.get("dateName", ""),
                    })
    except Exception as e:
        logger.warning("[BusinessHours] 공휴일 API 호출 실패 (year=%s): %s", year, e)
        return []

    return holidays


def get_holidays_for_year(db: Session, year: int) -> set[str]:
    """해당 연도의 공휴일(YYYYMMDD) 집합을 반환. DB 캐시 우선, 없으면 API 조회 후 캐싱."""
    rows = db.execute(
        text("SELECT holiday_date FROM public_holidays WHERE year = :year"),
        {"year": year},
    ).fetchall()
    if rows:
        return {r[0] for r in rows}

    now = time.time()
    last_attempt = _last_fetch_attempt.get(year, 0)
    if now - last_attempt < _HOLIDAY_FETCH_COOLDOWN_SEC:
        return set()  # 최근에 실패했음 — 쿨다운 중, fail-open
    _last_fetch_attempt[year] = now

    holidays = _fetch_holidays_from_api(year)
    if not holidays:
        return set()

    try:
        for h in holidays:
            db.execute(
                text(
                    "INSERT INTO public_holidays (year, holiday_date, name) "
                    "VALUES (:year, :date, :name) "
                    "ON CONFLICT (year, holiday_date) DO NOTHING"
                ),
                {"year": year, "date": h["locdate"], "name": h["name"]},
            )
        db.commit()
    except Exception:
        # SQLite는 ON CONFLICT 대상 지정이 다를 수 있어 실패해도 캐싱 실패일 뿐
        # 판정 자체(fail-open)에는 영향 없도록 조용히 롤백
        db.rollback()

    return {h["locdate"] for h in holidays}


def is_business_hours(db: Session, dt: datetime | None = None) -> tuple[bool, str]:
    """영업시간(1:1 톡 가능 시간) 여부와 사유를 반환한다.

    reason: "ok" | "weekend" | "outside_hours" | "lunch" | "holiday"
    """
    dt = dt or now_kst()

    if dt.weekday() >= 5:  # 5=토, 6=일
        return False, "weekend"

    t = (dt.hour, dt.minute)
    if t < WORK_START or t >= WORK_END:
        return False, "outside_hours"

    if False and LUNCH_START <= t < LUNCH_END:  # TEMP: 1:1톡 채널 ID 테스트용 임시 비활성화, 테스트 후 원복 예정
        return False, "lunch"

    holidays = get_holidays_for_year(db, dt.year)
    if dt.strftime("%Y%m%d") in holidays:
        return False, "holiday"

    return True, "ok"


def get_availability(db: Session, dt: datetime | None = None) -> dict:
    """1:1 톡 / 관리실 문자 링크가 공유하는 가용성 응답."""
    available, reason = is_business_hours(db, dt)
    return {
        "available": available,
        "reason": reason,
        "message": "" if available else UNAVAILABLE_MESSAGE,
    }
