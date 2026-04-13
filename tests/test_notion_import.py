"""Notion Import 기능 단위 테스트.

테스트 범위:
  1. HTML 파서 서비스 — 각 블록 타입 변환 정확도
  2. 인라인 서식 변환 — bold, italic, link 등
  3. ZIP 아카이브 처리 — 다중 페이지 구조 변환
  4. Import API 엔드포인트 — HTTP 상태 코드 및 응답 구조
  5. 에러 처리 — 잘못된 파일 형식, 빈 파일, 큰 파일
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from app.services.notion_import import (
  ConversionReport,
  ImportResult,
  _extract_inline_text,
  _is_image_file,
  _make_block,
  extract_and_parse_zip,
  parse_notion_html,
  parse_single_html,
)


# ── 테스트 HTML 헬퍼 ─────────────────────────────────────────────────────────

def _wrap_notion_html(body: str, title: str = "Test Page") -> str:
  """Notion export HTML 형식의 최소 구조를 반환합니다."""
  return f"""<!DOCTYPE html>
<html>
<head><title>{title}</title></head>
<body>
<article>
  <header><h1 class="page-title">{title}</h1></header>
  <div class="page-body">
    {body}
  </div>
</article>
</body>
</html>"""


def _make_zip(files: dict[str, str]) -> bytes:
  """파일명 → 내용 dict로 in-memory ZIP 파일을 생성합니다."""
  buf = io.BytesIO()
  with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    for name, content in files.items():
      zf.writestr(name, content)
  return buf.getvalue()


def _make_zip_with_image(html_files: dict[str, str], image_files: dict[str, bytes]) -> bytes:
  """HTML과 이미지 파일을 포함하는 ZIP을 생성합니다."""
  buf = io.BytesIO()
  with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    for name, content in html_files.items():
      zf.writestr(name, content)
    for name, data in image_files.items():
      zf.writestr(name, data)
  return buf.getvalue()


# ── 파서 서비스: 제목 추출 ───────────────────────────────────────────────────

class TestTitleExtraction:
  """페이지 제목 추출 테스트."""

  def test_extracts_page_title_from_header(self):
    html = _wrap_notion_html("<p>content</p>", title="My Title")
    result = parse_notion_html(html)
    assert result.title == "My Title"

  def test_falls_back_to_title_tag(self):
    html = """<html><head><title>Fallback Title</title></head>
    <body><div class="page-body"><p>text</p></div></body></html>"""
    result = parse_notion_html(html)
    assert result.title == "Fallback Title"

  def test_uses_untitled_when_no_title(self):
    html = """<html><body><div class="page-body"><p>text</p></div></body></html>"""
    result = parse_notion_html(html)
    assert result.title == "Untitled"


# ── 파서 서비스: 블록 변환 ───────────────────────────────────────────────────

class TestHeadingParsing:
  """제목(heading) 블록 변환 테스트."""

  def test_h1_becomes_text_level_1(self):
    html = _wrap_notion_html("<h1>Heading 1</h1>")
    result = parse_notion_html(html)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block["type"] == "text"
    assert block["text"] == "Heading 1"
    assert block["level"] == 1

  def test_h2_becomes_text_level_2(self):
    html = _wrap_notion_html("<h2>Heading 2</h2>")
    result = parse_notion_html(html)
    assert result.blocks[0]["level"] == 2

  def test_h3_becomes_text_level_3(self):
    html = _wrap_notion_html("<h3>Heading 3</h3>")
    result = parse_notion_html(html)
    assert result.blocks[0]["level"] == 3


class TestParagraphParsing:
  """문단(paragraph) 블록 변환 테스트."""

  def test_paragraph_becomes_text_block(self):
    html = _wrap_notion_html("<p>Hello World</p>")
    result = parse_notion_html(html)
    assert len(result.blocks) == 1
    assert result.blocks[0]["type"] == "text"
    assert result.blocks[0]["text"] == "Hello World"

  def test_empty_paragraph_is_skipped(self):
    html = _wrap_notion_html("<p>   </p>")
    result = parse_notion_html(html)
    assert len(result.blocks) == 0

  def test_multiple_paragraphs(self):
    html = _wrap_notion_html("<p>First</p><p>Second</p><p>Third</p>")
    result = parse_notion_html(html)
    assert len(result.blocks) == 3


class TestListParsing:
  """리스트 블록 변환 테스트."""

  def test_bulleted_list(self):
    html = _wrap_notion_html(
      '<ul class="bulleted-list"><li>Item A</li><li>Item B</li></ul>'
    )
    result = parse_notion_html(html)
    assert len(result.blocks) == 2
    assert result.blocks[0]["text"].startswith("• ")
    assert "Item A" in result.blocks[0]["text"]

  def test_numbered_list(self):
    html = _wrap_notion_html(
      '<ol class="numbered-list"><li>First</li><li>Second</li></ol>'
    )
    result = parse_notion_html(html)
    assert len(result.blocks) == 2
    assert result.blocks[0]["text"].startswith("1. ")
    assert result.blocks[1]["text"].startswith("2. ")

  def test_todo_list_checked(self):
    html = _wrap_notion_html(
      '<ul class="to-do-list"><li><div class="checkbox checkbox-on"></div>Done</li></ul>'
    )
    result = parse_notion_html(html)
    assert len(result.blocks) == 1
    assert result.blocks[0]["text"].startswith("☑")

  def test_todo_list_unchecked(self):
    html = _wrap_notion_html(
      '<ul class="to-do-list"><li><div class="checkbox checkbox-off"></div>Pending</li></ul>'
    )
    result = parse_notion_html(html)
    assert result.blocks[0]["text"].startswith("☐")


class TestToggleParsing:
  """토글 블록 변환 테스트."""

  def test_details_becomes_toggle(self):
    html = _wrap_notion_html(
      "<details><summary>Toggle Title</summary><p>Inner content</p></details>"
    )
    result = parse_notion_html(html)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block["type"] == "toggle"
    assert block["text"] == "Toggle Title"
    assert len(block["children"]) >= 1

  def test_empty_toggle_has_default_child(self):
    html = _wrap_notion_html(
      "<details><summary>Empty</summary></details>"
    )
    result = parse_notion_html(html)
    block = result.blocks[0]
    assert len(block["children"]) == 1
    assert block["children"][0]["type"] == "text"


class TestQuoteParsing:
  """인용문 블록 변환 테스트."""

  def test_blockquote_becomes_quote(self):
    html = _wrap_notion_html("<blockquote><p>A wise quote</p></blockquote>")
    result = parse_notion_html(html)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block["type"] == "quote"
    assert len(block["children"]) >= 1


class TestCodeParsing:
  """코드 블록 변환 테스트."""

  def test_pre_code_becomes_code_block(self):
    html = _wrap_notion_html(
      '<pre class="code"><code class="language-python">print("hello")</code></pre>'
    )
    result = parse_notion_html(html)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block["type"] == "code"
    assert 'print("hello")' in block["code"]
    assert block["language"] == "python"

  def test_code_without_language(self):
    html = _wrap_notion_html(
      '<pre class="code"><code>plain text</code></pre>'
    )
    result = parse_notion_html(html)
    assert result.blocks[0]["language"] == "plain"


class TestDividerParsing:
  """구분선 블록 변환 테스트."""

  def test_hr_becomes_divider(self):
    html = _wrap_notion_html("<hr/>")
    result = parse_notion_html(html)
    assert len(result.blocks) == 1
    assert result.blocks[0]["type"] == "divider"


class TestCalloutParsing:
  """콜아웃 블록 변환 테스트."""

  def test_callout_figure(self):
    html = _wrap_notion_html(
      '<figure class="callout"><span class="icon">⚠️</span>'
      '<div class="callout-body"><p>Warning text</p></div></figure>'
    )
    result = parse_notion_html(html)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block["type"] == "callout"
    assert block["emoji"] == "⚠️"
    assert len(block["children"]) >= 1


class TestImageParsing:
  """이미지 블록 변환 테스트."""

  def test_figure_img(self):
    html = _wrap_notion_html(
      '<figure><img src="images/photo.png"/>'
      '<figcaption>A nice photo</figcaption></figure>'
    )
    result = parse_notion_html(html)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block["type"] == "image"
    assert "photo.png" in block["url"]
    assert block["caption"] == "A nice photo"

  def test_standalone_img(self):
    html = _wrap_notion_html('<img src="test.jpg"/>')
    result = parse_notion_html(html)
    assert len(result.blocks) == 1
    assert result.blocks[0]["type"] == "image"


class TestBookmarkParsing:
  """북마크(URL embed) 블록 변환 테스트."""

  def test_bookmark_figure(self):
    html = _wrap_notion_html(
      '<figure class="bookmark source">'
      '<a href="https://example.com">'
      '<div class="bookmark-info">'
      '<div class="bookmark-title">Example</div>'
      '<div class="bookmark-description">A site</div>'
      '</div></a></figure>'
    )
    result = parse_notion_html(html)
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block["type"] == "url_embed"
    assert block["url"] == "https://example.com"
    assert block["title"] == "Example"


class TestTableParsing:
  """테이블 변환 테스트 (fallback 텍스트)."""

  def test_table_becomes_text_blocks(self):
    html = _wrap_notion_html(
      '<table><thead><tr><th>Name</th><th>Value</th></tr></thead>'
      '<tbody><tr><td>A</td><td>1</td></tr></tbody></table>'
    )
    result = parse_notion_html(html)
    # 헤더 + 구분선 + 데이터 행 = 최소 3블록
    assert len(result.blocks) >= 2
    assert result.report.fallback >= 1


# ── 인라인 서식 변환 ─────────────────────────────────────────────────────────

class TestInlineFormatting:
  """인라인 서식 태그 변환 테스트."""

  def test_bold(self):
    from bs4 import BeautifulSoup
    tag = BeautifulSoup("<p><strong>bold</strong></p>", "html.parser").find("p")
    plain, fmt = _extract_inline_text(tag)
    assert plain == "bold"
    assert "<b>bold</b>" in fmt

  def test_italic(self):
    from bs4 import BeautifulSoup
    tag = BeautifulSoup("<p><em>italic</em></p>", "html.parser").find("p")
    plain, fmt = _extract_inline_text(tag)
    assert plain == "italic"
    assert "<i>italic</i>" in fmt

  def test_link(self):
    from bs4 import BeautifulSoup
    tag = BeautifulSoup(
      '<p><a href="https://x.com">click</a></p>', "html.parser"
    ).find("p")
    plain, fmt = _extract_inline_text(tag)
    assert plain == "click"
    assert 'href="https://x.com"' in fmt

  def test_mixed_formatting(self):
    from bs4 import BeautifulSoup
    tag = BeautifulSoup(
      "<p>Plain <strong>bold</strong> and <em>italic</em></p>", "html.parser"
    ).find("p")
    plain, fmt = _extract_inline_text(tag)
    assert plain == "Plain bold and italic"
    assert "<b>bold</b>" in fmt
    assert "<i>italic</i>" in fmt

  def test_formatted_text_set_when_different(self):
    """formatted_text는 plain text와 다를 때만 설정됩니다."""
    html = _wrap_notion_html("<p><strong>bold text</strong></p>")
    result = parse_notion_html(html)
    block = result.blocks[0]
    assert block.get("formatted_text") is not None
    assert "<b>" in block["formatted_text"]

  def test_formatted_text_not_set_for_plain(self):
    """서식이 없는 텍스트에는 formatted_text가 설정되지 않습니다."""
    html = _wrap_notion_html("<p>plain text</p>")
    result = parse_notion_html(html)
    block = result.blocks[0]
    assert "formatted_text" not in block


# ── 하위 페이지 링크 수집 ────────────────────────────────────────────────────

class TestSubpageLinkCollection:
  """하위 페이지 HTML 링크 수집 테스트."""

  def test_collects_html_links(self):
    html = _wrap_notion_html(
      '<p><a href="SubPage%20UUID.html">SubPage</a></p>'
    )
    result = parse_notion_html(html)
    assert len(result.sub_page_links) == 1
    assert "SubPage UUID.html" in result.sub_page_links[0]

  def test_ignores_external_links(self):
    html = _wrap_notion_html(
      '<p><a href="https://example.com">External</a></p>'
    )
    result = parse_notion_html(html)
    assert len(result.sub_page_links) == 0

  def test_ignores_anchor_links(self):
    html = _wrap_notion_html('<p><a href="#section">Anchor</a></p>')
    result = parse_notion_html(html)
    assert len(result.sub_page_links) == 0


# ── ZIP 아카이브 처리 ────────────────────────────────────────────────────────

class TestZipProcessing:
  """ZIP 아카이브 파싱 테스트."""

  def test_parses_single_html_in_zip(self):
    html = _wrap_notion_html("<p>Content</p>", title="ZipPage")
    zip_data = _make_zip({"Page.html": html})
    result = extract_and_parse_zip(zip_data)
    assert len(result.pages) == 1
    assert result.pages[0]["title"] == "ZipPage"

  def test_parses_multiple_html_files(self):
    page1 = _wrap_notion_html("<p>Root</p>", title="Root")
    page2 = _wrap_notion_html("<p>Child</p>", title="Child")
    zip_data = _make_zip({
      "Root.html": page1,
      "Root/Child.html": page2,
    })
    result = extract_and_parse_zip(zip_data)
    assert len(result.pages) == 2

  def test_collects_images_from_zip(self):
    html = _wrap_notion_html(
      '<figure><img src="images/test.png"/></figure>',
      title="WithImage",
    )
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    zip_data = _make_zip_with_image(
      {"Page.html": html},
      {"images/test.png": fake_png},
    )
    result = extract_and_parse_zip(zip_data)
    assert len(result.image_mappings) == 1

  def test_rejects_non_zip(self):
    with pytest.raises(ValueError, match="유효하지 않은 ZIP"):
      extract_and_parse_zip(b"not a zip file")

  def test_rejects_zip_without_html(self):
    zip_data = _make_zip({"readme.txt": "no html here"})
    with pytest.raises(ValueError, match="HTML 파일이 없습니다"):
      extract_and_parse_zip(zip_data)

  def test_ignores_macosx_folder(self):
    html = _wrap_notion_html("<p>Content</p>")
    zip_data = _make_zip({
      "Page.html": html,
      "__MACOSX/._Page.html": "junk",
    })
    result = extract_and_parse_zip(zip_data)
    assert len(result.pages) == 1


class TestSingleHtmlParsing:
  """단일 HTML 파일 파싱 테스트."""

  def test_parses_single_html_bytes(self):
    html = _wrap_notion_html("<p>Solo page</p>", title="Solo")
    result = parse_single_html(html.encode("utf-8"))
    assert len(result.pages) == 1
    assert result.pages[0]["title"] == "Solo"
    assert len(result.image_mappings) == 0


# ── 변환 리포트 ──────────────────────────────────────────────────────────────

class TestConversionReport:
  """변환 리포트 생성 테스트."""

  def test_report_counts(self):
    html = _wrap_notion_html(
      "<h1>Title</h1><p>Text</p><hr/><p>  </p>"
    )
    result = parse_notion_html(html)
    report = result.report
    assert report.converted >= 3  # h1 + p + hr
    assert report.skipped >= 1    # 빈 <p>

  def test_report_to_dict(self):
    report = ConversionReport(
      total_elements=10, converted=7, fallback=2, skipped=1,
      warnings=["warning1"],
    )
    d = report.to_dict()
    assert d["total_elements"] == 10
    assert d["converted"] == 7
    assert d["warnings"] == ["warning1"]


# ── 유틸리티 함수 ────────────────────────────────────────────────────────────

class TestUtilities:
  """유틸리티 함수 테스트."""

  def test_make_block_has_uuid(self):
    block = _make_block("text", text="hello")
    assert "id" in block
    assert len(block["id"]) == 36  # UUID v4 format

  def test_is_image_file(self):
    assert _is_image_file("photo.png") is True
    assert _is_image_file("image.jpg") is True
    assert _is_image_file("pic.JPEG") is True
    assert _is_image_file("document.pdf") is False
    assert _is_image_file("script.js") is False


# ── API 엔드포인트 테스트 ────────────────────────────────────────────────────

class TestImportAPI:
  """Import API 엔드포인트 HTTP 테스트."""

  def test_import_single_html_returns_201(self, client):
    html = _wrap_notion_html("<p>API Test</p>", title="ImportedPage")
    resp = client.post(
      "/api/import/notion",
      files={"file": ("test.html", html.encode(), "text/html")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "document_id" in data
    assert data["title"] == "ImportedPage"
    assert data["total_pages"] == 1
    assert "report" in data

  def test_import_zip_returns_201(self, client):
    page1 = _wrap_notion_html("<p>Root</p>", title="ZipRoot")
    page2 = _wrap_notion_html("<p>Child</p>", title="ZipChild")
    zip_data = _make_zip({
      "Root.html": page1,
      "Root/Child.html": page2,
    })
    resp = client.post(
      "/api/import/notion",
      files={"file": ("export.zip", zip_data, "application/zip")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_pages"] == 2

  def test_import_unsupported_format_returns_415(self, client):
    resp = client.post(
      "/api/import/notion",
      files={"file": ("test.pdf", b"pdf data", "application/pdf")},
    )
    assert resp.status_code == 415

  def test_import_empty_file_returns_422(self, client):
    resp = client.post(
      "/api/import/notion",
      files={"file": ("test.html", b"", "text/html")},
    )
    assert resp.status_code == 422

  def test_import_invalid_zip_returns_422(self, client):
    resp = client.post(
      "/api/import/notion",
      files={"file": ("bad.zip", b"not a zip", "application/zip")},
    )
    assert resp.status_code == 422

  def test_imported_document_is_accessible(self, client):
    """Import된 문서가 문서 목록에서 조회 가능합니다."""
    html = _wrap_notion_html(
      "<h2>Heading</h2><p>Body text</p>",
      title="Accessible",
    )
    resp = client.post(
      "/api/import/notion",
      files={"file": ("test.html", html.encode(), "text/html")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    # 문서 조회
    doc_resp = client.get(f"/api/documents/{doc_id}")
    assert doc_resp.status_code == 200
    doc = doc_resp.json()
    assert doc["title"] == "Accessible"
    # 블록이 생성되어 있는지 확인
    assert len(doc["blocks"]) >= 2

  def test_import_preserves_block_types(self, client):
    """Import 후 블록 타입이 올바르게 보존됩니다."""
    html = _wrap_notion_html(
      "<h1>Title</h1><p>Paragraph</p><hr/>"
      '<pre class="code"><code class="language-js">code</code></pre>'
    )
    resp = client.post(
      "/api/import/notion",
      files={"file": ("test.html", html.encode(), "text/html")},
    )
    doc_id = resp.json()["document_id"]
    doc = client.get(f"/api/documents/{doc_id}").json()

    types = [b["type"] for b in doc["blocks"]]
    assert "text" in types
    assert "divider" in types
    assert "code" in types

  def test_import_creates_child_page_blocks(self, client):
    """ZIP import 시 하위 페이지가 PageBlock으로 연결됩니다."""
    root_html = _wrap_notion_html("<p>Root</p>", title="MultiRoot")
    child_html = _wrap_notion_html("<p>Child content</p>", title="ChildPage")
    zip_data = _make_zip({
      "Root.html": root_html,
      "Root/Child.html": child_html,
    })
    resp = client.post(
      "/api/import/notion",
      files={"file": ("export.zip", zip_data, "application/zip")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    # 루트 문서에 page 블록이 포함되어 있는지 확인
    doc = client.get(f"/api/documents/{doc_id}").json()
    page_blocks = [b for b in doc["blocks"] if b["type"] == "page"]
    assert len(page_blocks) >= 1

  def test_viewer_cannot_import(self, client, engine):
    """미인증 사용자는 import할 수 없습니다."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from main import app
    from app.dependencies import get_repository
    from app.repositories.sqlite_blocks import SQLiteBlockRepository

    def _override():
      with Session(engine) as s:
        yield SQLiteBlockRepository(s)

    app.dependency_overrides[get_repository] = _override
    with TestClient(app) as anon_client:
      html = _wrap_notion_html("<p>No auth</p>")
      resp = anon_client.post(
        "/api/import/notion",
        files={"file": ("test.html", html.encode(), "text/html")},
      )
      assert resp.status_code == 403
    app.dependency_overrides.clear()


