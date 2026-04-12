"""URL 임베드 블록 기능 단위 테스트 (이슈 #36).

커버리지 범위:
  1. _MetaParser  — OG / Twitter Card / 기본 HTML 태그 파싱
  2. _is_ssrf_safe — 차단 규칙 (프로토콜, 사설 IP, 루프백)
  3. fetch_url_metadata — HTTP 성공/실패/비HTML 응답 시나리오
  4. Repository 레이어 — url_embed 블록 생성·업데이트·타입 변환
  5. API 레이어 — POST /api/url-embed/fetch, POST /api/documents/{id}/blocks
"""
from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest


# ── 1. _MetaParser ────────────────────────────────────────────────────────────

class TestMetaParser:
  """HTML 소스에서 메타데이터를 올바르게 추출하는지 검증."""

  def _parse(self, html: str):
    from app.services.url_embed import _MetaParser
    p = _MetaParser()
    p.feed(html)
    return p

  def test_og_title_extracted(self):
    p = self._parse('<meta property="og:title" content="OG Title">')
    assert p.best_title == "OG Title"

  def test_og_description_extracted(self):
    p = self._parse('<meta property="og:description" content="OG Desc">')
    assert p.best_description == "OG Desc"

  def test_og_image_extracted(self):
    p = self._parse('<meta property="og:image" content="https://example.com/img.png">')
    assert p.best_logo == "https://example.com/img.png"

  def test_twitter_card_fallback(self):
    """OG 태그 없을 때 Twitter Card를 사용한다."""
    p = self._parse(
      '<meta name="twitter:title" content="TW Title">'
      '<meta name="twitter:description" content="TW Desc">'
    )
    assert p.best_title == "TW Title"
    assert p.best_description == "TW Desc"

  def test_og_takes_priority_over_twitter(self):
    """OG 태그가 Twitter Card보다 우선한다."""
    p = self._parse(
      '<meta property="og:title" content="OG Title">'
      '<meta name="twitter:title" content="TW Title">'
    )
    assert p.best_title == "OG Title"

  def test_html_title_fallback(self):
    """OG / Twitter 없을 때 <title> 태그를 사용한다."""
    p = self._parse("<title>  페이지 제목  </title>")
    assert p.best_title == "페이지 제목"

  def test_meta_description_fallback(self):
    """OG / Twitter 없을 때 meta[name=description]을 사용한다."""
    p = self._parse('<meta name="description" content="기본 설명">')
    assert p.best_description == "기본 설명"

  def test_favicon_link_extracted(self):
    p = self._parse('<link rel="icon" href="/favicon.ico">')
    assert p.best_logo == "/favicon.ico"

  def test_apple_touch_icon_preferred_over_favicon(self):
    """apple-touch-icon이 favicon보다 우선한다."""
    p = self._parse(
      '<link rel="icon" href="/favicon.ico">'
      '<link rel="apple-touch-icon" href="/apple.png">'
    )
    assert p.best_logo == "/apple.png"

  def test_og_image_preferred_over_apple_icon(self):
    """og:image가 apple-touch-icon보다 우선한다."""
    p = self._parse(
      '<meta property="og:image" content="https://cdn.example.com/og.jpg">'
      '<link rel="apple-touch-icon" href="/apple.png">'
    )
    assert p.best_logo == "https://cdn.example.com/og.jpg"

  def test_no_metadata_returns_empty(self):
    p = self._parse("<html><head></head><body><p>본문</p></body></html>")
    assert p.best_title == ""
    assert p.best_description == ""
    assert p.best_logo == ""

  def test_parsing_stops_after_head_closes(self):
    """</head> 이후 본문에 있는 태그는 무시한다."""
    p = self._parse(
      "<head><title>HEAD 제목</title></head>"
      "<body><meta property='og:title' content='BODY 태그'></body>"
    )
    assert p.best_title == "HEAD 제목"

  def test_empty_content_attribute_ignored(self):
    """content 속성이 빈 문자열인 meta 태그는 무시한다."""
    p = self._parse(
      '<meta property="og:title" content="">'
      "<title>폴백 제목</title>"
    )
    assert p.best_title == "폴백 제목"


# ── 2. _is_ssrf_safe ──────────────────────────────────────────────────────────

