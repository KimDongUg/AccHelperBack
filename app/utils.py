import json
from datetime import datetime, timedelta


def now_kst() -> datetime:
    """Naive KST (UTC+9) wall-clock time.

    The server container runs in UTC, so plain datetime.now() does not
    yield KST. Korea has no DST, so a fixed +9h offset from true UTC is
    always correct. Naive (no tzinfo) to match the DB columns and the
    admin frontend, which display datetimes as local wall-clock values
    without timezone conversion.
    """
    return datetime.utcnow() + timedelta(hours=9)


def parse_permissions(permissions_text: str | None) -> dict:
    """Parse JSON permissions text to dict."""
    if not permissions_text:
        return {}
    try:
        return json.loads(permissions_text)
    except (json.JSONDecodeError, TypeError):
        return {}


def serialize_permissions(permissions: dict | None) -> str:
    """Serialize permissions dict to JSON text."""
    if not permissions:
        return "{}"
    return json.dumps(permissions, ensure_ascii=False)
