"""Shared pytest fixtures."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.orm import Base
from app.repositories.sqlite_blocks import SQLiteBlockRepository


@pytest.fixture()
def engine():
  """In-memory SQLite engine, fresh per test.

  StaticPool ensures all sessions share a single connection so that tables
  created by create_all() are visible to subsequent sessions.
  """
  eng = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
  )
  Base.metadata.create_all(eng)
  return eng


@pytest.fixture()
def session(engine):
  with Session(engine) as s:
    yield s


@pytest.fixture()
def repo(session):
  return SQLiteBlockRepository(session)


@pytest.fixture()
def client(engine):
  """TestClient with in-memory DB injected via dependency override."""
  from main import app
  from app.dependencies import get_repository

  def _override():
    with Session(engine) as s:
      yield SQLiteBlockRepository(s)

  app.dependency_overrides[get_repository] = _override
  with TestClient(app) as c:
    yield c
  app.dependency_overrides.clear()
