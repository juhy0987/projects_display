"""파일 업로드·다운로드 기능 단위 테스트 (이슈 #63).

커버리지 범위:
  1. app.services.file  — sanitize_filename, validate_extension, save_file,
                          get_file_path, delete_stored_file
  2. Repository 레이어  — SQLiteFileRepository CRUD
  3. API 레이어         — POST 업로드, GET 다운로드, GET 목록, DELETE, 오류 케이스

참고:
  - pytest 공식 문서: https://docs.pytest.org/en/stable/
  - FastAPI TestClient: https://fastapi.tiangolo.com/tutorial/testing/
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.orm import Base, FileRow
from app.repositories.file_repo import SQLiteFileRepository


# ── 공통 픽스처 ───────────────────────────────────────────────────────────────

@pytest.fixture()
def file_engine():
  """files 테이블을 포함하는 인메모리 SQLite 엔진. 테스트별 격리."""
  eng = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
  )
  Base.metadata.create_all(eng)
  return eng


@pytest.fixture()
def file_session(file_engine):
  with Session(file_engine) as s:
    yield s


@pytest.fixture()
def file_repo(file_session):
  return SQLiteFileRepository(file_session)


@pytest.fixture()
def file_client(file_engine, tmp_path, monkeypatch):
  """파일 라우터가 포함된 TestClient. DB와 파일 저장 경로 모두 격리."""
  from main import app
  from app.dependencies import get_session
  from app.services import file as file_svc

  # 파일 저장 경로를 tmp_path로 교체 — 실제 static/files 에 영향 없음
  monkeypatch.setattr(file_svc, "FILES_DIR", tmp_path / "files")

  def _override_session():
    with Session(file_engine) as s:
      yield s

  app.dependency_overrides[get_session] = _override_session
  with TestClient(app) as c:
    c.post("/api/auth/login", json={"username": "admin", "password": "admin1234"})
    yield c
  app.dependency_overrides.pop(get_session, None)


def _make_upload_file(content: bytes = b"hello", filename: str = "test.txt") -> dict:
  """TestClient multipart 업로드용 파일 튜플을 생성하는 헬퍼."""
  return {"file": (filename, io.BytesIO(content), "text/plain")}


# ── 1. app.services.file ─────────────────────────────────────────────────────

class TestSanitizeFilename:
  """sanitize_filename() 의 입력 정규화 및 위험 문자 제거를 검증."""

  def test_normal_name_unchanged(self):
    """일반 파일명은 변경되지 않는다."""
    from app.services.file import sanitize_filename
    assert sanitize_filename("report.pdf") == "report.pdf"

  def test_path_separator_replaced(self):
    """슬래시·역슬래시 경로 구분자는 밑줄로 치환된다."""
    from app.services.file import sanitize_filename
    assert "/" not in sanitize_filename("../../etc/passwd")
    assert "\\" not in sanitize_filename("..\\windows\\system32")

  def test_null_byte_removed(self):
    """null byte(\x00)는 밑줄로 치환된다."""
    from app.services.file import sanitize_filename
    assert "\x00" not in sanitize_filename("file\x00name.txt")

  def test_control_characters_removed(self):
    """제어 문자(\x01–\x1f)는 밑줄로 치환된다."""
    from app.services.file import sanitize_filename
    result = sanitize_filename("file\x01name.txt")
    assert "\x01" not in result

  def test_empty_string_returns_unnamed(self):
    """빈 문자열은 'unnamed'를 반환한다."""
    from app.services.file import sanitize_filename
    assert sanitize_filename("") == "unnamed"

  def test_whitespace_only_returns_unnamed(self):
    """공백만 있는 문자열은 'unnamed'를 반환한다."""
    from app.services.file import sanitize_filename
    assert sanitize_filename("   ") == "unnamed"

  def test_korean_filename_preserved(self):
    """한글 파일명은 그대로 보존된다."""
    from app.services.file import sanitize_filename
    assert sanitize_filename("보고서.pdf") == "보고서.pdf"

  def test_max_length_truncation(self):
    """255자를 초과하는 파일명은 잘린다."""
    from app.services.file import sanitize_filename, MAX_FILENAME_LENGTH
    long_name = "a" * 300
    assert len(sanitize_filename(long_name)) <= MAX_FILENAME_LENGTH


class TestValidateExtension:
  """validate_extension() 의 허용/거부 로직을 검증."""

  def test_allowed_extension_returns_ext(self):
    """허용 확장자는 소문자 확장자를 반환한다."""
    from app.services.file import validate_extension
    assert validate_extension("report.pdf") == ".pdf"

  def test_uppercase_extension_normalized(self):
    """대문자 확장자도 소문자로 정규화하여 허용된다."""
    from app.services.file import validate_extension
    assert validate_extension("IMAGE.PNG") == ".png"

  def test_disallowed_extension_raises(self):
    """허용 목록에 없는 확장자는 ValueError를 발생시킨다."""
    from app.services.file import validate_extension
    with pytest.raises(ValueError, match="허용하지 않는"):
      validate_extension("script.exe")

  def test_no_extension_raises(self):
    """확장자 없는 파일명은 ValueError를 발생시킨다."""
    from app.services.file import validate_extension
    with pytest.raises(ValueError, match="확장자가 없습니다"):
      validate_extension("noextension")

  def test_shell_script_rejected(self):
    """.sh 파일은 허용되지 않는다."""
    from app.services.file import validate_extension
    with pytest.raises(ValueError):
      validate_extension("attack.sh")

  def test_python_file_rejected(self):
    """.py 파일은 허용되지 않는다."""
    from app.services.file import validate_extension
    with pytest.raises(ValueError):
      validate_extension("malicious.py")

  def test_zip_allowed(self):
    """.zip 파일은 허용된다."""
    from app.services.file import validate_extension
    assert validate_extension("archive.zip") == ".zip"

  def test_docx_allowed(self):
    """.docx 파일은 허용된다."""
    from app.services.file import validate_extension
    assert validate_extension("document.docx") == ".docx"


class TestSaveFile:
  """save_file() 의 디스크 저장 및 반환값을 검증."""

  def test_returns_stored_filename(self, tmp_path, monkeypatch):
    """저장 후 stored_filename이 반환된다."""
    from app.services import file as svc
    monkeypatch.setattr(svc, "FILES_DIR", tmp_path / "files")

    result = svc.save_file(b"data", "test.txt")
    assert "stored_filename" in result

  def test_stored_filename_is_uuid_hex(self, tmp_path, monkeypatch):
    """stored_filename은 32자리 UUID hex 형식이다."""
    from app.services import file as svc
    monkeypatch.setattr(svc, "FILES_DIR", tmp_path / "files")

    result = svc.save_file(b"data", "test.txt")
    assert len(result["stored_filename"]) == 32

  def test_file_exists_after_save(self, tmp_path, monkeypatch):
    """save_file 호출 후 디스크에 파일이 존재한다."""
    from app.services import file as svc
    files_dir = tmp_path / "files"
    monkeypatch.setattr(svc, "FILES_DIR", files_dir)

    result = svc.save_file(b"hello", "test.txt")
    assert (files_dir / result["stored_filename"]).exists()

  def test_size_bytes_matches_data(self, tmp_path, monkeypatch):
    """반환된 size_bytes는 실제 데이터 크기와 일치한다."""
    from app.services import file as svc
    monkeypatch.setattr(svc, "FILES_DIR", tmp_path / "files")

    data = b"0" * 1234
    result = svc.save_file(data, "test.txt")
    assert result["size_bytes"] == 1234

  def test_sanitized_filename_returned(self, tmp_path, monkeypatch):
    """sanitize된 원본 파일명이 반환된다."""
    from app.services import file as svc
    monkeypatch.setattr(svc, "FILES_DIR", tmp_path / "files")

    result = svc.save_file(b"data", "../../evil.txt")
    assert "/" not in result["sanitized_filename"]

  def test_unique_stored_filename_per_call(self, tmp_path, monkeypatch):
    """두 번 호출하면 서로 다른 stored_filename이 생성된다."""
    from app.services import file as svc
    monkeypatch.setattr(svc, "FILES_DIR", tmp_path / "files")

    r1 = svc.save_file(b"a", "a.txt")
    r2 = svc.save_file(b"b", "b.txt")
    assert r1["stored_filename"] != r2["stored_filename"]

  def test_exceeding_max_bytes_raises(self, tmp_path, monkeypatch):
    """MAX_BYTES를 초과하는 데이터는 ValueError를 발생시킨다."""
    from app.services import file as svc
    monkeypatch.setattr(svc, "FILES_DIR", tmp_path / "files")
    monkeypatch.setattr(svc, "MAX_BYTES", 10)  # 10 bytes로 제한

    with pytest.raises(ValueError, match="초과"):
      svc.save_file(b"x" * 11, "big.txt")


class TestGetFilePath:
  """get_file_path() 의 경로 조회 및 path traversal 방어를 검증."""

  def test_returns_correct_path(self, tmp_path, monkeypatch):
    """저장된 파일의 올바른 절대 경로를 반환한다."""
    from app.services import file as svc
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    monkeypatch.setattr(svc, "FILES_DIR", files_dir)

    fname = "abc123"
    (files_dir / fname).write_bytes(b"content")

    path = svc.get_file_path(fname)
    assert path.exists()

  def test_missing_file_raises_file_not_found(self, tmp_path, monkeypatch):
    """존재하지 않는 파일은 FileNotFoundError를 발생시킨다."""
    from app.services import file as svc
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    monkeypatch.setattr(svc, "FILES_DIR", files_dir)

    with pytest.raises(FileNotFoundError):
      svc.get_file_path("nonexistent")

  def test_path_traversal_raises_value_error(self, tmp_path, monkeypatch):
    """경로 순회 입력(../)은 ValueError를 발생시킨다."""
    from app.services import file as svc
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    monkeypatch.setattr(svc, "FILES_DIR", files_dir)

    with pytest.raises(ValueError, match="허용되지 않는"):
      svc.get_file_path("../secret")


class TestDeleteStoredFile:
  """delete_stored_file() 의 삭제 동작을 검증."""

  def test_existing_file_deleted_returns_true(self, tmp_path, monkeypatch):
    """존재하는 파일 삭제 시 True를 반환하고 파일이 사라진다."""
    from app.services import file as svc
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    monkeypatch.setattr(svc, "FILES_DIR", files_dir)

    fname = "deleteme"
    (files_dir / fname).write_bytes(b"bye")

    assert svc.delete_stored_file(fname) is True
    assert not (files_dir / fname).exists()

  def test_missing_file_returns_false(self, tmp_path, monkeypatch):
    """존재하지 않는 파일에 대해 False를 반환한다."""
    from app.services import file as svc
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    monkeypatch.setattr(svc, "FILES_DIR", files_dir)

    assert svc.delete_stored_file("ghost") is False

  def test_path_traversal_returns_false(self, tmp_path, monkeypatch):
    """경로 순회 입력에 대해 False를 반환하며 예외를 던지지 않는다."""
    from app.services import file as svc
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    monkeypatch.setattr(svc, "FILES_DIR", files_dir)

    assert svc.delete_stored_file("../outside") is False


# ── 2. Repository 레이어 ──────────────────────────────────────────────────────

class TestSQLiteFileRepository:
  """SQLiteFileRepository의 CRUD 메서드를 검증."""

  def _create(self, repo: SQLiteFileRepository, **kwargs) -> FileRow:
    """테스트용 FileRow를 생성하는 헬퍼."""
    defaults = {
      "original_filename": "test.txt",
      "stored_filename": "uuid_hex_value",
      "mime_type": "text/plain",
      "size_bytes": 100,
    }
    defaults.update(kwargs)
    return repo.create_file(**defaults)

  def test_create_returns_file_row(self, file_repo):
    """create_file이 FileRow를 반환한다."""
    row = self._create(file_repo)
    assert isinstance(row, FileRow)

  def test_create_assigns_id(self, file_repo):
    """생성된 row에 id가 할당된다."""
    row = self._create(file_repo)
    assert row.id and len(row.id) > 0

  def test_create_persists_fields(self, file_repo):
    """저장된 필드 값이 정확히 유지된다."""
    row = self._create(
      file_repo,
      original_filename="보고서.pdf",
      stored_filename="abc123",
      mime_type="application/pdf",
      size_bytes=9999,
    )
    assert row.original_filename == "보고서.pdf"
    assert row.stored_filename == "abc123"
    assert row.mime_type == "application/pdf"
    assert row.size_bytes == 9999

  def test_create_sets_created_at(self, file_repo):
    """created_at 필드가 ISO-8601 형식으로 설정된다."""
    row = self._create(file_repo)
    assert "T" in row.created_at  # ISO-8601 날짜·시각 구분자

  def test_get_existing_file(self, file_repo):
    """get_file로 생성한 row를 조회할 수 있다."""
    row = self._create(file_repo)
    fetched = file_repo.get_file(row.id)
    assert fetched is not None
    assert fetched.id == row.id

  def test_get_nonexistent_returns_none(self, file_repo):
    """존재하지 않는 id 조회 시 None을 반환한다."""
    assert file_repo.get_file("no-such-id") is None

  def test_list_returns_all_files(self, file_repo):
    """list_files는 생성한 모든 row를 반환한다."""
    self._create(file_repo, stored_filename="uuid1")
    self._create(file_repo, stored_filename="uuid2")
    rows = file_repo.list_files()
    assert len(rows) == 2

  def test_list_empty_when_no_files(self, file_repo):
    """파일이 없을 때 빈 리스트를 반환한다."""
    assert file_repo.list_files() == []

  def test_delete_returns_deleted_row(self, file_repo):
    """delete_file은 삭제된 FileRow를 반환한다."""
    row = self._create(file_repo)
    deleted = file_repo.delete_file(row.id)
    assert deleted is not None
    assert deleted.id == row.id

  def test_delete_removes_from_db(self, file_repo):
    """삭제 후 get_file 조회 시 None을 반환한다."""
    row = self._create(file_repo)
    file_repo.delete_file(row.id)
    assert file_repo.get_file(row.id) is None

  def test_delete_nonexistent_returns_none(self, file_repo):
    """존재하지 않는 id 삭제 시 None을 반환한다."""
    assert file_repo.delete_file("ghost-id") is None

  def test_list_ordered_by_created_at_desc(self, file_repo):
    """list_files는 생성 시각 역순(최신 우선)으로 반환한다."""
    r1 = self._create(file_repo, stored_filename="older", original_filename="a.txt")
    r2 = self._create(file_repo, stored_filename="newer", original_filename="b.txt")
    rows = file_repo.list_files()
    # 최신(r2)이 먼저 나와야 함
    assert rows[0].id == r2.id
    assert rows[1].id == r1.id


# ── 3. API 레이어 ─────────────────────────────────────────────────────────────

class TestFileUploadAPI:
  """POST /api/files 업로드 엔드포인트를 검증."""

  def test_upload_returns_201(self, file_client):
    """정상 업로드 요청은 201을 반환한다."""
    resp = file_client.post("/api/files", files=_make_upload_file())
    assert resp.status_code == 201

  def test_upload_response_has_required_fields(self, file_client):
    """응답 JSON에 id, original_filename, download_url 등이 포함된다."""
    resp = file_client.post("/api/files", files=_make_upload_file())
    data = resp.json()
    for field in ("id", "original_filename", "mime_type", "size_bytes", "created_at", "download_url"):
      assert field in data, f"필드 누락: {field}"

  def test_upload_download_url_points_to_api(self, file_client):
    """download_url이 /api/files/{id} 형식을 가진다."""
    resp = file_client.post("/api/files", files=_make_upload_file())
    data = resp.json()
    assert data["download_url"] == f"/api/files/{data['id']}"

  def test_upload_disallowed_extension_returns_415(self, file_client):
    """허용되지 않는 확장자(.exe) 업로드 시 415를 반환한다."""
    resp = file_client.post(
      "/api/files",
      files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert resp.status_code == 415

  def test_upload_shell_script_returns_415(self, file_client):
    """셸 스크립트(.sh) 업로드 시 415를 반환한다."""
    resp = file_client.post(
      "/api/files",
      files={"file": ("attack.sh", io.BytesIO(b"#!/bin/sh"), "text/x-sh")},
    )
    assert resp.status_code == 415

  def test_upload_pdf_allowed(self, file_client):
    """PDF 파일 업로드가 성공한다."""
    resp = file_client.post(
      "/api/files",
      files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert resp.status_code == 201

  def test_upload_zip_allowed(self, file_client):
    """ZIP 파일 업로드가 성공한다."""
    resp = file_client.post(
      "/api/files",
      files={"file": ("archive.zip", io.BytesIO(b"PK"), "application/zip")},
    )
    assert resp.status_code == 201

  def test_upload_size_bytes_correct(self, file_client):
    """응답의 size_bytes가 실제 업로드 크기와 일치한다."""
    content = b"x" * 500
    resp = file_client.post(
      "/api/files",
      files={"file": ("data.txt", io.BytesIO(content), "text/plain")},
    )
    assert resp.json()["size_bytes"] == 500

  def test_upload_korean_filename_sanitized(self, file_client):
    """한글 파일명이 포함된 업로드도 정상 처리된다."""
    resp = file_client.post(
      "/api/files",
      files={"file": ("한글파일.txt", io.BytesIO(b"content"), "text/plain")},
    )
    assert resp.status_code == 201
    assert resp.json()["original_filename"] == "한글파일.txt"


class TestFileDownloadAPI:
  """GET /api/files/{file_id} 다운로드 엔드포인트를 검증."""

  def _upload(self, client, content: bytes = b"file content", filename: str = "test.txt"):
    """업로드 후 메타데이터를 반환하는 헬퍼."""
    return client.post("/api/files", files=_make_upload_file(content, filename)).json()

  def test_download_returns_200(self, file_client):
    """정상 다운로드 요청은 200을 반환한다."""
    meta = self._upload(file_client)
    resp = file_client.get(f"/api/files/{meta['id']}")
    assert resp.status_code == 200

  def test_download_content_matches_uploaded(self, file_client):
    """다운로드한 파일 내용이 업로드한 내용과 일치한다."""
    content = b"hello, world!"
    meta = self._upload(file_client, content=content)
    resp = file_client.get(f"/api/files/{meta['id']}")
    assert resp.content == content

  def test_download_content_disposition_header_present(self, file_client):
    """Content-Disposition 헤더가 응답에 포함된다."""
    meta = self._upload(file_client, filename="report.txt")
    resp = file_client.get(f"/api/files/{meta['id']}")
    assert "content-disposition" in resp.headers

  def test_download_content_disposition_is_attachment(self, file_client):
    """Content-Disposition이 attachment 타입이다."""
    meta = self._upload(file_client, filename="report.txt")
    resp = file_client.get(f"/api/files/{meta['id']}")
    assert "attachment" in resp.headers["content-disposition"]

  def test_download_content_disposition_rfc5987_encoded(self, file_client):
    """Content-Disposition에 RFC 5987 인코딩(filename*)이 사용된다."""
    meta = self._upload(file_client, filename="보고서.txt")
    resp = file_client.get(f"/api/files/{meta['id']}")
    assert "filename*=UTF-8''" in resp.headers["content-disposition"]

  def test_download_nonexistent_returns_404(self, file_client):
    """존재하지 않는 file_id 요청 시 404를 반환한다."""
    resp = file_client.get("/api/files/no-such-id")
    assert resp.status_code == 404


class TestFileListAPI:
  """GET /api/files 목록 조회 엔드포인트를 검증."""

  def test_empty_list_when_no_uploads(self, file_client):
    """업로드 전 목록 조회 시 빈 배열을 반환한다."""
    resp = file_client.get("/api/files")
    assert resp.status_code == 200
    assert resp.json() == []

  def test_list_includes_uploaded_file(self, file_client):
    """업로드 후 목록에 해당 파일이 포함된다."""
    meta = file_client.post("/api/files", files=_make_upload_file()).json()
    items = file_client.get("/api/files").json()
    ids = [item["id"] for item in items]
    assert meta["id"] in ids

  def test_list_count_increases_after_upload(self, file_client):
    """업로드할 때마다 목록 수가 증가한다."""
    file_client.post("/api/files", files=_make_upload_file(filename="a.txt"))
    file_client.post("/api/files", files=_make_upload_file(filename="b.txt"))
    items = file_client.get("/api/files").json()
    assert len(items) == 2

  def test_list_items_have_download_url(self, file_client):
    """목록의 각 항목에 download_url이 포함된다."""
    file_client.post("/api/files", files=_make_upload_file())
    items = file_client.get("/api/files").json()
    for item in items:
      assert "download_url" in item


class TestFileDeleteAPI:
  """DELETE /api/files/{file_id} 삭제 엔드포인트를 검증."""

  def test_delete_returns_204(self, file_client):
    """정상 삭제 요청은 204를 반환한다."""
    meta = file_client.post("/api/files", files=_make_upload_file()).json()
    resp = file_client.delete(f"/api/files/{meta['id']}")
    assert resp.status_code == 204

  def test_deleted_file_not_in_list(self, file_client):
    """삭제 후 목록 조회 시 해당 파일이 없다."""
    meta = file_client.post("/api/files", files=_make_upload_file()).json()
    file_client.delete(f"/api/files/{meta['id']}")
    items = file_client.get("/api/files").json()
    assert all(item["id"] != meta["id"] for item in items)

  def test_deleted_file_download_returns_404(self, file_client):
    """삭제 후 다운로드 시도 시 404를 반환한다."""
    meta = file_client.post("/api/files", files=_make_upload_file()).json()
    file_client.delete(f"/api/files/{meta['id']}")
    resp = file_client.get(f"/api/files/{meta['id']}")
    assert resp.status_code == 404

  def test_delete_nonexistent_returns_404(self, file_client):
    """존재하지 않는 file_id 삭제 시 404를 반환한다."""
    resp = file_client.delete("/api/files/no-such-id")
    assert resp.status_code == 404
