"""Image upload service using Supabase Storage."""

import logging
import uuid
from pathlib import PurePosixPath

import httpx

from app.config import SUPABASE_BUCKET, SUPABASE_KEY, SUPABASE_URL

logger = logging.getLogger("acchelper")

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

CONTENT_TYPE_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _get_extension(filename: str) -> str:
    return PurePosixPath(filename).suffix.lstrip(".").lower()


async def upload_image(file_bytes: bytes, original_filename: str) -> str:
    """Upload image to Supabase Storage and return public URL.

    Raises ValueError on validation failure, RuntimeError on upload failure.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY 환경변수가 설정되지 않았습니다.")

    ext = _get_extension(original_filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"허용되지 않는 파일 형식입니다. ({', '.join(ALLOWED_EXTENSIONS)})")

    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError("파일 크기는 5MB 이하만 가능합니다.")

    # Generate unique filename
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    storage_path = f"uploads/{unique_name}"
    content_type = CONTENT_TYPE_MAP.get(ext, "application/octet-stream")

    # Upload via Supabase Storage REST API
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{storage_path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": content_type,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(upload_url, content=file_bytes, headers=headers)

    if resp.status_code not in (200, 201):
        logger.error("Supabase upload failed: %s %s", resp.status_code, resp.text)
        raise RuntimeError(f"이미지 업로드 실패 (status={resp.status_code})")

    # Return public URL
    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{storage_path}"
    return public_url
