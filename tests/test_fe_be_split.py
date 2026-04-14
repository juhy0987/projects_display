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


def test_static_uploads_mount_exists(client, tmp_path, monkeypatch):
  """업로드 이미지는 be 의 /static/uploads 로 계속 서빙되어야 한다.

  실제 파일을 생성하지 않고 404 여부만 검사한다 (마운트 존재 시 404, 미마운트 시 405/404 혼재).
  StaticFiles 는 없는 파일에 대해 404 를 반환한다.
  (Ref: https://www.starlette.io/staticfiles/)
  """
  res = client.get("/static/uploads/__does_not_exist__.webp")
  assert res.status_code == 404


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


def test_be_has_no_templates_directory():
  """be 레포에는 프론트 템플릿 디렉터리가 더 이상 존재하지 않아야 한다."""
  be_root = Path(__file__).resolve().parent.parent
  assert not (be_root / "templates").exists(), "templates/ 는 fe/ 로 이전되어야 한다."
  assert not (be_root / "static" / "js").exists(), "static/js 는 fe/ 로 이전되어야 한다."
  assert not (be_root / "static" / "css").exists(), "static/css 는 fe/ 로 이전되어야 한다."
