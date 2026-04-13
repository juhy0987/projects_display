"""URL 임베드 메타데이터 조회 라우터.

엔드포인트:
  POST /api/url-embed/fetch
    — URL을 받아 Open Graph / Twitter Card / HTML 메타데이터를 수집하고,
      선택적으로 해당 블록의 content_json을 즉시 업데이트한다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.auth.dependencies import require_admin
from app.dependencies import get_repository
from app.repositories.sqlite_blocks import SQLiteBlockRepository
from app.services.url_embed import UrlEmbedMetadata, fetch_url_metadata

router = APIRouter(prefix="/api/url-embed", tags=["url-embed"])

# URL 최대 길이 — 실용적 상한값 (RFC 7230 권고 수준)
_MAX_URL_LENGTH = 2048


class UrlFetchRequest(BaseModel):
  """POST /api/url-embed/fetch 요청 바디."""

  url: str
  # 블록 ID를 함께 전달하면 fetch 결과가 해당 블록 content_json에 즉시 반영됨
  block_id: str | None = None

  @field_validator("url")
  @classmethod
  def validate_url(cls, v: str) -> str:
    v = v.strip()
    if not v:
      raise ValueError("URL은 비어 있을 수 없습니다.")
    if len(v) > _MAX_URL_LENGTH:
      raise ValueError(f"URL은 {_MAX_URL_LENGTH}자를 초과할 수 없습니다.")
    if not v.startswith(("http://", "https://")):
      raise ValueError("http:// 또는 https://로 시작하는 URL만 허용됩니다.")
    return v


class UrlFetchResponse(BaseModel):
  """POST /api/url-embed/fetch 응답 바디."""

  url: str
  title: str
  description: str
  logo: str
  provider: str
  fetched_at: str
  status: str   # "success" | "error"
  error: str    # status="error"일 때 사람이 읽을 수 있는 메시지


@router.post("/fetch", response_model=UrlFetchResponse)
def fetch_embed(
  body: UrlFetchRequest,
  _admin: str = Depends(require_admin),
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> UrlFetchResponse:
  """URL의 Open Graph / Twitter Card 메타데이터를 조회한다.

  block_id가 함께 전달되면 조회 결과를 해당 url_embed 블록에 자동으로 저장한다.
  메타데이터 수집에 실패하더라도 HTTP 200으로 응답하고 status 필드를 "error"로 설정한다.
  (클라이언트가 fallback UI를 표시하기 위해 에러 상태를 명시적으로 전달받아야 함)
  """
  meta: UrlEmbedMetadata = fetch_url_metadata(body.url)

  # 블록 ID가 주어진 경우 content_json 업데이트
  if body.block_id is not None:
    patch = {
      "url": meta.url,
      "title": meta.title,
      "description": meta.description,
      "logo": meta.logo,
      "provider": meta.provider,
      "fetched_at": meta.fetched_at,
      "status": meta.status,
    }
    updated = repo.update_block(body.block_id, patch)
    if not updated:
      raise HTTPException(status_code=404, detail="Block not found")

  return UrlFetchResponse(
    url=meta.url,
    title=meta.title,
    description=meta.description,
    logo=meta.logo,
    provider=meta.provider,
    fetched_at=meta.fetched_at,
    status=meta.status,
    error=meta.error,
  )
