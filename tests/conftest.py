"""Shared pytest fixtures."""
from __future__ import annotations

import os

# 테스트 환경에서 관리자 자격 증명을 고정한다.
# config.py가 모듈 임포트 시 환경변수를 읽으므로, 최상위에서 설정해야 한다.
os.environ.setdefault("ADMIN_PASSWORD", "admin1234")

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
  """TestClient with in-memory DB and admin session pre-authenticated.

  기존 테스트는 모두 관리자 권한이 필요한 쓰기 작업을 포함하므로,
  테스트 시작 시 자동으로 로그인하여 세션 쿠키를 설정한다.
  """
  from main import app
  from app.dependencies import get_repository

  def _override():
    with Session(engine) as s:
      yield SQLiteBlockRepository(s)

  app.dependency_overrides[get_repository] = _override
  with TestClient(app) as c:
    # 관리자 로그인 — 세션 쿠키가 TestClient에 자동 저장됨
    login_res = c.post("/api/auth/login", json={"username": "admin", "password": "admin1234"})
    assert login_res.status_code == 200, (
      f"Admin auto-login failed: status={login_res.status_code}, body={login_res.text}"
    )
    yield c
  app.dependency_overrides.clear()
