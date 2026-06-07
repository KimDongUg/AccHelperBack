import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from app.config import COLLECTOR_API_KEY, DATA_DIR

logger = logging.getLogger("acchelper")
router = APIRouter(prefix="/api/collector", tags=["collector"])

_PERSISTENT = Path("/data/uploads/collector")
_FALLBACK   = DATA_DIR / "collector"


def _save_dir() -> Path:
    for p in (_PERSISTENT, _FALLBACK, Path("/tmp/collector")):
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            continue
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
    request: Request,
    filename: str = Query(default="fee.xlsx"),
    _=Depends(_verify_api_key),
):
    """ERP 수집기 → 관리비 엑셀 업로드 (raw bytes, API 키 인증)"""
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="엑셀 파일(.xlsx)만 업로드 가능합니다.")

    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="파일이 비어 있습니다.")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="파일 크기 초과 (최대 50MB).")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = _save_dir() / f"fee_{timestamp}.xlsx"
    save_path.write_bytes(content)

    logger.info("관리비 엑셀 업로드: %s (%d bytes)", save_path.name, len(content))
    return {"ok": True, "filename": save_path.name, "size": len(content)}
