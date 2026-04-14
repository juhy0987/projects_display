"""Notion Import 기능 단위 테스트.

테스트 범위:
  1. HTML 파서 서비스 — 각 블록 타입 변환 정확도
  2. 인라인 서식 변환 — bold, italic, link 등
  3. ZIP 아카이브 처리 — 다중 페이지 구조 변환, 이중 ZIP
  4. Import API 엔드포인트 — HTTP 상태 코드 및 응답 구조
  5. 에러 처리 — 잘못된 파일 형식, 빈 파일, 큰 파일
  6. Markdown 파서 서비스 — 각 블록 타입 변환
  7. CSV 데이터베이스 파싱
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
  _flatten_zip,
  _is_image_file,
  _make_block,
  _md_convert_inline,
  _coerce_cell_value,
  _infer_column_type,
  _parse_csv_to_database,
  extract_and_parse_zip,
  parse_notion_html,
  parse_notion_markdown,
  parse_single_html,
  parse_single_markdown,
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

  def test_rejects_zip_without_content(self):
    zip_data = _make_zip({"readme.txt": "no content here"})
    with pytest.raises(ValueError, match="변환 가능한 파일"):
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


# ── Markdown 파서 테스트 ─────────────────────────────────────────────────────

class TestMarkdownTitle:
  """Markdown 제목 추출 테스트."""

  def test_extracts_h1_title(self):
    result = parse_notion_markdown("# My Page\n\nSome text")
    assert result.title == "My Page"

  def test_untitled_when_no_h1(self):
    result = parse_notion_markdown("Some text without heading")
    assert result.title == "Untitled"


class TestMarkdownHeadings:
  """Markdown 제목 블록 변환 테스트."""

  def test_h2_becomes_level_2(self):
    result = parse_notion_markdown("# Title\n\n## Section")
    h2_blocks = [b for b in result.blocks if b.get("level") == 2]
    assert len(h2_blocks) == 1
    assert h2_blocks[0]["text"] == "Section"

  def test_h3_becomes_level_3(self):
    result = parse_notion_markdown("# Title\n\n### Subsection")
    h3_blocks = [b for b in result.blocks if b.get("level") == 3]
    assert len(h3_blocks) == 1


class TestMarkdownParagraph:
  """Markdown 단락 변환 테스트."""

  def test_plain_paragraph(self):
    result = parse_notion_markdown("# Title\n\nHello world")
    text_blocks = [b for b in result.blocks if b["type"] == "text" and not b.get("level")]
    assert len(text_blocks) == 1
    assert text_blocks[0]["text"] == "Hello world"


class TestMarkdownLists:
  """Markdown 리스트 변환 테스트."""

  def test_bulleted_list(self):
    result = parse_notion_markdown("# T\n\n- Apple\n- Banana")
    bullets = [b for b in result.blocks if "•" in b.get("text", "")]
    assert len(bullets) == 2
    assert "Apple" in bullets[0]["text"]

  def test_numbered_list(self):
    result = parse_notion_markdown("# T\n\n1. First\n2. Second")
    nums = [b for b in result.blocks if b.get("text", "").startswith(("1.", "2."))]
    assert len(nums) == 2

  def test_todo_checked(self):
    result = parse_notion_markdown("# T\n\n- [x] Done task")
    assert any("☑" in b.get("text", "") for b in result.blocks)

  def test_todo_unchecked(self):
    result = parse_notion_markdown("# T\n\n- [ ] Pending task")
    assert any("☐" in b.get("text", "") for b in result.blocks)


class TestMarkdownCodeBlock:
  """Markdown 코드 블록 변환 테스트."""

  def test_fenced_code_with_language(self):
    md = "# T\n\n```python\nprint('hello')\n```"
    result = parse_notion_markdown(md)
    code_blocks = [b for b in result.blocks if b["type"] == "code"]
    assert len(code_blocks) == 1
    assert code_blocks[0]["language"] == "python"
    assert "print('hello')" in code_blocks[0]["code"]

  def test_fenced_code_without_language(self):
    md = "# T\n\n```\nplain text\n```"
    result = parse_notion_markdown(md)
    code_blocks = [b for b in result.blocks if b["type"] == "code"]
    assert code_blocks[0]["language"] == "plain"


class TestMarkdownQuote:
  """Markdown 인용문 변환 테스트."""

  def test_blockquote(self):
    result = parse_notion_markdown("# T\n\n> A wise saying")
    quotes = [b for b in result.blocks if b["type"] == "quote"]
    assert len(quotes) == 1
    assert "A wise saying" in quotes[0]["text"]


class TestMarkdownDivider:
  """Markdown 구분선 변환 테스트."""

  def test_hr(self):
    result = parse_notion_markdown("# T\n\n---")
    dividers = [b for b in result.blocks if b["type"] == "divider"]
    assert len(dividers) == 1


class TestMarkdownImage:
  """Markdown 이미지 변환 테스트."""

  def test_image(self):
    result = parse_notion_markdown("# T\n\n![caption](images/photo.png)")
    imgs = [b for b in result.blocks if b["type"] == "image"]
    assert len(imgs) == 1
    assert "photo.png" in imgs[0]["url"]
    assert imgs[0]["caption"] == "caption"


class TestMarkdownInline:
  """Markdown 인라인 서식 변환 테스트."""

  def test_bold(self):
    plain, fmt = _md_convert_inline("**bold text**")
    assert plain == "bold text"
    assert fmt == "<b>bold text</b>"

  def test_italic(self):
    plain, fmt = _md_convert_inline("*italic*")
    assert plain == "italic"
    assert fmt == "<i>italic</i>"

  def test_strikethrough(self):
    plain, fmt = _md_convert_inline("~~deleted~~")
    assert plain == "deleted"
    assert fmt == "<s>deleted</s>"

  def test_inline_code(self):
    plain, fmt = _md_convert_inline("`code`")
    assert plain == "code"
    assert fmt == "<code>code</code>"

  def test_link(self):
    plain, fmt = _md_convert_inline("[click](https://x.com)")
    assert plain == "click"
    assert 'href="https://x.com"' in fmt

  def test_no_formatting_returns_none(self):
    plain, fmt = _md_convert_inline("plain text")
    assert plain == "plain text"
    assert fmt is None


class TestMarkdownSubpageLinks:
  """Markdown 하위 페이지 링크 수집 테스트."""

  def test_collects_md_links(self):
    md = "# T\n\n- [SubPage](SubPage%20UUID.md)"
    result = parse_notion_markdown(md)
    assert len(result.sub_page_links) == 1
    assert "SubPage UUID.md" in result.sub_page_links[0]


# ── 이중 ZIP 처리 테스트 ─────────────────────────────────────────────────────

class TestNestedZip:
  """이중 ZIP (ZIP 내부 ZIP) 추출 테스트."""

  def test_flatten_nested_zip(self):
    """내부 ZIP을 자동으로 해제합니다."""
    inner_zip = _make_zip({"page.md": "# Hello\n\nWorld"})
    outer_zip = _make_zip({"Export-Part-1.zip": inner_zip.decode("latin-1")})
    # 바이너리로 직접 생성
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as zf:
      zf.writestr("page.md", "# Hello\n\nWorld")
    outer_buf = io.BytesIO()
    with zipfile.ZipFile(outer_buf, "w") as zf:
      zf.writestr("Export-Part-1.zip", inner_buf.getvalue())

    files = _flatten_zip(outer_buf.getvalue())
    assert "page.md" in files
    assert b"# Hello" in files["page.md"]

  def test_extract_and_parse_nested_zip(self):
    """이중 ZIP에서 Markdown 파일을 파싱합니다."""
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as zf:
      zf.writestr("Root/page.md", "# Test Page\n\nContent here")
    outer_buf = io.BytesIO()
    with zipfile.ZipFile(outer_buf, "w") as zf:
      zf.writestr("Export-Part-1.zip", inner_buf.getvalue())

    result = extract_and_parse_zip(outer_buf.getvalue())
    assert len(result.pages) == 1
    assert result.pages[0]["title"] == "Test Page"

  def test_crc_corrupted_zip_entry_recovers(self, monkeypatch):
    """CRC 검증 실패 엔트리도 우회해서 추출합니다.

    Notion export ZIP에서 종종 발생하는 CRC mismatch 케이스에 대한 fallback.
    """
    import zipfile as zf_mod
    from app.services import notion_import as ni

    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as zf:
      zf.writestr("page.md", "# CRC Test\n\nContent")
    outer_buf = io.BytesIO()
    with zipfile.ZipFile(outer_buf, "w") as zf:
      zf.writestr("Part-1.zip", inner_buf.getvalue())

    # 첫 번째 zf.read() 호출에서 BadZipFile(CRC) 예외를 발생시킨다
    original_read = zf_mod.ZipFile.read
    call_count = {"n": 0}

    def fake_read(self, name, pwd=None):
      call_count["n"] += 1
      if call_count["n"] == 1:
        raise zf_mod.BadZipFile(f"Bad CRC-32 for file {name!r}")
      return original_read(self, name, pwd)

    monkeypatch.setattr(zf_mod.ZipFile, "read", fake_read)

    # CRC 우회 경로가 발동되어도 정상 추출되어야 함
    result = ni.extract_and_parse_zip(outer_buf.getvalue())
    assert len(result.pages) == 1
    assert result.pages[0]["title"] == "CRC Test"

  def test_nested_zip_depth_limit(self):
    """과도한 중첩 ZIP은 차단합니다 (ZIP Bomb 방어)."""
    from app.services import notion_import as ni

    # MAX_NESTED_ZIP_DEPTH + 2 단계의 중첩 ZIP 생성
    payload = b"# Inner\n\nContent"
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
      zf.writestr("page.md", payload)
    payload = inner.getvalue()

    for _ in range(ni.MAX_NESTED_ZIP_DEPTH + 2):
      buf = io.BytesIO()
      with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("nested.zip", payload)
      payload = buf.getvalue()

    with pytest.raises(ValueError, match="중첩 깊이"):
      ni._flatten_zip(payload)

  def test_zip_compression_ratio_limit(self):
    """비정상적인 압축비는 차단합니다 (ZIP Bomb 방어)."""
    from app.services import notion_import as ni

    # 1MB 영(0) 바이트 데이터를 ZIP — 매우 높은 압축비
    huge_zeros = b"\x00" * (1024 * 1024)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
      zf.writestr("zeros.bin", huge_zeros)

    with pytest.raises(ValueError, match="압축비"):
      ni._flatten_zip(buf.getvalue())

  def test_nested_zip_with_images(self):
    """이중 ZIP에서 이미지를 추출합니다."""
    fake_png = b"\x89PNG" + b"\x00" * 50
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as zf:
      zf.writestr("Root/page.md", "# T\n\n![img](page/image.png)")
      zf.writestr("Root/page/image.png", fake_png)
    outer_buf = io.BytesIO()
    with zipfile.ZipFile(outer_buf, "w") as zf:
      zf.writestr("Part-1.zip", inner_buf.getvalue())

    result = extract_and_parse_zip(outer_buf.getvalue())
    assert len(result.image_mappings) == 1


# ── CSV 파싱 테스트 ──────────────────────────────────────────────────────────

class TestCsvParsing:
  """CSV → DatabaseBlock 파싱 테스트 (이슈 #69: Notion DB 연계 정합성)."""

  def test_csv_to_database_block(self):
    """CSV가 database 블록(+ db_row children)으로 변환된다."""
    csv_text = "Name,Score\nAlice,100\nBob,95"
    db = _parse_csv_to_database(csv_text, title="Scores")

    assert db is not None
    assert db["type"] == "database"
    assert db["title"] == "Scores"
    assert db["color"] == "default"
    assert len(db["columns"]) == 2
    assert db["columns"][0]["name"] == "Name"
    assert db["columns"][1]["name"] == "Score"
    # 각 컬럼에 고유 id가 부여되어야 한다
    col_ids = [c["id"] for c in db["columns"]]
    assert len(set(col_ids)) == 2

    rows = db["children"]
    assert len(rows) == 2
    assert all(r["type"] == "db_row" for r in rows)
    # 제목은 첫 컬럼(Name) 값에서 파생
    assert rows[0]["title"] == "Alice"
    assert rows[1]["title"] == "Bob"
    # properties는 column_id → 값 매핑
    name_id, score_id = col_ids
    assert rows[0]["properties"][name_id] == "Alice"
    # Score는 숫자 컬럼으로 추론되어 int로 coerce
    assert rows[0]["properties"][score_id] == 100

  def test_empty_csv_returns_none(self):
    assert _parse_csv_to_database("", title="X") is None
    # 공백만 있는 CSV도 None
    assert _parse_csv_to_database("\n,\n", title="X") is None

  def test_header_only_csv(self):
    """헤더만 있는 CSV도 빈 database로 생성된다(스키마만 유지)."""
    db = _parse_csv_to_database("A,B", title="Empty")
    assert db is not None
    assert len(db["columns"]) == 2
    assert db["children"] == []

  def test_column_name_fallback(self):
    """헤더가 비어있으면 Column N 으로 대체된다."""
    db = _parse_csv_to_database(",Score\n,10", title="X")
    assert db is not None
    assert db["columns"][0]["name"] == "Column 1"
    assert db["columns"][1]["name"] == "Score"

  def test_ragged_rows_are_filled(self):
    """열 수가 부족한 행은 빈 값으로 채워진다(데이터 유실 방지)."""
    db = _parse_csv_to_database("A,B,C\n1,2\n3,4,5", title="X")
    assert db is not None
    row0 = db["children"][0]["properties"]
    ids = [c["id"] for c in db["columns"]]
    # 세 번째 컬럼은 빈 값
    assert row0[ids[2]] in ("", None)

  def test_infer_column_type_number(self):
    assert _infer_column_type(["1", "2", "3.14"]) == "number"
    # 천 단위 콤마 허용
    assert _infer_column_type(["1,000", "2,500"]) == "number"

  def test_infer_column_type_checkbox(self):
    assert _infer_column_type(["Yes", "No", "yes"]) == "checkbox"
    assert _infer_column_type(["true", "false"]) == "checkbox"
    # "0"/"1" 만 있는 컬럼은 숫자 파싱 가능하더라도 checkbox 로 우선 판정
    assert _infer_column_type(["0", "1", "1", "0"]) == "checkbox"
    assert _infer_column_type(["1", "1"]) == "checkbox"
    # 2 이상의 숫자가 섞이면 checkbox 토큰 집합을 벗어나 number 유지
    assert _infer_column_type(["0", "1", "2"]) == "number"

  def test_infer_column_type_text_default(self):
    assert _infer_column_type(["Alice", "Bob"]) == "text"
    # 일부만 숫자면 text
    assert _infer_column_type(["1", "two"]) == "text"
    # 빈 값만 있는 경우도 text
    assert _infer_column_type(["", ""]) == "text"

  def test_coerce_cell_value(self):
    assert _coerce_cell_value("42", "number") == 42
    assert _coerce_cell_value("3.14", "number") == 3.14
    assert _coerce_cell_value("", "number") is None
    # 숫자로 변환 실패 시 원본 유지 (폴백)
    assert _coerce_cell_value("N/A", "number") == "N/A"
    assert _coerce_cell_value("Yes", "checkbox") is True
    assert _coerce_cell_value("No", "checkbox") is False
    assert _coerce_cell_value("Hello", "text") == "Hello"

  def test_csv_in_zip_attached_as_database(self):
    """ZIP 내 CSV가 부모 페이지에 database 블록으로 추가된다."""
    md_content = "# Project\n\n- [DB](DB%20aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.csv)"
    csv_content = "Task,Status\nDo thing,Done"
    zip_data = _make_zip({
      "Root/page.md": md_content,
      "Root/DB aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.csv": csv_content,
    })
    result = extract_and_parse_zip(zip_data)
    all_blocks = []
    for page in result.pages:
      all_blocks.extend(page["blocks"])
    db_blocks = [b for b in all_blocks if b.get("type") == "database"]
    assert len(db_blocks) == 1
    assert db_blocks[0]["title"] == "DB"
    assert [c["name"] for c in db_blocks[0]["columns"]] == ["Task", "Status"]
    assert len(db_blocks[0]["children"]) == 1

  def test_row_pages_absorbed_into_db_rows(self):
    """CSV 동반 row .md 파일이 db_row의 children으로 흡수된다.

    동일 행이 부모 페이지의 하위 PageBlock 과 database 의 db_row 로
    중복 생성되면 안 된다 (이슈 #69).
    """
    uuid_hash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    row_uuid = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    md_parent = f"# Project\n\n- [Tasks](Tasks%20{uuid_hash}.csv)"
    md_row_a = "# Task A\n\nDetail for A"
    csv_content = "Name,Status\nTask A,Done\nTask B,Todo"
    # Notion export 의 실제 레이아웃: 동반 디렉터리에는 UUID 해시가 없다.
    zip_data = _make_zip({
      "Root/page.md": md_parent,
      f"Root/Tasks {uuid_hash}.csv": csv_content,
      f"Root/Tasks/Task A {row_uuid}.md": md_row_a,
    })
    result = extract_and_parse_zip(zip_data)

    # row 페이지는 pages 리스트에서 제거되어 있어야 한다
    remaining_paths = [p["path"] for p in result.pages]
    assert not any("Task A" in path for path in remaining_paths)

    # database 블록의 Task A 행 children 에 원본 블록이 흡수되어야 한다
    db_blocks = [b for p in result.pages for b in p["blocks"]
                 if b.get("type") == "database"]
    assert len(db_blocks) == 1
    rows_by_title = {r["title"]: r for r in db_blocks[0]["children"]}
    assert set(rows_by_title) == {"Task A", "Task B"}
    # 흡수된 Task A는 "Detail for A" 텍스트 블록을 children 으로 가진다
    assert any(
      b.get("type") == "text" and "Detail for A" in b.get("text", "")
      for b in rows_by_title["Task A"]["children"]
    )
    # 매칭 페이지가 없는 Task B 는 children 이 비어있다 (신규 생성)
    assert rows_by_title["Task B"]["children"] == []

  def test_row_page_absorbed_with_korean_real_notion_layout(self):
    """Notion 실제 export 레이아웃 회귀 테스트.

    예: "범진님이 주신 팁" 페이지가 "자료 정리 <uuid>.csv" 데이터베이스에
    속하는 형태. CSV 와 같은 디렉터리에 UUID 없는 이름의 자매 폴더가 있고,
    그 안에 row 상세 md 가 위치한다.
    """
    csv_uuid = "2b7b6f198639811fa1c1de11af2a0139"
    row_uuid = "2b7b6f1986398128874fe950e502335a"
    csv_rel = f"자료 정리 {csv_uuid}.csv"
    parent_md = f"# 푸항항\n\n- [자료 정리]({csv_rel.replace(' ', '%20')})"
    row_md = "# 범진님이 주신 팁\n\n실전 팁 본문"
    csv_body = "이름,카테고리\n범진님이 주신 팁,팁"

    zip_data = _make_zip({
      "푸항항.md": parent_md,
      f"푸항항/{csv_rel}": csv_body,
      f"푸항항/자료 정리/범진님이 주신 팁 {row_uuid}.md": row_md,
    })
    result = extract_and_parse_zip(zip_data)

    # row 페이지는 독립 페이지로 남아있지 않아야 한다
    remaining_titles = [p["title"] for p in result.pages]
    assert "범진님이 주신 팁" not in remaining_titles

    db_blocks = [b for p in result.pages for b in p["blocks"]
                 if b.get("type") == "database"]
    assert len(db_blocks) == 1
    rows_by_title = {r["title"]: r for r in db_blocks[0]["children"]}
    assert "범진님이 주신 팁" in rows_by_title
    # 흡수된 행의 children 에 본문 텍스트가 포함된다
    assert any(
      "실전 팁 본문" in b.get("text", "")
      for b in rows_by_title["범진님이 주신 팁"]["children"]
    )

  def test_duplicate_row_titles_do_not_share_block_ids(self):
    """같은 title 의 db_row 가 여러 개여도 block id 가 중복되지 않는다.

    각 row 페이지는 최대 하나의 db_row 에만 흡수되어야 한다
    (pop 기반 1:1 매칭). list 참조 공유는 영속화 시 UNIQUE 제약 충돌을
    일으키므로 block id 집합 중복이 없음을 검증한다.
    """
    from collections import Counter

    uuid_hash = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    row_uuid_a = "11111111111111111111111111111111"
    # CSV 에 같은 title 이 두 번 등장 (Notion 에서는 드물지만 가능)
    csv_body = "Name,Status\nDup,Done\nDup,Todo"
    zip_data = _make_zip({
      "Root/page.md": f"# P\n\n- [T](T%20{uuid_hash}.csv)",
      f"Root/T {uuid_hash}.csv": csv_body,
      f"Root/T/Dup {row_uuid_a}.md": "# Dup\n\nOnly one detail page",
    })
    result = extract_and_parse_zip(zip_data)

    ids: list[str] = []
    def walk(bs):
      for b in bs:
        if b.get("id"):
          ids.append(b["id"])
        for c in b.get("children") or []:
          walk([c])
    for p in result.pages:
      walk(p["blocks"])
    assert not [k for k, v in Counter(ids).items() if v > 1], (
      "파싱 결과에 동일 block id 가 중복 등장해선 안 된다"
    )

  def test_duplicate_title_pages_all_absorbed(self):
    """CSV 에 동일 title 의 row 가 여러 개이면 해당 수만큼 페이지가 흡수된다.

    기존 setdefault 로직은 첫 페이지만 매칭되어 나머지가 잔류했다.
    Notion 회의록 DB 의 "백엔드 정기 멘토링" 처럼 반복되는 이름에 대응.
    """
    uuid_hash = "f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0"
    uuid_a = "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1"
    uuid_b = "a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2"
    uuid_c = "a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3"
    csv_body = "Name,When\nMtg,D1\nMtg,D2\nMtg,D3"
    zip_data = _make_zip({
      "Root/page.md": f"# P\n\n- [M](M%20{uuid_hash}.csv)",
      f"Root/M {uuid_hash}.csv": csv_body,
      f"Root/M/Mtg {uuid_a}.md": "# Mtg\n\nalpha",
      f"Root/M/Mtg {uuid_b}.md": "# Mtg\n\nbravo",
      f"Root/M/Mtg {uuid_c}.md": "# Mtg\n\ncharlie",
    })
    result = extract_and_parse_zip(zip_data)
    # 잔류 없음
    assert not [p for p in result.pages if p["title"] == "Mtg"]
    # 세 db_row 모두 고유 상세 블록을 가진다
    db = next(b for p in result.pages for b in p["blocks"] if b.get("type") == "database")
    texts = []
    for row in db["children"]:
      for child in row["children"]:
        if child.get("type") == "text":
          texts.append(child.get("text", ""))
    assert {"alpha", "bravo", "charlie"} <= set(texts)

  def test_orphan_companion_pages_promoted_to_db_rows(self):
    """CSV 에 대응 row 가 없는 동반 디렉터리 페이지도 합성 db_row 로 승격된다.

    Notion 의 뷰 필터/이동 등으로 CSV 와 상세 페이지 수가 어긋날 수 있다.
    이런 orphan 도 DB 영역 외부로 새지 않고 database 블록 내부 row 로 흡수해야 한다.
    """
    uuid_hash = "b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0"
    orphan_uuid = "c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0"
    csv_body = "Name,Tag\nAlice,x"  # Bob 없음
    zip_data = _make_zip({
      "Root/page.md": f"# P\n\n- [D](D%20{uuid_hash}.csv)",
      f"Root/D {uuid_hash}.csv": csv_body,
      f"Root/D/Alice {orphan_uuid}.md": "# Alice\n\nhello",
      f"Root/D/Bob {orphan_uuid[::-1]}.md": "# Bob\n\norphan body",
    })
    result = extract_and_parse_zip(zip_data)
    # 잔류 페이지 없음
    assert not [p for p in result.pages if p["title"] in ("Alice", "Bob")]
    db = next(b for p in result.pages for b in p["blocks"] if b.get("type") == "database")
    row_titles = [r["title"] for r in db["children"]]
    assert row_titles == ["Alice", "Bob"]  # Bob 은 끝에 추가된 합성 row
    bob = next(r for r in db["children"] if r["title"] == "Bob")
    # 합성 row 의 properties 는 컬럼 id 를 키로, 타입별 기본값으로 채워진다
    # (_coerce_cell_value 와 동일 규칙: text→"", number→None, checkbox→False)
    assert set(bob["properties"].keys()) == {c["id"] for c in db["columns"]}
    for col in db["columns"]:
      expected = {"text": "", "number": None, "checkbox": False}[col["type"]]
      assert bob["properties"][col["id"]] == expected
    # 원본 상세 블록을 children 으로 가진다
    assert any("orphan body" in b.get("text", "") for b in bob["children"])

  def test_row_pages_merged_end_to_end(self, client):
    """API 전체 플로우: row 페이지가 db_row 에만 존재하고 트리에 중복되지 않는다."""
    uuid_hash = "cccccccccccccccccccccccccccccccc"
    row_uuid = "dddddddddddddddddddddddddddddddd"
    zip_data = _make_zip({
      "Root/page.md": f"# Parent\n\n- [Tasks](Tasks%20{uuid_hash}.csv)",
      f"Root/Tasks {uuid_hash}.csv": "Name,Score\nAlice,100",
      f"Root/Tasks/Alice {row_uuid}.md": "# Alice\n\nhello",
    })
    resp = client.post(
      "/api/import/notion",
      files={"file": ("export.zip", zip_data, "application/zip")},
    )
    assert resp.status_code == 201
    doc = client.get(f"/api/documents/{resp.json()['document_id']}").json()

    # 루트 문서에는 page 블록(=row 페이지 참조)이 없어야 한다 — db 블록 하나만.
    block_types = [b["type"] for b in doc["blocks"]]
    assert "database" in block_types
    assert "page" not in block_types

    # db_row 는 있고, 그 문서를 조회하면 "hello" 블록이 존재한다.
    db = next(b for b in doc["blocks"] if b["type"] == "database")
    assert len(db["rows"]) == 1
    row_doc = client.get(f"/api/documents/{db['rows'][0]['document_id']}").json()
    assert any("hello" in b.get("text", "") for b in row_doc["blocks"])

  def test_all_csv_excluded(self):
    """_all.csv 파일은 중복이므로 제외된다."""
    zip_data = _make_zip({
      "Root/page.md": "# Title\n\nText",
      "Root/DB aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.csv": "A,B\n1,2",
      "Root/DB abc123_all.csv": "A,B\n1,2",
    })
    result = extract_and_parse_zip(zip_data)
    db_blocks = [b for page in result.pages
                 for b in page["blocks"]
                 if b.get("type") == "database"]
    assert len(db_blocks) == 1


# ── Markdown ZIP import API 테스트 ──────────────────────────────────────────

class TestMarkdownImportAPI:
  """Markdown 관련 Import API 테스트."""

  def test_import_single_md_returns_201(self, client):
    md = "# MD Page\n\nSome content\n\n- Item 1\n- Item 2"
    resp = client.post(
      "/api/import/notion",
      files={"file": ("page.md", md.encode(), "text/markdown")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "MD Page"
    assert data["total_pages"] == 1

  def test_import_md_zip_returns_201(self, client):
    """Markdown ZIP import 테스트."""
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as zf:
      zf.writestr("Root/page.md", "# ZipMD\n\nContent")
    outer_buf = io.BytesIO()
    with zipfile.ZipFile(outer_buf, "w") as zf:
      zf.writestr("Part-1.zip", inner_buf.getvalue())

    resp = client.post(
      "/api/import/notion",
      files={"file": ("export.zip", outer_buf.getvalue(), "application/zip")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "ZipMD"

  def test_import_md_preserves_block_types(self, client):
    md = "# Title\n\nParagraph\n\n---\n\n```js\nconsole.log()\n```"
    resp = client.post(
      "/api/import/notion",
      files={"file": ("test.md", md.encode(), "text/markdown")},
    )
    doc_id = resp.json()["document_id"]
    doc = client.get(f"/api/documents/{doc_id}").json()
    types = [b["type"] for b in doc["blocks"]]
    assert "text" in types
    assert "divider" in types
    assert "code" in types


# ── CSV → DatabaseBlock 영속화 통합 테스트 ─────────────────────────────────────

class TestCsvDatabasePersistence:
  """import_pages가 database/db_row 블록을 올바르게 영속화하는지 검증한다.

  이슈 #69 DoD: Notion 연계 시나리오에서 DB 동작이 기대값과 일치한다.
  """

  def _build_zip(self, csv_content: str) -> bytes:
    """페이지 + CSV로 구성된 최소 Notion export ZIP을 생성한다."""
    md_content = (
      "# Project\n\n- [DB](DB%20aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.csv)"
    )
    return _make_zip({
      "Root/page.md": md_content,
      "Root/DB aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.csv": csv_content,
    })

  def test_import_creates_database_block_with_rows(self, client):
    zip_data = self._build_zip("Name,Score\nAlice,100\nBob,95")
    resp = client.post(
      "/api/import/notion",
      files={"file": ("export.zip", zip_data, "application/zip")},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]
    doc = client.get(f"/api/documents/{doc_id}").json()

    db_blocks = [b for b in doc["blocks"] if b["type"] == "database"]
    assert len(db_blocks) == 1
    db = db_blocks[0]
    assert db["title"] == "DB"
    assert [c["name"] for c in db["columns"]] == ["Name", "Score"]
    assert [c["type"] for c in db["columns"]] == ["text", "number"]
    # db_row는 database의 자식으로 복원된다(DatabaseBlock.rows)
    assert len(db["rows"]) == 2
    row_titles = sorted(r["title"] for r in db["rows"])
    assert row_titles == ["Alice", "Bob"]

  def test_db_rows_have_child_documents(self, client):
    """각 db_row는 자체 문서를 가지며 properties가 보존된다."""
    zip_data = self._build_zip("Name,Done\nTask A,Yes\nTask B,No")
    resp = client.post(
      "/api/import/notion",
      files={"file": ("export.zip", zip_data, "application/zip")},
    )
    doc_id = resp.json()["document_id"]
    doc = client.get(f"/api/documents/{doc_id}").json()
    db = next(b for b in doc["blocks"] if b["type"] == "database")
    done_col_id = next(c["id"] for c in db["columns"] if c["name"] == "Done")

    # checkbox 타입으로 추론되어 bool로 coerce
    done_values = {r["title"]: r["properties"][done_col_id] for r in db["rows"]}
    assert done_values == {"Task A": True, "Task B": False}

    # 각 행은 독립 문서이므로 GET /api/documents/<row.document_id>이 200
    for row in db["rows"]:
      row_doc = client.get(f"/api/documents/{row['document_id']}")
      assert row_doc.status_code == 200