class TestIsSSRFSafe:
  """SSRF 방어 로직이 사설/루프백 주소를 올바르게 차단하는지 검증."""

  def _safe(self, url: str) -> bool:
    from app.services.url_embed import _is_ssrf_safe
    return _is_ssrf_safe(url)

  def _mock_resolve(self, ip: str):
    """getaddrinfo를 특정 IP를 반환하도록 패치하는 컨텍스트 반환."""
    return patch(
      "app.services.url_embed.socket.getaddrinfo",
      return_value=[(None, None, None, None, (ip, 0))],
    )

  def test_public_ip_allowed(self):
    with self._mock_resolve("93.184.216.34"):  # example.com
      assert self._safe("https://example.com") is True

  def test_loopback_blocked(self):
    with self._mock_resolve("127.0.0.1"):
      assert self._safe("http://localhost") is False

  def test_private_class_a_blocked(self):
    with self._mock_resolve("10.0.0.1"):
      assert self._safe("http://internal.corp") is False

  def test_private_class_b_blocked(self):
    with self._mock_resolve("172.16.0.1"):
      assert self._safe("http://internal.corp") is False

  def test_private_class_c_blocked(self):
    with self._mock_resolve("192.168.1.1"):
      assert self._safe("http://router.local") is False

  def test_link_local_blocked(self):
    with self._mock_resolve("169.254.169.254"):  # AWS 메타데이터 엔드포인트
      assert self._safe("http://169.254.169.254") is False

  def test_ipv6_loopback_blocked(self):
    with self._mock_resolve("::1"):
      assert self._safe("http://[::1]") is False

  def test_ftp_protocol_blocked(self):
    assert self._safe("ftp://example.com/file") is False

  def test_file_protocol_blocked(self):
    assert self._safe("file:///etc/passwd") is False

  def test_unresolvable_hostname_blocked(self):
    with patch(
      "app.services.url_embed.socket.getaddrinfo",
      side_effect=socket.gaierror("Name not resolved"),
    ):
      assert self._safe("http://does-not-exist.invalid") is False

  def test_empty_url_blocked(self):
    assert self._safe("") is False

  def test_no_scheme_blocked(self):
    assert self._safe("example.com/path") is False


# ── 3. fetch_url_metadata ─────────────────────────────────────────────────────

