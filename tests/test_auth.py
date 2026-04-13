"""관리자 인증 및 권한 제어 테스트.

검증 시나리오:
  1. 로그인 성공/실패
  2. 로그아웃 후 세션 무효화
  3. 인증 상태 조회 (GET /api/auth/status)
  4. Viewer의 쓰기 요청 차단 (403)
  5. 관리자 인증 후 쓰기 요청 허용
  6. 세션 만료 후 쓰기 요청 차단

Ref: https://fastapi.tiangolo.com/tutorial/testing/
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.config import SESSION_COOKIE_NAME
from app.auth.session import SessionStore, session_store
from app.models.orm import Base
from app.repositories.sqlite_blocks import SQLiteBlockRepository


@pytest.fixture()
def engine():
  eng = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
  )
  Base.metadata.create_all(eng)
  return eng


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


@pytest.fixture(autouse=True)
def _clean_sessions():
  """각 테스트 전후로 세션 저장소를 초기화한다."""
  session_store._sessions.clear()
  yield
  session_store._sessions.clear()


def _login(client: TestClient, username: str = "admin", password: str = "admin1234") -> TestClient:
  """로그인 헬퍼 — 세션 쿠키를 client에 설정한다."""
  res = client.post("/api/auth/login", json={"username": username, "password": password})
  assert res.status_code == 200
  return client


# ── 로그인/로그아웃 테스트 ──────────────────────────────────────────────────

class TestLogin:
  def test_login_success(self, client: TestClient):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin1234"})
    assert res.status_code == 200
    data = res.json()
    assert data["message"] == "로그인 성공"
    assert data["username"] == "admin"
    assert SESSION_COOKIE_NAME in res.cookies

  def test_login_wrong_password(self, client: TestClient):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert res.status_code == 401
    assert "올바르지 않습니다" in res.json()["detail"]

  def test_login_wrong_username(self, client: TestClient):
    res = client.post("/api/auth/login", json={"username": "hacker", "password": "admin1234"})
    assert res.status_code == 401

  def test_login_empty_credentials(self, client: TestClient):
    res = client.post("/api/auth/login", json={"username": "", "password": ""})
    assert res.status_code == 401


# ── 로그아웃 테스트 ────────────────────────────────────────────────────────

class TestLogout:
  def test_logout_clears_session(self, client: TestClient):
    _login(client)
    # 로그아웃
    res = client.post("/api/auth/logout")
    assert res.status_code == 200
    assert res.json()["message"] == "로그아웃 완료"
    # 로그아웃 후 상태 확인
    status = client.get("/api/auth/status")
    assert status.json()["authenticated"] is False

  def test_logout_without_session(self, client: TestClient):
    """세션 없이 로그아웃해도 에러가 발생하지 않는다."""
    res = client.post("/api/auth/logout")
    assert res.status_code == 200


# ── 인증 상태 조회 테스트 ──────────────────────────────────────────────────

class TestAuthStatus:
  def test_status_unauthenticated(self, client: TestClient):
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is False
    assert data["username"] is None

  def test_status_authenticated(self, client: TestClient):
    _login(client)
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is True
    assert data["username"] == "admin"


# ── Viewer 쓰기 차단 테스트 ───────────────────────────────────────────────

class TestViewerWriteBlocked:
  """미인증 상태에서 모든 쓰기 엔드포인트가 403을 반환하는지 검증한다."""

  def test_create_document_blocked(self, client: TestClient):
    res = client.post("/api/documents")
    assert res.status_code == 403

  def test_update_title_blocked(self, client: TestClient):
    res = client.patch("/api/documents/fake-id", json={"title": "test"})
    assert res.status_code == 403

  def test_create_block_blocked(self, client: TestClient):
    res = client.post("/api/documents/fake-id/blocks", json={"type": "text"})
    assert res.status_code == 403

  def test_delete_document_blocked(self, client: TestClient):
    res = client.delete("/api/documents/fake-id")
    assert res.status_code == 403

  def test_patch_block_blocked(self, client: TestClient):
    res = client.patch("/api/blocks/fake-id", json={"text": "hello"})
    assert res.status_code == 403

  def test_move_block_blocked(self, client: TestClient):
    res = client.patch("/api/blocks/fake-id/position", json={})
    assert res.status_code == 403

  def test_change_block_type_blocked(self, client: TestClient):
    res = client.patch("/api/blocks/fake-id/type", json={"type": "code"})
    assert res.status_code == 403

  def test_delete_block_blocked(self, client: TestClient):
    res = client.delete("/api/blocks/fake-id")
    assert res.status_code == 403

  def test_upload_image_blocked(self, client: TestClient):
    res = client.post("/api/upload", files={"file": ("test.png", b"fake", "image/png")})
    assert res.status_code == 403

  def test_database_patch_blocked(self, client: TestClient):
    res = client.patch("/api/database/blocks/fake-id", json={"title": "test"})
    assert res.status_code == 403

  def test_database_add_column_blocked(self, client: TestClient):
    res = client.post("/api/database/blocks/fake-id/schema/columns", json={"name": "col"})
    assert res.status_code == 403

  def test_database_remove_column_blocked(self, client: TestClient):
    res = client.delete("/api/database/blocks/fake-id/schema/columns/fake-col")
    assert res.status_code == 403


# ── 관리자 쓰기 허용 테스트 ───────────────────────────────────────────────

class TestAdminWriteAllowed:
  """인증 후 쓰기 엔드포인트가 정상 동작하는지 검증한다."""

  def test_create_document_allowed(self, client: TestClient):
    _login(client)
    res = client.post("/api/documents")
    assert res.status_code == 201
    assert "id" in res.json()

  def test_create_and_patch_block(self, client: TestClient):
    _login(client)
    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "text"},
    ).json()
    res = client.patch(f"/api/blocks/{block['id']}", json={"text": "hello"})
    assert res.status_code == 200

  def test_delete_document_allowed(self, client: TestClient):
    _login(client)
    doc = client.post("/api/documents").json()
    res = client.delete(f"/api/documents/{doc['id']}")
    assert res.status_code == 204


# ── 세션 만료 테스트 ───────────────────────────────────────────────────────

class TestSessionExpiry:
  def test_expired_session_blocks_write(self, client: TestClient):
    _login(client)
    # 세션을 수동으로 만료시킨다
    for entry in session_store._sessions.values():
      entry.expires_at = time.time() - 1
    res = client.post("/api/documents")
    assert res.status_code == 403
    assert "만료" in res.json()["detail"]


# ── 로그아웃 후 쓰기 차단 테스트 ──────────────────────────────────────────

class TestLogoutBlocksWrite:
  def test_write_blocked_after_logout(self, client: TestClient):
    _login(client)
    # 쓰기 가능 확인
    doc = client.post("/api/documents")
    assert doc.status_code == 201
    # 로그아웃
    client.post("/api/auth/logout")
    # 쓰기 차단 확인
    res = client.post("/api/documents")
    assert res.status_code == 403


# ── 읽기 API 접근 테스트 ──────────────────────────────────────────────────

class TestReadAccessAllowed:
  """미인증 상태에서도 읽기 API는 정상 동작해야 한다."""

  def test_list_documents_allowed(self, client: TestClient):
    res = client.get("/api/documents")
    assert res.status_code == 200

  def test_get_document_returns_404_not_403(self, client: TestClient):
    """존재하지 않는 문서 조회는 403이 아닌 404를 반환한다."""
    res = client.get("/api/documents/nonexistent")
    assert res.status_code == 404


# ── 세션 저장소 단위 테스트 ───────────────────────────────────────────────

class TestSessionStore:
  def test_create_and_validate(self):
    store = SessionStore()
    token = store.create("admin")
    assert store.validate(token) == "admin"

  def test_validate_invalid_token(self):
    store = SessionStore()
    assert store.validate("bogus-token") is None

  def test_revoke(self):
    store = SessionStore()
    token = store.create("admin")
    assert store.revoke(token) is True
    assert store.validate(token) is None
    assert store.revoke(token) is False

  def test_cleanup_expired(self):
    store = SessionStore()
    token = store.create("admin")
    # 수동 만료
    store._sessions[token].expires_at = time.time() - 1
    removed = store.cleanup_expired()
    assert removed == 1
    assert store.validate(token) is None
