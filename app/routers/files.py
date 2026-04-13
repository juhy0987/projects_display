"""범용 파일 업로드·다운로드·삭제 라우터.

엔드포인트:
  POST   /api/files              — 파일 업로드 (허용 확장자 검증, 50 MB 제한)
  GET    /api/files/{file_id}    — 파일 다운로드 (원본 파일명 Content-Disposition 보장)
  GET    /api/files              — 업로드된 파일 목록 조회
  DELETE /api/files/{file_id}    — DB 메타데이터 + 디스크 파일 삭제

보안:
  - ALLOWED_EXTENSIONS 화이트리스트 검증 (실행 파일 차단)
  - UUID 저장명으로 경로 순회 방지
  - Content-Disposition RFC 5987 인코딩으로 한글 파일명 다운로드 보장

참고:
  - FastAPI File Upload: https://fastapi.tiangolo.com/tutorial/request-files/
  - RFC 5987 (filename* 인코딩): https://datatracker.ietf.org/doc/html/rfc5987
  - Content-Disposition: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Disposition
"""
from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.dependencies import get_session
from app.repositories.file_repo import SQLiteFileRepository
from app.services.file import (
  MAX_BYTES,
  delete_stored_file,
  get_file_path,
  save_file,
  validate_extension,
)

CHUNK_SIZE = 64 * 1024  # 64 KB 단위 청크 읽기

router = APIRouter(prefix="/api/files", tags=["files"])


def _get_file_repo(session: Session = Depends(get_session)) -> SQLiteFileRepository:
  """FileRepository 의존성 — 요청마다 새 인스턴스 반환."""
  return SQLiteFileRepository(session)


class FileMetadataResponse(BaseModel):
  """업로드 결과 및 목록 조회 공통 응답 스키마."""

  id: str
  original_filename: str
  mime_type: str
  size_bytes: int
  created_at: str
  download_url: str


def _to_response(row) -> FileMetadataResponse:
  """FileRow ORM 객체를 FileMetadataResponse로 변환하는 내부 헬퍼."""
  return FileMetadataResponse(
    id=row.id,
    original_filename=row.original_filename,
    mime_type=row.mime_type,
    size_bytes=row.size_bytes,
    created_at=row.created_at,
    download_url=f"/api/files/{row.id}",
  )


@router.post("", status_code=201, response_model=FileMetadataResponse)
async def upload_file(
  _admin: str = Depends(require_admin),
  file: UploadFile = File(...),
  repo: SQLiteFileRepository = Depends(_get_file_repo),
) -> FileMetadataResponse:
  """파일을 업로드하고 메타데이터를 반환합니다.

  허용 확장자 화이트리스트를 검증한 뒤 UUID 기반 이름으로 저장합니다.

  Args:
    file: 업로드 파일 (multipart/form-data).

  Returns:
    저장된 파일의 메타데이터 (id, original_filename, download_url 포함).

  Raises:
    415: 허용되지 않는 파일 확장자.
    413: 파일 크기가 50 MB 초과.
  """
  original_name = file.filename or "unnamed"

  # 확장자 검증 — 허용 목록에 없는 형식은 415 반환
  try:
    validate_extension(original_name)
  except ValueError as exc:
    raise HTTPException(status_code=415, detail=str(exc))

  # 청크 단위 읽기 — 50 MB 초과 즉시 413 반환 (메모리 보호)
  chunks: list[bytes] = []
  total = 0
  while chunk := await file.read(CHUNK_SIZE):
    total += len(chunk)
    if total > MAX_BYTES:
      raise HTTPException(status_code=413, detail="파일 크기가 50 MB를 초과합니다.")
    chunks.append(chunk)
  data = b"".join(chunks)

  # 디스크 저장 (UUID 기반 파일명, 원본명은 sanitize)
  result = save_file(data, original_name)

  # 메타데이터를 DB에 저장
  row = repo.create_file(
    original_filename=result["sanitized_filename"],
    stored_filename=result["stored_filename"],
    mime_type=file.content_type or "application/octet-stream",
    size_bytes=result["size_bytes"],
  )
  return _to_response(row)


@router.get("", response_model=list[FileMetadataResponse])
def list_files(
  repo: SQLiteFileRepository = Depends(_get_file_repo),
) -> list[FileMetadataResponse]:
  """업로드된 파일 목록을 생성 시각 역순으로 반환합니다."""
  return [_to_response(row) for row in repo.list_files()]


@router.get("/{file_id}")
def download_file(
  file_id: str,
  repo: SQLiteFileRepository = Depends(_get_file_repo),
) -> FileResponse:
  """파일을 다운로드합니다.

  원본 파일명을 RFC 5987 형식으로 인코딩하여 Content-Disposition 헤더에 설정합니다.
  이를 통해 브라우저가 한글을 포함한 UTF-8 파일명을 올바르게 처리합니다.

  Ref: RFC 5987 — https://datatracker.ietf.org/doc/html/rfc5987#section-3.2

  Raises:
    404: file_id가 DB에 없거나 디스크 파일이 삭제된 경우.
  """
  row = repo.get_file(file_id)
  if row is None:
    raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

  try:
    path = get_file_path(row.stored_filename)
  except (FileNotFoundError, ValueError):
    # DB에는 있지만 디스크 파일이 존재하지 않는 경우 (수동 삭제 등)
    raise HTTPException(status_code=404, detail="파일이 서버에 존재하지 않습니다.")

  # RFC 5987: filename*=UTF-8''<percent-encoded>
  # percent_encode safe="" — 모든 non-ASCII 문자를 인코딩
  encoded_name = urllib.parse.quote(row.original_filename, safe="")
  content_disposition = f"attachment; filename*=UTF-8''{encoded_name}"

  return FileResponse(
    path=str(path),
    media_type=row.mime_type,
    headers={"Content-Disposition": content_disposition},
  )


@router.delete("/{file_id}", status_code=204)
def delete_file(
  file_id: str,
  _admin: str = Depends(require_admin),
  repo: SQLiteFileRepository = Depends(_get_file_repo),
) -> None:
  """파일 메타데이터(DB)와 디스크 파일을 함께 삭제합니다.

  디스크 파일이 이미 없는 경우에도 DB 삭제는 정상 처리됩니다.

  Raises:
    404: file_id가 DB에 없는 경우.
  """
  row = repo.delete_file(file_id)
  if row is None:
    raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
  # 디스크 파일 정리 — 이미 없어도 오류 없이 통과
  delete_stored_file(row.stored_filename)
