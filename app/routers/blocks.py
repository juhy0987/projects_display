from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.dependencies import get_repository
from app.repositories.sqlite_blocks import SQLiteBlockRepository

router = APIRouter(prefix="/api/blocks", tags=["blocks"])


class BlockPatch(BaseModel):
  # text / heading
  text: str | None = None
  level: Literal[1, 2, 3] | None = None
  formatted_text: str | None = None  # HTML string with inline formatting
  # image
  url: str | None = None
  caption: str | None = None
  # toggle
  is_open: bool | None = None
  # code
  code: str | None = None
  language: str | None = None
  # callout (color은 callout 지원 색상만 허용)
  emoji: str | None = None
  color: Literal["yellow", "blue", "green", "red", "gray"] | None = None


class DatabaseBlockPatch(BaseModel):
  title: str | None = None
  color: Literal["default", "gray", "brown", "orange", "yellow", "green", "blue", "purple", "pink", "red"] | None = None


class BlockPositionPatch(BaseModel):
  before_block_id: str | None = None


class BlockTypeChange(BaseModel):
  type: Literal["text", "image", "toggle", "quote", "code", "callout", "divider", "url_embed"]


@router.patch("/{block_id}")
def patch_block(
  block_id: str,
  body: BlockPatch,
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> dict[str, str]:
  """Update editable content fields of a block."""
  patch_data = body.model_dump(exclude_unset=True, exclude_none=True)
  if not patch_data:
    raise HTTPException(status_code=422, detail="No fields to update")
  if not repo.update_block(block_id, patch_data):
    raise HTTPException(status_code=404, detail="Block not found")
  return {"id": block_id}


@router.patch("/{block_id}/position")
def move_block(
  block_id: str,
  body: BlockPositionPatch,
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> dict[str, str]:
  """Reorder a block among its siblings."""
  result = repo.move_block(block_id, body.before_block_id)
  if result is None:
    raise HTTPException(status_code=404, detail="Block not found")
  if result is False:
    raise HTTPException(status_code=422, detail="Invalid before_block_id")
  return {"id": block_id}


@router.patch("/{block_id}/type")
def change_block_type(
  block_id: str,
  body: BlockTypeChange,
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> dict[str, str]:
  """Change a block's type and reset its content to defaults."""
  if not repo.change_block_type(block_id, body.type):
    raise HTTPException(status_code=404, detail="Block not found")
  return {"id": block_id}


@router.delete("/{block_id}", status_code=204)
def delete_block(
  block_id: str,
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> Response:
  """Delete a block and all its descendants."""
  if not repo.delete_block(block_id):
    raise HTTPException(status_code=404, detail="Block not found")
  return Response(status_code=204)