# ── 복합 시나리오 테스트 ─────────────────────────────────────────────────────

class TestComplexScenarios:
  """복합 변환 시나리오 테스트."""

  def test_nested_toggle_with_code(self):
    """토글 내부에 코드 블록이 있는 구조를 변환합니다."""
    html = _wrap_notion_html(
      '<details><summary>API 예제</summary>'
      '<pre class="code"><code class="language-python">'
      'import requests\nresp = requests.get("/")'
      '</code></pre></details>'
    )
    result = parse_notion_html(html)
    toggle = result.blocks[0]
    assert toggle["type"] == "toggle"
    code_children = [c for c in toggle["children"] if c["type"] == "code"]
    assert len(code_children) == 1
    assert "import requests" in code_children[0]["code"]

  def test_mixed_content_page(self):
    """다양한 블록 타입이 혼합된 페이지 변환."""
    html = _wrap_notion_html("""
      <h1>Main Title</h1>
      <p>Introduction paragraph.</p>
      <ul class="bulleted-list"><li>Point A</li><li>Point B</li></ul>
      <hr/>
      <blockquote><p>A quote from someone</p></blockquote>
      <pre class="code"><code>console.log('hello')</code></pre>
    """)
    result = parse_notion_html(html)
    types = [b["type"] for b in result.blocks]
    assert "text" in types
    assert "divider" in types
    assert "quote" in types
    assert "code" in types
    assert result.report.converted >= 5

  def test_callout_with_custom_emoji(self):
    """커스텀 이모지가 있는 콜아웃 변환."""
    html = _wrap_notion_html(
      '<figure class="callout">'
      '<span class="icon">🔥</span>'
      '<div class="callout-body"><p>Important note</p></div>'
      '</figure>'
    )
    result = parse_notion_html(html)
    block = result.blocks[0]
    assert block["type"] == "callout"
    assert block["emoji"] == "🔥"

  def test_deep_nested_list(self):
    """중첩 리스트 변환."""
    html = _wrap_notion_html(
      '<ul class="bulleted-list">'
      '<li>Level 1<ul><li>Level 2</li></ul></li>'
      '</ul>'
    )
    result = parse_notion_html(html)
    # Level 1 + Level 2 = 2 blocks
    assert len(result.blocks) >= 2
