"""Notion Export HTML Import API 라우터.

Notion에서 export한 HTML 파일(단일 .html 또는 .zip 아카이브)을 업로드하면
프로젝트 페이지 구조로 자동 변환합니다.

엔드포인트:
  POST /api/import/notion — Notion HTML/ZIP 파일 업로드 및 변환

Ref:
  - Notion Export 포맷: https://www.notion.so/help/export-your-content
  - FastAPI File Upload: https://fastapi.tiangolo.com/tutorial/request-files/
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.auth.dependencies import require_admin
from app.dependencies import get_repository
from app.repositories.sqlite_blocks import SQLiteBlockRepository
from app.services.image import process_image
from app.services.notion_import import (
  ImportResult,
  extract_and_parse_zip,
  parse_single_html,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/import", tags=["import"])

# 업로드 크기 제한: 500 MB (Notion export ZIP은 대용량일 수 있음)
MAX_IMPORT_BYTES = 500 * 1024 * 1024

# 청크 단위 읽기 크기
CHUNK_SIZE = 64 * 1024


# ── 응답 모델 ────────────────────────────────────────────────────────────────────

class ImportResponse(BaseModel):
  """Import 완료 응답 스키마."""

  document_id: str
  title: str
  total_pages: int
  report: dict[str, Any]


# ── Import 엔드포인트 ────────────────────────────────────────────────────────────

@router.post("/notion", status_code=201, response_model=ImportResponse)
async def import_notion(
  _admin: str = Depends(require_admin),
  file: UploadFile = File(...),
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> ImportResponse:
  """Notion export HTML/ZIP 파일을 프로젝트 페이지로 변환 import합니다.

  지원 파일 형식:
    - .html — 단일 Notion 페이지
    - .zip  — Notion export 아카이브 (다중 페이지/이미지 포함)

  Returns:
    생성된 루트 문서 ID, 제목, 페이지 수, 변환 리포트.

  Raises:
    HTTPException 415: 지원하지 않는 파일 형식
    HTTPException 413: 파일 크기 초과
    HTTPException 422: 파싱 실패
  """
  filename = file.filename or ""
  lower_name = filename.lower()

  if not (lower_name.endswith(".html") or lower_name.endswith(".htm") or lower_name.endswith(".zip")):
    raise HTTPException(
      status_code=415,
      detail="지원하지 않는 파일 형식입니다. .html 또는 .zip 파일을 업로드해주세요.",
    )

  # 청크 단위로 읽어 메모리 제한 방어
  chunks: list[bytes] = []
  total_size = 0
  while True:
    chunk = await file.read(CHUNK_SIZE)
    if not chunk:
      break
    total_size += len(chunk)
    if total_size > MAX_IMPORT_BYTES:
      raise HTTPException(
        status_code=413,
        detail=f"파일 크기가 {MAX_IMPORT_BYTES // (1024 * 1024)} MB를 초과합니다.",
      )
    chunks.append(chunk)

  data = b"".join(chunks)
  if not data:
    raise HTTPException(status_code=422, detail="빈 파일입니다.")

  # 파싱
  try:
    if lower_name.endswith(".zip"):
      result = extract_and_parse_zip(data)
    else:
      result = parse_single_html(data)
  except ValueError as exc:
    raise HTTPException(status_code=422, detail=str(exc))
  except Exception as exc:
    logger.error("Notion import 파싱 실패: %s", exc)
    raise HTTPException(status_code=422, detail=f"파싱 중 오류가 발생했습니다: {exc}")

  if not result.pages:
    raise HTTPException(status_code=422, detail="변환할 페이지가 없습니다.")

  # DB에 문서/블록 생성
  try:
    root_doc = _persist_import(result, repo)
  except Exception as exc:
    logger.error("Notion import 저장 실패: %s", exc)
    raise HTTPException(status_code=500, detail=f"저장 중 오류가 발생했습니다: {exc}")

  return ImportResponse(
    document_id=root_doc["id"],
    title=root_doc["title"],
    total_pages=len(result.pages),
    report=result.report.to_dict(),
  )


# ── 영속화 로직 ─────────────────────────────────────────────────────────────────

def _persist_import(
  result: ImportResult,
  repo: SQLiteBlockRepository,
) -> dict[str, Any]:
  """파싱된 Import 결과를 DB에 문서/블록으로 저장합니다.

  페이지 계층 구조:
    - 최상위 페이지 → 루트 문서
    - 하위 페이지 → 루트 문서의 하위 PageBlock으로 연결

  이미지 처리:
    - ZIP 내 이미지 파일은 process_image()를 통해 저장
    - 블록의 url 필드를 실제 저장 경로로 갱신
  """
  from app.models.orm import BlockRow, DocumentRow

  session = repo._session

  # 페이지 경로 → 생성된 document_id 매핑
  path_to_doc_id: dict[str, str] = {}

  # 1단계: 루트 문서 결정 — 첫 번째 페이지 또는 단일 페이지
  first_page = result.pages[0]

  # 단일 페이지인 경우 바로 루트 문서로 생성
  if len(result.pages) == 1:
    root_id = str(uuid.uuid4())
    session.add(DocumentRow(
      id=root_id,
      title=first_page["title"],
      subtitle="",
      parent_id=None,
    ))
    session.flush()
    path_to_doc_id[first_page["path"]] = root_id

    # 이미지 URL 치환 후 블록 저장
    _upload_images_in_blocks(first_page["blocks"], result.image_mappings)
    _persist_blocks(session, root_id, first_page["blocks"])
    session.commit()

    return {"id": root_id, "title": first_page["title"]}

  # 다중 페이지: 첫 번째 페이지를 루트 문서로, 나머지를 하위로 연결
  root_id = str(uuid.uuid4())
  session.add(DocumentRow(
    id=root_id,
    title=first_page["title"],
    subtitle="",
    parent_id=None,
  ))
  session.flush()
  path_to_doc_id[first_page["path"]] = root_id

  _upload_images_in_blocks(first_page["blocks"], result.image_mappings)
  _persist_blocks(session, root_id, first_page["blocks"])

  # 2단계: 하위 페이지 생성 및 PageBlock으로 연결
  for page in result.pages[1:]:
    child_doc_id = str(uuid.uuid4())
    # 부모 문서 결정: 경로 기반 계층 탐색
    parent_doc_id = _find_parent_doc_id(page["path"], path_to_doc_id, root_id)

    session.add(DocumentRow(
      id=child_doc_id,
      title=page["title"],
      subtitle="",
      parent_id=parent_doc_id,
    ))
    session.flush()
    path_to_doc_id[page["path"]] = child_doc_id

    # 부모 문서에 PageBlock 추가
    _add_page_block(session, parent_doc_id, child_doc_id, page["title"])

    # 이미지 URL 치환 후 블록 저장
    _upload_images_in_blocks(page["blocks"], result.image_mappings)
    _persist_blocks(session, child_doc_id, page["blocks"])

  session.commit()
  return {"id": root_id, "title": first_page["title"]}


def _find_parent_doc_id(
  page_path: str,
  path_to_doc_id: dict[str, str],
  root_id: str,
) -> str:
  """페이지 경로를 기반으로 부모 문서 ID를 결정합니다.

  Notion export 디렉터리 구조에서 부모 페이지의 HTML 파일은
  자식 페이지의 디렉터리와 같은 레벨에 위치합니다.

  예시:
    Root UUID.html          ← 루트
    Root UUID/
      Child UUID.html       ← Root의 자식
      Child UUID/
        GrandChild UUID.html  ← Child의 자식
  """
  from pathlib import PurePosixPath

  parts = PurePosixPath(page_path).parts

  # 부모 디렉터리의 HTML 파일을 역순으로 탐색
  if len(parts) >= 2:
    # 부모 디렉터리 이름으로 부모 HTML 파일을 매칭
    parent_dir = str(PurePosixPath(*parts[:-1]))
    # parent_dir + ".html" 패턴으로 부모 문서 검색
    for registered_path, doc_id in path_to_doc_id.items():
      reg_stem = PurePosixPath(registered_path).stem
      if parent_dir.endswith(reg_stem):
        return doc_id
      # 부분 경로 매칭 — 디렉터리명이 HTML 파일명(확장자 제외)과 동일
      reg_parts = PurePosixPath(registered_path).parts
      if len(reg_parts) >= 1:
        parent_dir_name = parts[-2] if len(parts) >= 2 else ""
        if reg_parts[-1].replace(".html", "") == parent_dir_name:
          return doc_id

  return root_id


def _add_page_block(
  session: Any,
  parent_doc_id: str,
  child_doc_id: str,
  title: str,
) -> None:
  """부모 문서에 하위 페이지를 가리키는 PageBlock을 추가합니다."""
  from sqlalchemy import func, select

  from app.models.orm import BlockRow

  # 현재 최대 position 조회
  max_pos = session.execute(
    select(func.coalesce(func.max(BlockRow.position), 0))
    .where(
      BlockRow.document_id == parent_doc_id,
      BlockRow.parent_block_id.is_(None),
    )
  ).scalar_one()

  block_id = str(uuid.uuid4())
  content = json.dumps({
    "document_id": child_doc_id,
    "is_reference": False,
  }, ensure_ascii=False)

  session.add(BlockRow(
    id=block_id,
    document_id=parent_doc_id,
    parent_block_id=None,
    type="page",
    position=max_pos + 1,
    content_json=content,
  ))


def _persist_blocks(
  session: Any,
  document_id: str,
  blocks: list[dict[str, Any]],
  parent_block_id: str | None = None,
) -> None:
  """블록 리스트를 DB에 저장합니다.

  컨테이너 블록(toggle, quote, callout)의 children은 재귀적으로 처리됩니다.
  """
  from app.models.orm import BlockRow

  for position, block in enumerate(blocks, start=1):
    block_id = block.get("id", str(uuid.uuid4()))
    block_type = block["type"]

    # children은 content_json에서 제외 (별도 BlockRow로 저장)
    children = block.pop("children", None)

    # content_json 구성: id, type은 BlockRow 컬럼이므로 제외
    content = {k: v for k, v in block.items() if k not in ("id", "type")}
    content_json = json.dumps(content, ensure_ascii=False)

    session.add(BlockRow(
      id=block_id,
      document_id=document_id,
      parent_block_id=parent_block_id,
      type=block_type,
      position=position,
      content_json=content_json,
    ))

    # 컨테이너 블록의 자식 재귀 저장
    if children:
      _persist_blocks(session, document_id, children, parent_block_id=block_id)


def _upload_images_in_blocks(
  blocks: list[dict[str, Any]],
  image_mappings: dict[str, bytes],
) -> None:
  """블록 내 이미지 URL을 실제 업로드된 경로로 치환합니다.

  ZIP 내부 상대 경로로 참조된 이미지를 process_image()를 통해
  서버에 저장하고, 블록의 url 필드를 갱신합니다.
  """
  for block in blocks:
    if block.get("type") == "image":
      url = block.get("url", "")
      if url in image_mappings:
        try:
          img_data = image_mappings[url]
          result = process_image(img_data)
          block["url"] = result["url"]
        except Exception as exc:
          logger.warning("이미지 업로드 실패: %s — %s", url, exc)
          block["url"] = ""

    # 재귀: 컨테이너 블록의 children
    children = block.get("children")
    if children:
      _upload_images_in_blocks(children, image_mappings)
