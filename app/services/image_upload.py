"""Image upload service using local filesystem."""

import uuid
from pathlib import PurePosixPath

from app.config import UPLOAD_DIR

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def _get_extension(filename: str) -> str:
    return PurePosixPath(filename).suffix.lstrip(".").lower()


def save_image(file_bytes: bytes, original_filename: str) -> str:
    """Save image to local disk and return the relative path.

    Raises ValueError on validation failure.
    """
    ext = _get_extension(original_filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"허용되지 않는 파일 형식입니다. ({', '.join(ALLOWED_EXTENSIONS)})")

    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError("파일 크기는 5MB 이하만 가능합니다.")

    unique_name = f"{uuid.uuid4().hex}.{ext}"
    dest = UPLOAD_DIR / unique_name
    dest.write_bytes(file_bytes)

    # Return path segment used in URL: /uploads/{filename}
    return unique_name
