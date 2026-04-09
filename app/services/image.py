from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image

UPLOADS_DIR = Path(__file__).resolve().parents[2] / "static" / "uploads"
THUMBNAILS_DIR = UPLOADS_DIR / "thumbnails"

MAX_DIMENSION = 1920
THUMBNAIL_SIZE = (320, 320)
COMPRESS_QUALITY = 85


def _ensure_dirs() -> None:
  UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
  THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)


def _downscale(img: Image.Image, max_dim: int) -> Image.Image:
  """원본 비율을 유지하며 max_dim 이내로 축소. 이미 작으면 그대로 반환."""
  w, h = img.size
  if w <= max_dim and h <= max_dim:
    return img
  scale = max_dim / max(w, h)
  return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def process_image(data: bytes) -> dict[str, str]:
  """
  이미지를 압축하고 썸네일을 생성한 뒤 경로를 반환합니다.

  Returns:
    {
      "url": "/static/uploads/<name>.webp",
      "thumbnail_url": "/static/uploads/thumbnails/<name>.webp",
    }
  """
  _ensure_dirs()

  name = uuid.uuid4().hex
  img = Image.open(__import__("io").BytesIO(data)).convert("RGB")

  compressed = _downscale(img, MAX_DIMENSION)
  compressed_path = UPLOADS_DIR / f"{name}.webp"
  compressed.save(compressed_path, format="WEBP", quality=COMPRESS_QUALITY, method=6)

  thumb = img.copy()
  thumb.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
  thumb_path = THUMBNAILS_DIR / f"{name}.webp"
  thumb.save(thumb_path, format="WEBP", quality=COMPRESS_QUALITY, method=6)

  return {
    "url": f"/static/uploads/{name}.webp",
    "thumbnail_url": f"/static/uploads/thumbnails/{name}.webp",
  }
