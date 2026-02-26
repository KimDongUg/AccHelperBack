from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File

from app.dependencies import require_admin
from app.services.image_upload import save_image

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("/image")
async def upload_image_endpoint(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_admin),
):
    """이미지 업로드 (관리자 인증 필요, 5MB 이하, jpg/png/gif/webp)"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일이 없습니다.")

    file_bytes = await file.read()

    try:
        filename = save_image(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Build absolute public URL
    base_url = str(request.base_url).rstrip("/")
    url = f"{base_url}/uploads/{filename}"

    return {"url": url}
