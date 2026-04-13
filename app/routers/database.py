from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.auth.dependencies import require_admin
from app.dependencies import get_repository
from app.repositories.sqlite_blocks import SQLiteBlockRepository
from app.routers.blocks import DatabaseBlockPatch

router = APIRouter(prefix="/api/database", tags=["database"])


# ── Database block meta patch ─────────────────────────────────────────────────

@router.patch("/blocks/{block_id}")
def patch_database_block(
  block_id: str,
  body: DatabaseBlockPatch,
  _admin: str = Depends(require_admin),
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> dict[str, str]:
  """Update title or color of a database block."""
  patch_data = body.model_dump(exclude_unset=True, exclude_none=True)
  if not patch_data:
    raise HTTPException(status_code=422, detail="No fields to update")
  if not repo.update_block(block_id, patch_data):
    raise HTTPException(status_code=404, detail="Database block not found")
  return {"id": block_id}


# ── Schema management ──────────────────────────────────────────────────────────

class ColumnCreate(BaseModel):
  name: str
  type: Literal["text", "number", "select", "checkbox"] = "text"
  options: list[str] = Field(default_factory=list)


class ColumnUpdate(BaseModel):
  name: str | None = None
  type: Literal["text", "number", "select", "checkbox"] | None = None
  options: list[str] | None = None


@router.post("/blocks/{block_id}/schema/columns", status_code=201)
def add_column(
  block_id: str,
  body: ColumnCreate,
  _admin: str = Depends(require_admin),
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> dict:
  """Add a new column to a database block's schema."""
  col_id = str(uuid.uuid4())
  column: dict[str, Any] = {
    "id": col_id,
    "name": body.name,
    "type": body.type,
    "options": body.options,
  }
  if not repo.add_db_column(block_id, column):
    raise HTTPException(status_code=404, detail="Database block not found")
  return column


@router.patch("/blocks/{block_id}/schema/columns/{col_id}")
def update_column(
  block_id: str,
  col_id: str,
  body: ColumnUpdate,
  _admin: str = Depends(require_admin),
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> dict[str, str]:
  """Rename or change a column's type/options."""
  patch = body.model_dump(exclude_unset=True, exclude_none=True)
  if not patch:
    raise HTTPException(status_code=422, detail="No fields to update")
  if not repo.update_db_column(block_id, col_id, patch):
    raise HTTPException(status_code=404, detail="Database block or column not found")
  return {"block_id": block_id, "col_id": col_id}


@router.delete("/blocks/{block_id}/schema/columns/{col_id}", status_code=204)
def remove_column(
  block_id: str,
  col_id: str,
  _admin: str = Depends(require_admin),
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> Response:
  """Remove a column from the database schema (and wipes its values from all rows)."""
  if not repo.remove_db_column(block_id, col_id):
    raise HTTPException(status_code=404, detail="Database block or column not found")
  return Response(status_code=204)


# ── Row properties ─────────────────────────────────────────────────────────────

class PropertiesUpdate(BaseModel):
  properties: dict[str, Any]


@router.patch("/blocks/{block_id}/properties")
def update_properties(
  block_id: str,
  body: PropertiesUpdate,
  _admin: str = Depends(require_admin),
  repo: SQLiteBlockRepository = Depends(get_repository),
) -> dict[str, str]:
  """Replace all property values on a db_row block."""
  if not repo.update_db_row_properties(block_id, body.properties):
    raise HTTPException(status_code=404, detail="db_row block not found")
  return {"block_id": block_id}
