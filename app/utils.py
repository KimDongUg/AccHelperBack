import json


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
