import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi import UploadFile
from fastapi import File

from app.config import COLLECTOR_API_KEY, DATA_DIR

logger = logging.getLogger("acchelper")
router = APIRouter(prefix="/api/collector", tags=["collector"])

# 영구 디스크(/data/uploads)가 있으면 그 하위에, 없으면 DATA_DIR 하위에 저장
_PERSISTENT = Path("/data/uploads/collector")
_FALLBACK   = DATA_DIR / "collector"


def _collector_dir() -> Path:
    try:
        _PERSISTENT.mkdir(parents=True, exist_ok=True)
        return _PERSISTENT
    except Exception:
        pass
    try:
        _FALLBACK.mkdir(parents=True, exist_ok=True)
        return _FALLBACK
    except Exception:
        return Path("/tmp")


def _verify_api_key(authorization: str = Header(...)):
    if not COLLECTOR_API_KEY:
        raise HTTPException(status_code=503, detail="서버 COLLECTOR_API_KEY가 설정되지 않았습니다.")
    if authorization != f"Bearer {COLLECTOR_API_KEY}":
        raise HTTPException(status_code=401, detail="API 키 인증 실패")


@router.get("/health")
def health():
    return {"ok": True}


@router.post("/upload")
async def upload_fee_excel(
    file: UploadFile = File(...),
    _=Depends(_verify_api_key),
):
    """ERP 수집기 → 관리비 엑셀 업로드 (API 키 인증)"""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="엑셀 파일(.xlsx)만 업로드 가능합니다.")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="파일 크기 초과 (최대 50MB).")

    save_dir  = _collector_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = save_dir / f"fee_{timestamp}.xlsx"
    save_path.write_bytes(content)

    logger.info("관리비 엑셀 업로드: %s (%d bytes)", save_path.name, len(content))
    return {"ok": True, "filename": save_path.name, "size": len(content)}
