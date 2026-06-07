import json
import logging
from datetime import datetime
from pathlib import Path

import openpyxl
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import COLLECTOR_API_KEY, DATA_DIR
from app.database import get_db
from app.models.fee_data import FeeEntry

logger = logging.getLogger("acchelper")
router = APIRouter(prefix="/api/collector", tags=["collector"])

_PERSISTENT = Path("/data/uploads/collector")
_FALLBACK   = DATA_DIR / "collector"

_FIXED_KEYS = {"동", "호", "휴대폰", "name", "이름"}


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


def _parse_and_store(file_path: Path, year_month: str, db: Session):
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            return 0

        headers = [str(v).strip() if v is not None else "" for v in rows[0]]

        # 기존 같은 년월 데이터 삭제
        db.query(FeeEntry).filter(FeeEntry.year_month == year_month).delete()

        count = 0
        for row in rows[1:]:
            if not any(v for v in row):
                continue
            rd = {headers[i]: str(v).strip() if v is not None else "" for i, v in enumerate(row)}

            dong  = rd.get("동", "")
            ho    = rd.get("호", "")
            name  = rd.get("name", rd.get("이름", ""))
            phone = rd.get("휴대폰", "").replace("-", "").replace(" ", "")

            if not dong or not ho:
                continue

            fee_data = {k: v for k, v in rd.items() if k not in _FIXED_KEYS and v}
            entry = FeeEntry(
                year_month=year_month,
                dong=dong, ho=ho,
                name=name, phone=phone,
                fee_json=json.dumps(fee_data, ensure_ascii=False),
                uploaded_at=datetime.utcnow(),
            )
            db.add(entry)
            count += 1

        db.commit()
        wb.close()
        return count
    except Exception as e:
        logger.warning("엑셀 파싱 실패: %s", e)
        db.rollback()
        return 0


@router.get("/health")
def health():
    return {"ok": True}


@router.post("/upload")
async def upload_fee_excel(
    request: Request,
    filename: str = Query(default="fee.xlsx"),
    _=Depends(_verify_api_key),
    db: Session = Depends(get_db),
):
    """ERP 수집기 → 관리비 엑셀 업로드 (raw bytes, API 키 인증)"""
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="엑셀 파일(.xlsx)만 업로드 가능합니다.")

    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="파일이 비어 있습니다.")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="파일 크기 초과 (최대 50MB).")

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    year_month = timestamp[:6]
    save_path  = _save_dir() / f"fee_{timestamp}.xlsx"
    save_path.write_bytes(content)

    count = _parse_and_store(save_path, year_month, db)
    logger.info("관리비 엑셀 업로드+파싱: %s (%d bytes, %d rows)", save_path.name, len(content), count)
    return {"ok": True, "filename": save_path.name, "size": len(content), "rows": count}
