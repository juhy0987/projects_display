from __future__ import annotations

import functools
from collections.abc import Generator
from pathlib import Path

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.models.orm import Base

_BASE_DIR = Path(__file__).resolve().parent.parent
_DB_FILE = _BASE_DIR / "data" / "blocks.sqlite3"


def _migrate(engine: Engine) -> None:
  """Run additive schema migrations that create_all cannot handle."""
  with engine.connect() as conn:
    try:
      conn.execute(text("ALTER TABLE documents ADD COLUMN parent_id TEXT"))
      conn.commit()
    except OperationalError as e:
      # SQLite raises OperationalError("duplicate column name") when the column
      # already exists — that is the only expected error here.
      if "duplicate column name" not in str(e).lower():
        raise


@functools.cache
def _get_engine() -> Engine:
  """Create the engine, initialize schema, and seed once per process."""
  _DB_FILE.parent.mkdir(parents=True, exist_ok=True)
  engine = create_engine(
    f"sqlite:///{_DB_FILE}",
    connect_args={"check_same_thread": False},
  )
  Base.metadata.create_all(engine)
  _migrate(engine)
  from app.repositories.sqlite_blocks import SQLiteBlockRepository
  with Session(engine) as session:
    SQLiteBlockRepository(session)._seed_if_empty()
  return engine


def get_session() -> Generator[Session, None, None]:
  """Yield a SQLAlchemy session for the duration of a single request."""
  with Session(_get_engine()) as session:
    yield session


def get_repository(session: Session = Depends(get_session)):
  from app.repositories.sqlite_blocks import SQLiteBlockRepository
  return SQLiteBlockRepository(session)
