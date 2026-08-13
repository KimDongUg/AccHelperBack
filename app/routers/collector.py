import json
import logging
import re
from pathlib import Path

import openpyxl
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.database import get_db
from app.models.company import Company
from app.models.fee_data import FeeEntry
from app.utils import now_kst

logger = logging.getLogger("acchelper")
router = APIRouter(prefix="/api/collector", tags=["collector"])

_PERSISTENT = Path("/data/uploads/collector")
_FALLBACK   = DATA_DIR / "collector"

_FIXED_KEYS = {"동", "호", "휴대폰", "name", "이름"}

# 수집기가 내보내는 파일명 "관리비데이터_YYYYMM.xlsx"에서 청구 년월 추출
_FILENAME_YM_RE = re.compile(r"_(\d{6})\.xlsx?$", re.IGNORECASE)


def _save_dir() -> Path:
    for p in (_PERSISTENT, _FALLBACK, Path("/tmp/collector")):
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            continue
    return Path("/tmp")


def _get_company_by_api_key(authorization: str = Header(...), db: Session = Depends(get_db)) -> Company:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="API 키 인증 실패")
    api_key = authorization[7:]
    company = (
        db.query(Company)
        .filter(Company.collector_api_key == api_key, Company.deleted_at == None)
        .first()
    )
    if not company:
        raise HTTPException(status_code=401, detail="API 키 인증 실패")
    return company


def _store_rows(rows: list[dict], year_month: str, company_id: int, db: Session) -> int:
    """세대별 dict 목록(동/호/이름/휴대폰/항목_.../검침_... 등)을 FeeEntry로 저장.
    엑셀 업로드(_parse_and_store)와 JSON 직접 업로드(upload_fee_json) 공용 로직."""
    # 이번 업로드에 휴대폰 정보가 비어있는 세대는 직전에 저장된 휴대폰번호를 유지
    # (업로드 데이터에 따라 휴대폰 컬럼이 통째로 빠지는 경우, OTP 발송이 막히는 것을 방지)
    known_phones: dict[tuple[str, str], str] = {}
    for d, h, p in (
        db.query(FeeEntry.dong, FeeEntry.ho, FeeEntry.phone)
        .filter(FeeEntry.company_id == company_id, FeeEntry.phone != "")
        .order_by(FeeEntry.uploaded_at.asc())
    ):
        known_phones[(d, h)] = p

    db.query(FeeEntry).filter(
        FeeEntry.year_month == year_month, FeeEntry.company_id == company_id
    ).delete()

    count = 0
    for raw in rows:
        rd = {k: ("" if v is None else str(v).strip()) for k, v in raw.items()}

        dong  = rd.get("동", "")
        ho    = rd.get("호", "")
        name  = rd.get("name", rd.get("이름", ""))
        phone = rd.get("휴대폰", "").replace("-", "").replace(" ", "")

        if not dong or not ho:
            continue

        if not phone:
            phone = known_phones.get((dong, ho), "")

        fee_data = {k: v for k, v in rd.items() if k not in _FIXED_KEYS and v}
        entry = FeeEntry(
            company_id=company_id,
            year_month=year_month,
            dong=dong, ho=ho,
            name=name, phone=phone,
            fee_json=json.dumps(fee_data, ensure_ascii=False),
            uploaded_at=now_kst(),
        )
        db.add(entry)
        count += 1

    db.commit()
    return count


def _parse_and_store(file_path: Path, year_month: str, company_id: int, db: Session):
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            return 0

        headers = [str(v).strip() if v is not None else "" for v in rows[0]]
        dict_rows = []
        for row in rows[1:]:
            if not any(v for v in row):
                continue
            dict_rows.append({headers[i]: v for i, v in enumerate(row)})

        count = _store_rows(dict_rows, year_month, company_id, db)
        wb.close()
        return count
    except Exception as e:
        logger.warning("엑셀 파싱 실패: %s", e)
        db.rollback()
        return 0


class UploadJsonRequest(BaseModel):
    year_month: str
    rows: list[dict]


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/verify")
def verify_key(company: Company = Depends(_get_company_by_api_key)):
    """확장프로그램 설정 화면에서 API 키가 유효한지 즉시 확인하는 용도."""
    return {"ok": True, "company_id": company.company_id, "company_name": company.company_name}


@router.post("/upload-json")
def upload_fee_json(
    payload: UploadJsonRequest,
    company: Company = Depends(_get_company_by_api_key),
    db: Session = Depends(get_db),
):
    """확장프로그램 → 관리비 데이터 직접 업로드 (xlsx 변환 없이 JSON 그대로)"""
    if not payload.rows:
        raise HTTPException(status_code=400, detail="데이터가 비어 있습니다.")
    if not re.fullmatch(r"\d{6}", payload.year_month or ""):
        raise HTTPException(status_code=400, detail="year_month은 YYYYMM 형식이어야 합니다.")

    count = _store_rows(payload.rows, payload.year_month, company.company_id, db)
    logger.info(
        "관리비 JSON 업로드: company_id=%d year_month=%s (%d rows)",
        company.company_id, payload.year_month, count,
    )
    return {"ok": True, "year_month": payload.year_month, "rows": count}


@router.post("/upload")
async def upload_fee_excel(
    request: Request,
    filename: str = Query(default="fee.xlsx"),
    company: Company = Depends(_get_company_by_api_key),
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

    timestamp = now_kst().strftime("%Y%m%d_%H%M%S")

    # 청구 년월은 수집기가 ERP 화면에서 읽어 파일명에 담아 보낸 값을 사용한다
    # (업로드 시각의 달이 아니라, 데이터가 실제로 속한 청구월이어야 함)
    ym_match   = _FILENAME_YM_RE.search(filename)
    year_month = ym_match.group(1) if ym_match else timestamp[:6]
    save_path  = _save_dir() / f"fee_{timestamp}.xlsx"
    save_path.write_bytes(content)

    count = _parse_and_store(save_path, year_month, company.company_id, db)
    logger.info(
        "관리비 엑셀 업로드+파싱: company_id=%d %s (%d bytes, %d rows)",
        company.company_id, save_path.name, len(content), count,
    )
    return {"ok": True, "filename": save_path.name, "size": len(content), "rows": count}
