"""FE/BE 분리(#54)에 따른 be 엔드포인트/미들웨어 회귀 테스트.

본 테스트는 다음을 보장한다.

- `/` 루트 HTML 응답이 제거되었다 (FE 에서 서빙).
- `/api/health` 헬스체크가 200 을 반환한다.
- `/static/uploads`, `/static/files` 마운트가 유지된다
  (업로드 이미지/사용자 파일은 be 가 계속 제공한다).
- CORS 프리플라이트가 허용 오리진에 대해 올바른 헤더를 반환한다.
  (Ref: https://fastapi.tiangolo.com/tutorial/cors/)
"""
from __future__ import annotations

from pathlib import Path


def test_root_html_route_removed(client):
  """FE 분리 후 be 는 루트 HTML 을 반환하지 않아야 한다."""
  res = client.get("/")
  assert res.status_code == 404


def test_health_endpoint_returns_ok(client):
  """헬스체크 엔드포인트는 단순 200 JSON 을 반환한다."""
  res = client.get("/api/health")
  assert res.status_code == 200
  assert res.json() == {"status": "ok"}


def test_static_uploads_mount_serves_file(client, tmp_path):
  """업로드 이미지는 be 의 /static/uploads 로 계속 서빙되어야 한다.

  임시 파일을 static/uploads 에 생성한 뒤 200 응답과 내용을 검증한다.
  404 만으로는 '라우트 없음'과 'StaticFiles 마운트 내 파일 없음'을 구분할 수 없으므로,
  실제 파일을 조회해 마운트가 올바르게 동작하는지 확인한다.
  (Ref: https://www.starlette.io/staticfiles/)
  """
  from main import BASE_DIR

  uploads_dir = BASE_DIR / "static" / "uploads"
  uploads_dir.mkdir(parents=True, exist_ok=True)
  test_file = uploads_dir / "__test_probe__.txt"
  test_file.write_text("probe")
  try:
    res = client.get("/static/uploads/__test_probe__.txt")
    assert res.status_code == 200
    assert res.text == "probe"
  finally:
    test_file.unlink(missing_ok=True)


def test_cors_preflight_allows_configured_origin(client):
  """기본 허용 오리진(http://localhost:5173) 에 대해 CORS 프리플라이트가 허용되어야 한다."""
  res = client.options(
    "/api/health",
    headers={
      "Origin": "http://localhost:5173",
      "Access-Control-Request-Method": "GET",
    },
  )
  # 프리플라이트 성공 시 200, 허용 오리진 헤더 반영
  assert res.status_code == 200
  assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
  assert res.headers.get("access-control-allow-credentials") == "true"


def test_cors_rejects_unknown_origin(client):
  """허용되지 않은 오리진은 Access-Control-Allow-Origin 헤더를 부여받지 못한다."""
  res = client.options(
    "/api/health",
    headers={
      "Origin": "http://evil.example",
      "Access-Control-Request-Method": "GET",
    },
  )
  # CORSMiddleware 는 미허용 오리진에 대해 Allow-Origin 헤더를 생략한다.
  assert res.headers.get("access-control-allow-origin") != "http://evil.example"


def test_cors_wildcard_origin_fallback(monkeypatch):
  """FE_ALLOWED_ORIGINS 에 와일드카드(*)가 포함되면 기본 오리진으로 폴백해야 한다.

  allow_credentials=True 와 allow_origins=["*"] 조합은 CORS 스펙에 위배되어
  Starlette CORSMiddleware 가 RuntimeError 를 발생시킨다. 이를 방어하기 위해
  와일드카드 입력 시 기본값으로 대체하는 로직을 검증한다.
  (Ref: https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS#credentialed_requests_and_wildcards)
  """
  monkeypatch.setenv("FE_ALLOWED_ORIGINS", "*")

  import importlib
  import main as main_module
  importlib.reload(main_module)
  try:
    from fastapi.testclient import TestClient
    with TestClient(main_module.app) as c:
      res = c.options(
        "/api/health",
        headers={
          "Origin": "http://localhost:5173",
          "Access-Control-Request-Method": "GET",
        },
      )
      assert res.status_code == 200
      assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
  finally:
    monkeypatch.delenv("FE_ALLOWED_ORIGINS", raising=False)
    importlib.reload(main_module)


def test_be_has_no_templates_directory():
  """be 레포에는 프론트 템플릿 디렉터리가 더 이상 존재하지 않아야 한다."""
  be_root = Path(__file__).resolve().parent.parent
  assert not (be_root / "templates").exists(), "templates/ 는 fe/ 로 이전되어야 한다."
  assert not (be_root / "static" / "js").exists(), "static/js 는 fe/ 로 이전되어야 한다."
  assert not (be_root / "static" / "css").exists(), "static/css 는 fe/ 로 이전되어야 한다."
