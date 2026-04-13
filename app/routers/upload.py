from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import UnidentifiedImageError

from app.auth.dependencies import require_admin
from app.services.image import process_image

ALLOWED_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
CHUNK_SIZE = 64 * 1024  # 64 KB

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("")
async def upload_image(
  _admin: str = Depends(require_admin),
  file: UploadFile = File(...),
) -> dict[str, str]:
  """이미지를 업로드하고 압축·썸네일 생성 후 URL을 반환합니다."""
  if file.content_type not in ALLOWED_MIME:
    raise HTTPException(status_code=415, detail="지원하지 않는 이미지 형식입니다.")

  chunks: list[bytes] = []
  total = 0
  while chunk := await file.read(CHUNK_SIZE):
    total += len(chunk)
    if total > MAX_BYTES:
      raise HTTPException(status_code=413, detail="파일 크기가 10 MB를 초과합니다.")
    chunks.append(chunk)
  data = b"".join(chunks)

  try:
    return process_image(data)
  except UnidentifiedImageError:
    raise HTTPException(status_code=415, detail="이미지를 인식할 수 없습니다.")
  except Exception:
    raise HTTPException(status_code=422, detail="이미지를 처리할 수 없습니다.")
