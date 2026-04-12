from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.dependencies import get_repository
from app.models.blocks import BlockDocument
from app.repositories.sqlite_blocks import SQLiteBlockRepository

router = APIRouter(prefix="/api/documents", tags=["documents"])


MAX_TITLE_LENGTH = 100


class DocumentTitleUpdate(BaseModel):
  title: str

  @field_validator("title")
  @classmethod
  def validate_title(cls, v: str) -> str:
    stripped = v.strip()
    if not stripped:
      return "새 문서"
    if len(stripped) > MAX_TITLE_LENGTH:
      raise ValueError(f"제목은 {MAX_TITLE_LENGTH}자를 초과할 수 없습니다.")
    return stripped


@router.get("")
def list_documents(repo: SQLiteBlockRepository = Depends(get_repository)) -> list[dict]:
  """Return all available block documents as a parent-child tree."""
  return repo.list_documents()


@router.get("/{document_id}", response_model=BlockDocument)
def get_document(
  document_id: str,
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> BlockDocument:
  """Return one block document by id."""
  document = repo.get_document(document_id)
  if document is None:
    raise HTTPException(status_code=404, detail="Document not found")
  return document


@router.post("", status_code=201)
def create_document(repo: SQLiteBlockRepository = Depends(get_repository)) -> dict:
  """Create a new empty document and return its info."""
  return repo.create_document()


@router.patch("/{document_id}")
def update_document_title(
  document_id: str,
  body: DocumentTitleUpdate,
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> dict[str, str]:
  """Update the title of an existing document."""
  if not repo.update_document_title(document_id, body.title):
    raise HTTPException(status_code=404, detail="Document not found")
  return {"id": document_id, "title": body.title}


class BlockCreate(BaseModel):
  type: Literal["text", "image", "toggle", "quote", "code", "callout", "divider", "url_embed", "page", "database", "db_row"]
  parent_block_id: str | None = None
  # Only used when type="page": link to an existing document instead of creating a new one
  target_document_id: str | None = None


@router.post("/{document_id}/blocks", status_code=201)
def create_block(
  document_id: str,
  body: BlockCreate,
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> dict:
  """Append a new block to a document.

  For ``type=page`` a new child document is automatically created unless
  ``target_document_id`` is provided, in which case the block links to the
  existing document.  A newly created child document is returned inside the
  ``child_document`` field of the response.
  """
  if body.target_document_id is not None and body.type != "page":
    raise HTTPException(status_code=422, detail="target_document_id is only valid for page blocks")
  if not repo.document_exists(document_id):
    raise HTTPException(status_code=404, detail="Document not found")
  if body.type == "page" and body.target_document_id is not None:
    if not repo.document_exists(body.target_document_id):
      raise HTTPException(status_code=404, detail="Target document not found")
  result = repo.create_block(document_id, body.type, body.parent_block_id, body.target_document_id)
  if result is None:
    raise HTTPException(status_code=422, detail="Parent block not found")
  return result


@router.delete("/{document_id}", status_code=204)
def delete_document(
  document_id: str,
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> None:
  """Delete a document and all its blocks."""
  if not repo.delete_document(document_id):
    raise HTTPException(status_code=404, detail="Document not found")
