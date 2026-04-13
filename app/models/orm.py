from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
  pass


class DocumentRow(Base):
  __tablename__ = "documents"

  id: Mapped[str] = mapped_column(String, primary_key=True)
  title: Mapped[str] = mapped_column(String, nullable=False)
  subtitle: Mapped[str] = mapped_column(String, nullable=False, default="")
  parent_id: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
  # db_row 블록이 생성한 페이지임을 표시 — 해당 db_row 블록의 id
  source_block_id: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

  blocks: Mapped[list[BlockRow]] = relationship(
    back_populates="document",
    cascade="all, delete-orphan",
    foreign_keys="[BlockRow.document_id]",
  )


class BlockRow(Base):
  __tablename__ = "blocks"

  id: Mapped[str] = mapped_column(String, primary_key=True)
  document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False)
  parent_block_id: Mapped[str | None] = mapped_column(String, nullable=True)
  type: Mapped[str] = mapped_column(String, nullable=False)
  position: Mapped[int] = mapped_column(Integer, nullable=False)
  content_json: Mapped[str] = mapped_column(Text, nullable=False)

  document: Mapped[DocumentRow] = relationship(
    back_populates="blocks",
    foreign_keys=[document_id],
  )

  __table_args__ = (
    Index("idx_blocks_document_parent_pos", "document_id", "parent_block_id", "position"),
  )


class FileRow(Base):
  """업로드된 파일의 메타데이터를 저장하는 테이블.

  실제 파일 바이트는 static/files/<stored_filename> 경로에 저장됩니다.
  stored_filename은 UUID 기반이므로 경로 순회(path traversal) 위험이 없습니다.
  """

  __tablename__ = "files"

  id: Mapped[str] = mapped_column(String, primary_key=True)
  # 클라이언트가 전송한 원본 파일명 (정규화·sanitize 완료)
  original_filename: Mapped[str] = mapped_column(String, nullable=False)
  # 디스크에 저장된 UUID 기반 파일명 (확장자 없음)
  stored_filename: Mapped[str] = mapped_column(String, nullable=False)
  mime_type: Mapped[str] = mapped_column(String, nullable=False)
  size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
  # ISO-8601 UTC 타임스탬프
  created_at: Mapped[str] = mapped_column(String, nullable=False)

  __table_args__ = (
    UniqueConstraint("stored_filename", name="uq_files_stored_filename"),
  )