class TestFetchUrlMetadata:
  """fetch_url_metadata의 성공/실패 시나리오를 검증."""

  _SAMPLE_HTML = """
  <html><head>
    <title>샘플 페이지</title>
    <meta property="og:title" content="OG 제목">
    <meta property="og:description" content="OG 설명">
    <meta property="og:image" content="https://example.com/og.jpg">
  </head><body></body></html>
  """

  def _make_mock_response(self, html: str, content_type: str = "text/html; charset=utf-8"):
    """build_opener().open() 응답을 흉내 내는 컨텍스트 매니저 Mock."""
    mock_resp = MagicMock()
    mock_resp.headers.get.return_value = content_type
    mock_resp.headers.get_content_charset.return_value = "utf-8"
    mock_resp.read.return_value = html.encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp

  def _fetch(self, url: str, html: str, content_type: str = "text/html"):
    from app.services.url_embed import fetch_url_metadata

    mock_resp = self._make_mock_response(html, content_type)
    mock_opener = MagicMock()
    mock_opener.open.return_value = mock_resp
    with (
      patch("app.services.url_embed._is_ssrf_safe", return_value=True),
      patch("app.services.url_embed.urllib.request.build_opener", return_value=mock_opener),
    ):
      return fetch_url_metadata(url)

  # ── 성공 시나리오 ──────────────────────────────────────────────────────────

  def test_success_returns_og_fields(self):
    meta = self._fetch("https://example.com", self._SAMPLE_HTML)
    assert meta.status == "success"
    assert meta.title == "OG 제목"
    assert meta.description == "OG 설명"
    assert meta.logo == "https://example.com/og.jpg"

  def test_provider_extracted_without_www(self):
    meta = self._fetch("https://www.example.com", self._SAMPLE_HTML)
    assert meta.provider == "example.com"

  def test_relative_logo_resolved_to_absolute(self):
    html = (
      "<html><head>"
      '<link rel="icon" href="/favicon.ico">'
      "</head><body></body></html>"
    )
    meta = self._fetch("https://example.com/page", html)
    assert meta.logo == "https://example.com/favicon.ico"

  def test_fetched_at_is_populated(self):
    meta = self._fetch("https://example.com", self._SAMPLE_HTML)
    assert meta.fetched_at != ""

  def test_title_truncated_to_200_chars(self):
    long_title = "A" * 300
    html = f"<html><head><title>{long_title}</title></head></html>"
    meta = self._fetch("https://example.com", html)
    assert len(meta.title) <= 200

  def test_description_truncated_to_500_chars(self):
    long_desc = "D" * 600
    html = f'<html><head><meta name="description" content="{long_desc}"></head></html>'
    meta = self._fetch("https://example.com", html)
    assert len(meta.description) <= 500

  # ── 실패 시나리오 ──────────────────────────────────────────────────────────

  def test_ssrf_blocked_returns_error(self):
    from app.services.url_embed import fetch_url_metadata

    with patch("app.services.url_embed._is_ssrf_safe", return_value=False):
      meta = fetch_url_metadata("http://192.168.1.1")
    assert meta.status == "error"
    assert meta.error != ""

  def test_http_error_returns_error(self):
    import urllib.error
    from app.services.url_embed import fetch_url_metadata

    mock_opener = MagicMock()
    mock_opener.open.side_effect = urllib.error.HTTPError(None, 404, "Not Found", {}, None)
    with (
      patch("app.services.url_embed._is_ssrf_safe", return_value=True),
      patch("app.services.url_embed.urllib.request.build_opener", return_value=mock_opener),
    ):
      meta = fetch_url_metadata("https://example.com/missing")
    assert meta.status == "error"
    assert "404" in meta.error

  def test_url_error_returns_error(self):
    import urllib.error
    from app.services.url_embed import fetch_url_metadata

    mock_opener = MagicMock()
    mock_opener.open.side_effect = urllib.error.URLError("connection refused")
    with (
      patch("app.services.url_embed._is_ssrf_safe", return_value=True),
      patch("app.services.url_embed.urllib.request.build_opener", return_value=mock_opener),
    ):
      meta = fetch_url_metadata("https://unreachable.example.com")
    assert meta.status == "error"

  def test_timeout_returns_error(self):
    from app.services.url_embed import fetch_url_metadata

    mock_opener = MagicMock()
    mock_opener.open.side_effect = TimeoutError()
    with (
      patch("app.services.url_embed._is_ssrf_safe", return_value=True),
      patch("app.services.url_embed.urllib.request.build_opener", return_value=mock_opener),
    ):
      meta = fetch_url_metadata("https://slow.example.com")
    assert meta.status == "error"
    assert "초과" in meta.error

  def test_non_html_content_type_returns_error(self):
    meta = self._fetch("https://example.com/doc.pdf", "", content_type="application/pdf")
    assert meta.status == "error"

  def test_malformed_html_does_not_raise(self):
    """비정형 HTML에서도 예외 없이 부분 결과를 반환한다."""
    meta = self._fetch("https://example.com", "<<<not valid html>>>")
    assert meta.status == "success"  # 예외가 없으면 성공으로 처리


# ── 4. Repository 레이어 ──────────────────────────────────────────────────────

class TestUrlEmbedRepository:
  """SQLiteBlockRepository에서 url_embed 블록의 CRUD를 검증."""

  def test_create_url_embed_block(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "url_embed")
    assert block is not None
    assert block["type"] == "url_embed"
    assert block["url"] == ""
    assert block["status"] == "pending"

  def test_create_url_embed_returns_all_fields(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "url_embed")
    for field in ("url", "title", "description", "logo", "provider", "fetched_at", "status"):
      assert field in block, f"필드 누락: {field}"

  def test_update_url_embed_metadata(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "url_embed")
    patch_data = {
      "url": "https://example.com",
      "title": "예시 사이트",
      "description": "예시 설명",
      "logo": "https://example.com/favicon.ico",
      "provider": "example.com",
      "fetched_at": "2026-04-12T00:00:00+00:00",
      "status": "success",
    }
    assert repo.update_block(block["id"], patch_data)
    fetched = repo.get_document(doc["id"])
    embed = fetched.blocks[0]
    assert embed.type == "url_embed"
    assert embed.url == "https://example.com"
    assert embed.title == "예시 사이트"
    assert embed.status == "success"

  def test_url_embed_persists_across_get_document(self, repo):
    """저장 후 문서를 다시 불러왔을 때 url_embed 블록이 유지된다."""
    doc = repo.create_document()
    repo.create_block(doc["id"], "url_embed")
    repo.update_block(
      repo.get_document(doc["id"]).blocks[0].id,
      {"url": "https://example.com", "title": "저장 테스트", "status": "success"},
    )
    refetched = repo.get_document(doc["id"])
    embed = refetched.blocks[0]
    assert embed.url == "https://example.com"
    assert embed.title == "저장 테스트"

  def test_change_type_to_url_embed(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "text")
    assert repo.change_block_type(block["id"], "url_embed")
    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].type == "url_embed"
    assert fetched.blocks[0].status == "pending"

  def test_change_type_from_url_embed_to_text(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "url_embed")
    assert repo.change_block_type(block["id"], "text")
    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].type == "text"

  def test_delete_url_embed_block(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "url_embed")
    assert repo.delete_block(block["id"])
    fetched = repo.get_document(doc["id"])
    assert len(fetched.blocks) == 0


