from __future__ import annotations

from pathlib import Path

from app.repositories.sqlite_blocks import SQLiteBlockRepository

_BASE_DIR = Path(__file__).resolve().parent.parent
_DB_FILE = _BASE_DIR / "data" / "blocks.sqlite3"

_repository = SQLiteBlockRepository(_DB_FILE)
_repository.initialize()


def get_repository() -> SQLiteBlockRepository:
  return _repository
