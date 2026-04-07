from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.dependencies import get_repository
from app.models.blocks import BlockDocument
from app.repositories.sqlite_blocks import SQLiteBlockRepository

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentTitleUpdate(BaseModel):
  title: str

  @field_validator("title")
  @classmethod
  def title_not_blank(cls, v: str) -> str:
    stripped = v.strip()
    return stripped if stripped else "새 문서"


@router.get("")
def list_documents(repo: SQLiteBlockRepository = Depends(get_repository)) -> list[dict[str, str]]:
  """Return all available block documents."""
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
def create_document(repo: SQLiteBlockRepository = Depends(get_repository)) -> dict[str, str]:
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
  type: Literal["text", "image", "container"]
  parent_block_id: str | None = None


@router.post("/{document_id}/blocks", status_code=201)
def create_block(
  document_id: str,
  body: BlockCreate,
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> dict:
  """Append a new block to a document."""
  result = repo.create_block(document_id, body.type, body.parent_block_id)
  if result is None:
    raise HTTPException(status_code=404, detail="Document not found")
  return result


@router.delete("/{document_id}", status_code=204)
def delete_document(
  document_id: str,
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> None:
  """Delete a document and all its blocks."""
  if not repo.delete_document(document_id):
    raise HTTPException(status_code=404, detail="Document not found")