# ── 5. API 레이어 ─────────────────────────────────────────────────────────────

class TestUrlEmbedAPI:
  """HTTP API를 통한 url_embed 블록 생성·조회·메타데이터 페치를 검증."""

  def test_create_url_embed_block_via_api(self, client):
    doc = client.post("/api/documents").json()
    resp = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "url_embed"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "url_embed"
    assert data["status"] == "pending"

  def test_get_document_includes_url_embed_block(self, client):
    doc = client.post("/api/documents").json()
    client.post(f"/api/documents/{doc['id']}/blocks", json={"type": "url_embed"})
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert fetched["blocks"][0]["type"] == "url_embed"

  def test_patch_url_embed_url_via_blocks_api(self, client):
    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "url_embed"},
    ).json()
    resp = client.patch(f"/api/blocks/{block['id']}", json={"url": "https://example.com"})
    assert resp.status_code == 200

  def test_change_type_to_url_embed_via_api(self, client):
    doc = client.post("/api/documents").json()
    block = client.post(f"/api/documents/{doc['id']}/blocks", json={"type": "text"}).json()
    resp = client.patch(f"/api/blocks/{block['id']}/type", json={"type": "url_embed"})
    assert resp.status_code == 200

  def test_fetch_endpoint_ssrf_blocked(self, client):
    """사설 IP를 가리키는 URL은 status="error"로 응답한다."""
    with patch("app.services.url_embed._is_ssrf_safe", return_value=False):
      resp = client.post("/api/url-embed/fetch", json={"url": "http://192.168.1.1"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"

  def test_fetch_endpoint_success_updates_block(self, client):
    """block_id 전달 시 fetch 결과가 블록에 저장된다."""
    from unittest.mock import MagicMock, patch as mpatch

    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "url_embed"},
    ).json()

    mock_meta = MagicMock()
    mock_meta.url = "https://example.com"
    mock_meta.title = "Mock Title"
    mock_meta.description = "Mock Desc"
    mock_meta.logo = "https://example.com/logo.png"
    mock_meta.provider = "example.com"
    mock_meta.fetched_at = "2026-04-12T00:00:00+00:00"
    mock_meta.status = "success"
    mock_meta.error = ""

    with mpatch("app.routers.url_embed.fetch_url_metadata", return_value=mock_meta):
      resp = client.post(
        "/api/url-embed/fetch",
        json={"url": "https://example.com", "block_id": block["id"]},
      )

    assert resp.status_code == 200
    assert resp.json()["title"] == "Mock Title"

    # 블록이 실제로 업데이트됐는지 확인
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    embed = fetched["blocks"][0]
    assert embed["title"] == "Mock Title"
    assert embed["status"] == "success"

  def test_fetch_endpoint_invalid_block_id_returns_404(self, client):
    """존재하지 않는 block_id 전달 시 404를 반환한다."""
    mock_meta = MagicMock()
    mock_meta.url = "https://example.com"
    mock_meta.title = ""
    mock_meta.description = ""
    mock_meta.logo = ""
    mock_meta.provider = "example.com"
    mock_meta.fetched_at = ""
    mock_meta.status = "success"
    mock_meta.error = ""

    with patch("app.routers.url_embed.fetch_url_metadata", return_value=mock_meta):
      resp = client.post(
        "/api/url-embed/fetch",
        json={"url": "https://example.com", "block_id": "nonexistent-id"},
      )
    assert resp.status_code == 404

  def test_fetch_endpoint_rejects_empty_url(self, client):
    resp = client.post("/api/url-embed/fetch", json={"url": ""})
    assert resp.status_code == 422

  def test_fetch_endpoint_rejects_non_http_url(self, client):
    resp = client.post("/api/url-embed/fetch", json={"url": "ftp://example.com/file"})
    assert resp.status_code == 422

  def test_fetch_endpoint_rejects_url_over_max_length(self, client):
    long_url = "https://example.com/" + "a" * 2048
    resp = client.post("/api/url-embed/fetch", json={"url": long_url})
    assert resp.status_code == 422
