from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile

from app.services.image import process_image

ALLOWED_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("")
async def upload_image(file: UploadFile) -> dict[str, str]:
  """이미지를 업로드하고 압축·썸네일 생성 후 URL을 반환합니다."""
  if file.content_type not in ALLOWED_MIME:
    raise HTTPException(status_code=415, detail="지원하지 않는 이미지 형식입니다.")

  data = await file.read()
  if len(data) > MAX_BYTES:
    raise HTTPException(status_code=413, detail="파일 크기가 10 MB를 초과합니다.")

  return process_image(data)
