"""파일 메타데이터 저장소.

파일 업로드·다운로드·삭제에 필요한 메타데이터를 SQLite에 저장·조회합니다.
실제 파일 바이트 처리는 app.services.file 에서 담당합니다.

참고:
  - SQLAlchemy 2.x Mapped Column API:
    https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.orm import FileRow


class SQLiteFileRepository:
  """FileRow 엔티티에 대한 CRUD 저장소."""

  def __init__(self, session: Session) -> None:
    self._session = session

  def create_file(
    self,
    *,
    original_filename: str,
    stored_filename: str,
    mime_type: str,
    size_bytes: int,
  ) -> FileRow:
    """파일 메타데이터를 DB에 저장하고 생성된 FileRow를 반환합니다.

    Args:
      original_filename: sanitize 완료된 원본 파일명.
      stored_filename: 디스크에 저장된 UUID 기반 파일명.
      mime_type: 업로드 시 전달된 MIME type.
      size_bytes: 파일 크기 (bytes).

    Returns:
      INSERT 후 refresh된 FileRow 인스턴스.
    """
    row = FileRow(
      id=uuid.uuid4().hex,
      original_filename=original_filename,
      stored_filename=stored_filename,
      mime_type=mime_type,
      size_bytes=size_bytes,
      created_at=datetime.now(timezone.utc).isoformat(),
    )
    self._session.add(row)
    self._session.commit()
    self._session.refresh(row)
    return row

  def get_file(self, file_id: str) -> FileRow | None:
    """file_id로 파일 메타데이터를 조회합니다.

    Returns:
      FileRow 인스턴스, 없으면 None.
    """
    return self._session.get(FileRow, file_id)

  def list_files(self) -> list[FileRow]:
    """모든 파일 메타데이터를 생성 시각 역순으로 반환합니다."""
    return list(
      self._session.execute(
        select(FileRow).order_by(FileRow.created_at.desc())
      ).scalars().all()
    )

  def delete_file(self, file_id: str) -> FileRow | None:
    """파일 메타데이터를 DB에서 삭제하고 삭제된 row를 반환합니다.

    반환된 row의 stored_filename으로 호출 측에서 디스크 파일을 제거해야 합니다.

    Returns:
      삭제된 FileRow (디스크 파일 삭제 정보 제공용), 없으면 None.
    """
    row = self._session.get(FileRow, file_id)
    if row is None:
      return None
    self._session.delete(row)
    self._session.commit()
    return row
