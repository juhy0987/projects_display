"""Notion Export를 프로젝트 블록 구조로 변환하는 파서 서비스.

Notion Export 포맷 (HTML / Markdown+CSV 양쪽 지원):
  HTML Export:
    - 각 페이지는 독립 HTML 파일로 export됨
    - 페이지 제목은 <header><h1 class="page-title"> 에 위치
    - 본문은 <div class="page-body"> 내부의 HTML 요소들로 구성

  Markdown Export:
    - 각 페이지는 독립 .md 파일로 export됨
    - 데이터베이스는 .csv 파일로 export됨
    - 이미지는 페이지 이름과 동일한 하위 폴더에 저장됨
    - 하위 페이지는 같은 폴더 내 별도 .md 파일로 [text](path) 링크됨

  ZIP 구조:
    - Notion export ZIP은 내부에 Part-N.zip을 포함할 수 있음 (이중 ZIP)
    - 자동으로 내부 ZIP을 해제하여 콘텐츠를 추출함

지원 블록 매핑:
  완전 지원 — heading(h1-h3), paragraph, bulleted/numbered list, to-do,
              toggle, quote, code, callout, divider, image, bookmark
  부분 지원 — table/CSV(텍스트 기반 렌더링), column layout(순차 렌더링)
  미지원   — embed, synced block, equation (fallback 텍스트 처리)

참고:
  - Notion Help: https://www.notion.so/help/export-your-content
  - BeautifulSoup 4 docs: https://www.crummy.com/software/BeautifulSoup/bs4/doc/
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote

from bs4 import BeautifulSoup, NavigableString, Tag

logger = logging.getLogger(__name__)


# ── 변환 리포트 ─────────────────────────────────────────────────────────────────

@dataclass
class ConversionReport:
  """Import 변환 결과 리포트.

  변환 성공·fallback·누락 항목을 추적하여
  사용자에게 투명한 결과 안내를 제공합니다.
  """

  total_elements: int = 0
  converted: int = 0
  fallback: int = 0
  skipped: int = 0
  warnings: list[str] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {
      "total_elements": self.total_elements,
      "converted": self.converted,
      "fallback": self.fallback,
      "skipped": self.skipped,
      "warnings": self.warnings,
    }


# ── 인라인 서식 변환 ────────────────────────────────────────────────────────────

# Notion HTML에서 사용되는 인라인 서식 태그와 프로젝트 formatted_text 마크업 매핑
# Ref: Notion export는 <strong>, <em>, <del>, <code> 등 표준 HTML 태그를 사용
_INLINE_TAG_MAP: dict[str, tuple[str, str]] = {
  "b":      ("<b>", "</b>"),
  "strong": ("<b>", "</b>"),
  "i":      ("<i>", "</i>"),
  "em":     ("<i>", "</i>"),
  "u":      ("<u>", "</u>"),
  "s":      ("<s>", "</s>"),
  "del":    ("<s>", "</s>"),
  "strike": ("<s>", "</s>"),
  "code":   ("<code>", "</code>"),
  "mark":   ("<mark>", "</mark>"),
}


def _extract_inline_text(element: Tag | NavigableString) -> tuple[str, str]:
  """HTML 요소에서 plain text와 formatted_text를 재귀적으로 추출합니다.

  Args:
    element: BeautifulSoup 파싱된 HTML 요소.

  Returns:
    (plain_text, formatted_text) 튜플.
    formatted_text는 인라인 서식(<b>, <i>, <u> 등)이 보존된 문자열.
  """
  if isinstance(element, NavigableString):
    text = str(element)
    return text, text

  plain_parts: list[str] = []
  formatted_parts: list[str] = []

  for child in element.children:
    if isinstance(child, NavigableString):
      text = str(child)
      plain_parts.append(text)
      formatted_parts.append(text)
    elif isinstance(child, Tag):
      child_plain, child_fmt = _extract_inline_text(child)
      plain_parts.append(child_plain)

      tag_name = child.name.lower()
      if tag_name == "a":
        href = child.get("href", "")
        formatted_parts.append(f'<a href="{href}">{child_fmt}</a>')
      elif tag_name == "br":
        plain_parts.append("\n")
        formatted_parts.append("\n")
      elif tag_name in _INLINE_TAG_MAP:
        open_tag, close_tag = _INLINE_TAG_MAP[tag_name]
        formatted_parts.append(f"{open_tag}{child_fmt}{close_tag}")
      else:
        # span 등 서식 없는 래퍼 — 내용만 전달
        formatted_parts.append(child_fmt)

  plain = "".join(plain_parts)
  formatted = "".join(formatted_parts)
  return plain, formatted


# ── 블록 변환 함수들 ────────────────────────────────────────────────────────────

def _make_block(block_type: str, **content: Any) -> dict[str, Any]:
  """블록 dict를 생성합니다. id는 UUID v4로 자동 할당됩니다."""
  return {"id": str(uuid.uuid4()), "type": block_type, **content}


def _parse_heading(tag: Tag) -> dict[str, Any]:
  """<h1>-<h3> 태그를 TextBlock(level=1-3)으로 변환합니다."""
  level_map = {"h1": 1, "h2": 2, "h3": 3}
  level = level_map.get(tag.name.lower(), 1)
  plain, formatted = _extract_inline_text(tag)
  block = _make_block("text", text=plain, level=level)
  if formatted != plain:
    block["formatted_text"] = formatted
  return block


def _parse_paragraph(tag: Tag) -> dict[str, Any] | None:
  """<p> 태그를 TextBlock으로 변환합니다. 빈 단락은 None을 반환합니다."""
  plain, formatted = _extract_inline_text(tag)
  if not plain.strip():
    return None
  block = _make_block("text", text=plain)
  if formatted != plain:
    block["formatted_text"] = formatted
  return block


def _parse_list(tag: Tag, report: ConversionReport) -> list[dict[str, Any]]:
  """<ul>/<ol> 태그의 각 <li>를 개별 TextBlock으로 변환합니다.

  Notion HTML 리스트 구조:
    <ul class="bulleted-list"> / <ol class="numbered-list">
      <li> ... </li>

  To-do 리스트 (<ul class="to-do-list">):
    <li><div class="checkbox checkbox-on/off">
  """
  blocks: list[dict[str, Any]] = []
  is_todo = "to-do-list" in (tag.get("class") or [])
  is_numbered = tag.name.lower() == "ol"

  for idx, li in enumerate(tag.find_all("li", recursive=False), start=1):
    report.total_elements += 1

    if is_todo:
      checkbox_div = li.find("div", class_=re.compile(r"checkbox"))
      checked = checkbox_div and "checkbox-on" in (checkbox_div.get("class") or [])
      # 체크박스 div 다음 텍스트가 실제 내용
      plain, formatted = _extract_inline_text(li)
      prefix = "☑ " if checked else "☐ "
      block = _make_block("text", text=prefix + plain)
      if formatted != plain:
        block["formatted_text"] = prefix + formatted
    elif is_numbered:
      plain, formatted = _extract_inline_text(li)
      prefix = f"{idx}. "
      block = _make_block("text", text=prefix + plain)
      if formatted != plain:
        block["formatted_text"] = prefix + formatted
    else:
      plain, formatted = _extract_inline_text(li)
      prefix = "• "
      block = _make_block("text", text=prefix + plain)
      if formatted != plain:
        block["formatted_text"] = prefix + formatted

    blocks.append(block)
    report.converted += 1

    # 중첩 리스트 처리
    nested = li.find(["ul", "ol"], recursive=False)
    if nested:
      blocks.extend(_parse_list(nested, report))

  return blocks


def _parse_toggle(tag: Tag, report: ConversionReport) -> dict[str, Any]:
  """<details> 태그를 ToggleBlock으로 변환합니다.

  Notion toggle 구조:
    <details>
      <summary>Toggle title</summary>
      <p>내부 콘텐츠...</p>
    </details>
  """
  summary = tag.find("summary")
  if summary:
    plain, formatted = _extract_inline_text(summary)
  else:
    plain, formatted = "", ""

  children = []
  for child in tag.children:
    if isinstance(child, Tag) and child.name != "summary":
      child_blocks = _parse_element(child, report)
      children.extend(child_blocks)

  # 자식이 없으면 빈 텍스트 블록 하나 추가 (기존 create_block 패턴과 일관성)
  if not children:
    children.append(_make_block("text", text=""))

  block = _make_block("toggle", text=plain, is_open=False, children=children)
  if formatted != plain:
    block["formatted_text"] = formatted
  return block


def _parse_quote(tag: Tag, report: ConversionReport) -> dict[str, Any]:
  """<blockquote> 태그를 QuoteBlock으로 변환합니다."""
  children = []
  first_text = ""
  for child in tag.children:
    if isinstance(child, NavigableString):
      text = str(child).strip()
      if text and not first_text:
        first_text = text
    elif isinstance(child, Tag):
      child_blocks = _parse_element(child, report)
      children.extend(child_blocks)

  if not children:
    children.append(_make_block("text", text=""))

  # 첫 번째 텍스트를 quote의 text 필드로 사용
  if not first_text and children:
    first_child = children[0]
    if first_child.get("type") == "text":
      first_text = first_child.get("text", "")

  return _make_block("quote", text=first_text, children=children)


def _parse_code(tag: Tag) -> dict[str, Any]:
  """<pre> 또는 <code> 블록을 CodeBlock으로 변환합니다.

  Notion 코드 블록 HTML 구조:
    <pre id="..." class="code"><code class="language-python">코드...</code></pre>
  """
  code_tag = tag.find("code") if tag.name == "pre" else tag
  code_text = code_tag.get_text() if code_tag else tag.get_text()

  # 언어 감지: class="language-python" 패턴
  language = "plain"
  if code_tag and isinstance(code_tag, Tag):
    classes = code_tag.get("class") or []
    for cls in classes:
      if isinstance(cls, str) and cls.startswith("language-"):
        language = cls.replace("language-", "")
        break

  return _make_block("code", code=code_text, language=language)


def _parse_callout(tag: Tag, report: ConversionReport) -> dict[str, Any]:
  """Notion callout (<figure class="callout">) 을 CalloutBlock으로 변환합니다.

  Notion callout HTML 구조:
    <figure class="callout" style="...">
      <span class="icon">💡</span>
      <div class="callout-body">
        <p>내용</p>
      </div>
    </figure>
  """
  # 아이콘 추출
  icon_span = tag.find("span", class_="icon")
  emoji = icon_span.get_text().strip() if icon_span else "💡"
  if not emoji:
    emoji = "💡"

  # 배경색 → color 매핑
  color = _extract_callout_color(tag)

  # 본문 콘텐츠 파싱
  children = []
  first_text = ""
  body_div = tag.find("div", class_="callout-body")
  content_source = body_div if body_div else tag

  for child in content_source.children:
    if isinstance(child, Tag) and child.name not in ("span",):
      if "icon" in (child.get("class") or []):
        continue
      child_blocks = _parse_element(child, report)
      children.extend(child_blocks)

  if not children:
    children.append(_make_block("text", text=""))

  if children and children[0].get("type") == "text":
    first_text = children[0].get("text", "")

  return _make_block(
    "callout",
    text=first_text,
    emoji=emoji,
    color=color,
    children=children,
  )


def _extract_callout_color(tag: Tag) -> str:
  """callout 태그의 background-color 스타일에서 color 값을 추출합니다."""
  style = tag.get("style", "")
  if not style:
    return "yellow"

  # Notion callout 배경색 → 프로젝트 color 매핑
  color_map = {
    "rgba(241,241,239": "gray",
    "rgba(244,238,225": "yellow",
    "rgba(251,236,221": "yellow",
    "rgba(232,222,238": "blue",
    "rgba(225,232,246": "blue",
    "rgba(221,237,226": "green",
    "rgba(253,235,236": "red",
    "rgba(244,223,235": "red",
  }
  for prefix, color in color_map.items():
    if prefix in style:
      return color
  return "yellow"


def _parse_image(tag: Tag) -> dict[str, Any] | None:
  """<figure>/<img> 태그를 ImageBlock으로 변환합니다.

  이미지 URL은 export 내 상대 경로 형태로 저장되며,
  import 과정에서 실제 파일이 업로드된 후 URL이 갱신됩니다.
  """
  img = tag.find("img") if tag.name != "img" else tag
  if img is None:
    return None

  src = img.get("src", "")
  if not src:
    return None

  # 캡션 추출 (figure > figcaption)
  caption = ""
  figcaption = tag.find("figcaption") if tag.name == "figure" else None
  if figcaption:
    caption = figcaption.get_text().strip()

  return _make_block("image", url=src, caption=caption)


def _parse_table(tag: Tag, report: ConversionReport) -> list[dict[str, Any]]:
  """<table> 태그를 텍스트 기반 블록으로 변환합니다.

  프로젝트의 DatabaseBlock 구조에 정확히 매핑하기 어려운 경우가 많으므로
  각 행을 텍스트 블록으로 변환하는 fallback 전략을 사용합니다.

  향후 DatabaseBlock 매핑 확장 시 이 함수를 교체할 수 있습니다.
  """
  blocks: list[dict[str, Any]] = []

  # 헤더 행 처리
  thead = tag.find("thead")
  if thead:
    header_row = thead.find("tr")
    if header_row:
      cells = [th.get_text().strip() for th in header_row.find_all(["th", "td"])]
      if any(cells):
        blocks.append(_make_block("text", text=" | ".join(cells), level=3))
        blocks.append(_make_block("divider"))
        report.converted += 1

  # 본문 행 처리
  tbody = tag.find("tbody") or tag
  for tr in tbody.find_all("tr", recursive=False):
    # thead 내부 tr은 이미 처리했으므로 건너뜀
    if tr.parent and tr.parent.name == "thead":
      continue
    cells = [td.get_text().strip() for td in tr.find_all(["td", "th"])]
    if any(cells):
      blocks.append(_make_block("text", text=" | ".join(cells)))
      report.converted += 1

  if blocks:
    report.fallback += 1
    report.warnings.append("테이블이 텍스트 기반으로 변환되었습니다 (부분 지원)")

  return blocks


def _parse_bookmark(tag: Tag) -> dict[str, Any] | None:
  """Notion bookmark (<figure class="bookmark">) 을 UrlEmbedBlock으로 변환합니다.

  Notion bookmark HTML 구조:
    <figure class="bookmark source">
      <a href="https://example.com">
        <div class="bookmark-info">
          <div class="bookmark-title">Title</div>
          <div class="bookmark-description">Description</div>
        </div>
      </a>
    </figure>
  """
  link = tag.find("a")
  if not link:
    return None

  url = link.get("href", "")
  if not url:
    return None

  title_div = tag.find("div", class_="bookmark-title")
  desc_div = tag.find("div", class_="bookmark-description")
  title = title_div.get_text().strip() if title_div else ""
  description = desc_div.get_text().strip() if desc_div else ""

  return _make_block(
    "url_embed",
    url=url,
    title=title,
    description=description,
    logo="",
    provider="",
    fetched_at="",
    status="pending",
  )


# ── 요소 디스패처 ───────────────────────────────────────────────────────────────

def _parse_element(element: Tag, report: ConversionReport) -> list[dict[str, Any]]:
  """단일 HTML 요소를 파싱하여 블록 리스트로 변환합니다.

  하나의 HTML 요소가 여러 블록을 생성할 수 있습니다 (예: 리스트).
  """
  tag_name = element.name.lower() if element.name else ""
  classes = element.get("class") or []

  report.total_elements += 1

  # heading
  if tag_name in ("h1", "h2", "h3"):
    report.converted += 1
    return [_parse_heading(element)]

  # paragraph
  if tag_name == "p":
    block = _parse_paragraph(element)
    if block:
      report.converted += 1
      return [block]
    report.skipped += 1
    return []

  # list
  if tag_name in ("ul", "ol"):
    return _parse_list(element, report)

  # toggle
  if tag_name == "details":
    report.converted += 1
    return [_parse_toggle(element, report)]

  # blockquote
  if tag_name == "blockquote":
    report.converted += 1
    return [_parse_quote(element, report)]

  # code block
  if tag_name == "pre":
    report.converted += 1
    return [_parse_code(element)]

  # divider
  if tag_name == "hr":
    report.converted += 1
    return [_make_block("divider")]

  # figure — callout / image / bookmark 분기
  if tag_name == "figure":
    if "callout" in classes:
      report.converted += 1
      return [_parse_callout(element, report)]
    if "bookmark" in classes:
      block = _parse_bookmark(element)
      if block:
        report.converted += 1
        return [block]
    # image figure
    if element.find("img"):
      block = _parse_image(element)
      if block:
        report.converted += 1
        return [block]
    report.skipped += 1
    return []

  # standalone image
  if tag_name == "img":
    block = _parse_image(element)
    if block:
      report.converted += 1
      return [block]
    report.skipped += 1
    return []

  # table
  if tag_name == "table":
    return _parse_table(element, report)

  # div — 재귀적으로 내부 요소 파싱
  if tag_name == "div":
    blocks: list[dict[str, Any]] = []
    for child in element.children:
      if isinstance(child, Tag):
        blocks.extend(_parse_element(child, report))
    # div 자체는 요소 카운트에서 제외
    report.total_elements -= 1
    return blocks

  # 미지원 요소 — fallback 텍스트 처리
  text = element.get_text().strip()
  if text:
    report.fallback += 1
    report.warnings.append(f"미지원 요소 <{tag_name}>를 텍스트로 변환했습니다")
    return [_make_block("text", text=text)]

  report.skipped += 1
  return []


# ── 페이지 파서 ─────────────────────────────────────────────────────────────────

@dataclass
class ParsedPage:
  """파싱된 Notion 페이지 한 장의 결과."""

  title: str
  blocks: list[dict[str, Any]]
  sub_page_links: list[str]  # 하위 페이지 HTML 파일 상대 경로
  report: ConversionReport


def parse_notion_html(html_content: str) -> ParsedPage:
  """단일 Notion HTML 파일을 파싱하여 블록 구조로 변환합니다.

  Args:
    html_content: Notion에서 export한 HTML 문자열.

  Returns:
    ParsedPage 객체 (제목, 블록 리스트, 하위 페이지 링크, 변환 리포트).
  """
  soup = BeautifulSoup(html_content, "html.parser")
  report = ConversionReport()

  # 제목 추출: <header> > <h1 class="page-title">
  title = ""
  header = soup.find("header")
  if header:
    h1 = header.find("h1", class_="page-title")
    if h1:
      title = h1.get_text().strip()

  # title 태그 fallback
  if not title:
    title_tag = soup.find("title")
    if title_tag:
      title = title_tag.get_text().strip()

  if not title:
    title = "Untitled"

  # 본문 파싱: <div class="page-body">
  page_body = soup.find("div", class_="page-body")
  blocks: list[dict[str, Any]] = []

  if page_body:
    for child in page_body.children:
      if isinstance(child, Tag):
        child_blocks = _parse_element(child, report)
        blocks.extend(child_blocks)

  # 하위 페이지 링크 수집
  sub_page_links = _collect_subpage_links(soup)

  return ParsedPage(
    title=title,
    blocks=blocks,
    sub_page_links=sub_page_links,
    report=report,
  )


def _collect_subpage_links(soup: BeautifulSoup) -> list[str]:
  """페이지 내 하위 페이지 링크(.html)를 수집합니다.

  Notion export에서 하위 페이지는 같은 폴더 내 별도 HTML 파일로 저장되며,
  부모 페이지에서 <a href="SubPage%20UUID.html"> 형태로 참조됩니다.
  """
  links: list[str] = []
  for a in soup.find_all("a", href=True):
    href = a["href"]
    # 외부 URL 및 앵커 링크 제외
    if href.startswith(("http://", "https://", "#", "mailto:")):
      continue
    # .html 파일 링크만 수집
    decoded = unquote(href)
    if decoded.endswith(".html"):
      links.append(decoded)
  return links


# ── ZIP 아카이브 처리 ───────────────────────────────────────────────────────────

@dataclass
class ImportResult:
  """전체 import 작업 결과."""

  pages: list[dict[str, Any]]  # 생성된 페이지 정보 리스트
  report: ConversionReport
  image_mappings: dict[str, bytes]  # 상대경로 → 이미지 바이트 데이터


def _flatten_zip(zip_data: bytes) -> dict[str, bytes]:
  """ZIP 파일 내 모든 파일을 추출합니다. 내부 ZIP도 재귀적으로 해제합니다.

  Notion export ZIP은 대용량 export 시 내부에 Part-N.zip 파일을
  포함할 수 있습니다. 이 함수는 모든 중첩 ZIP을 자동으로 해제하여
  최종 콘텐츠 파일만 반환합니다.

  Args:
    zip_data: ZIP 파일의 바이트 데이터.

  Returns:
    {파일경로: 바이트데이터} dict. 디렉터리 엔트리와 __MACOSX는 제외됨.

  Raises:
    ValueError: 유효하지 않은 ZIP 파일인 경우.
  """
  if not zipfile.is_zipfile(BytesIO(zip_data)):
    raise ValueError("유효하지 않은 ZIP 파일입니다.")

  result: dict[str, bytes] = {}

  with zipfile.ZipFile(BytesIO(zip_data), "r") as zf:
    for name in zf.namelist():
      if name.endswith("/") or "__MACOSX" in name:
        continue

      data = zf.read(name)

      # 내부 ZIP 파일 감지 → 재귀 추출
      if name.lower().endswith(".zip") and zipfile.is_zipfile(BytesIO(data)):
        inner = _flatten_zip(data)
        result.update(inner)
      else:
        result[name] = data

  return result


def extract_and_parse_zip(zip_data: bytes) -> ImportResult:
  """Notion export ZIP 파일을 추출하고 파싱합니다.

  HTML과 Markdown 양쪽 export 포맷을 자동 감지하여 처리합니다.
  내부에 Part-N.zip이 포함된 이중 ZIP 구조도 자동 해제합니다.

  ZIP 구조 예시:
    Export-UUID.zip
      └─ Export-UUID-Part-1.zip    ← 이중 ZIP (자동 해제)
           └─ 루트폴더/
                ├─ 페이지.md (또는 .html)
                ├─ 페이지/
                │    ├─ 하위페이지.md
                │    ├─ image.png
                │    └─ 데이터베이스.csv
                └─ 데이터베이스.csv

  Args:
    zip_data: ZIP 파일의 바이트 데이터.

  Returns:
    ImportResult 객체.

  Raises:
    ValueError: ZIP 파일이 유효하지 않거나 콘텐츠 파일이 없는 경우.
  """
  all_files = _flatten_zip(zip_data)

  overall_report = ConversionReport()
  pages: list[dict[str, Any]] = []
  image_mappings: dict[str, bytes] = {}

  # 파일 분류
  html_files: list[str] = []
  md_files: list[str] = []
  csv_files: list[str] = []

  for name in all_files:
    lower = name.lower()
    if lower.endswith((".html", ".htm")):
      html_files.append(name)
    elif lower.endswith(".md"):
      md_files.append(name)
    elif lower.endswith(".csv"):
      # _all.csv 는 동일 데이터의 중복이므로 제외
      if not lower.endswith("_all.csv"):
        csv_files.append(name)
    elif _is_image_file(name):
      image_mappings[name] = all_files[name]

  # 포맷 자동 감지: HTML 우선, 없으면 Markdown
  content_files = html_files if html_files else md_files
  is_markdown = not html_files and bool(md_files)

  if not content_files:
    raise ValueError("ZIP 파일에 변환 가능한 파일(.html/.md)이 없습니다.")

  # 경로 깊이 기준 정렬 (상위 페이지 먼저)
  content_files.sort(key=lambda p: p.count("/"))

  # 각 콘텐츠 파일 파싱
  for file_path in content_files:
    try:
      raw = all_files[file_path]
      content = raw.decode("utf-8", errors="replace")

      if is_markdown:
        parsed = parse_notion_markdown(content)
      else:
        parsed = parse_notion_html(content)

      # 이미지 URL을 ZIP 내 절대 경로로 정규화
      file_dir = str(PurePosixPath(file_path).parent)
      _resolve_image_urls(parsed.blocks, file_dir, image_mappings)

      pages.append({
        "path": file_path,
        "title": parsed.title,
        "blocks": parsed.blocks,
        "sub_page_links": parsed.sub_page_links,
      })

      # 리포트 집계
      overall_report.total_elements += parsed.report.total_elements
      overall_report.converted += parsed.report.converted
      overall_report.fallback += parsed.report.fallback
      overall_report.skipped += parsed.report.skipped
      overall_report.warnings.extend(parsed.report.warnings)

    except Exception as exc:
      logger.error("파일 파싱 실패: %s — %s", file_path, exc)
      overall_report.warnings.append(f"파일 파싱 실패: {file_path}")

  # CSV 파일 → 테이블 블록으로 변환하여 관련 페이지에 추가
  for csv_path in csv_files:
    try:
      raw = all_files[csv_path]
      csv_text = raw.decode("utf-8-sig", errors="replace")
      csv_blocks = _parse_csv_to_blocks(csv_text)
      if csv_blocks:
        csv_dir = str(PurePosixPath(csv_path).parent)
        csv_stem = PurePosixPath(csv_path).stem
        # UUID 해시 제거 — Notion export는 "제목 UUID해시.csv" 패턴
        csv_title = re.sub(r"\s+[0-9a-f]{32}$", "", csv_stem).strip() or csv_stem

        # 동일 디렉터리의 부모 페이지를 찾아 블록 추가
        parent_page = _find_parent_page_for_csv(csv_dir, csv_title, pages)
        if parent_page:
          parent_page["blocks"].extend(csv_blocks)
        else:
          # 부모를 못 찾으면 독립 페이지로 생성
          pages.append({
            "path": csv_path,
            "title": csv_title,
            "blocks": csv_blocks,
            "sub_page_links": [],
          })
        overall_report.converted += len(csv_blocks)
        overall_report.total_elements += len(csv_blocks)
    except Exception as exc:
      logger.warning("CSV 파싱 실패: %s — %s", csv_path, exc)
      overall_report.warnings.append(f"CSV 파싱 실패: {csv_path}")

  return ImportResult(pages=pages, report=overall_report, image_mappings=image_mappings)


def parse_single_html(html_data: bytes) -> ImportResult:
  """단일 HTML 파일을 파싱합니다 (ZIP이 아닌 경우).

  Args:
    html_data: HTML 파일의 바이트 데이터.

  Returns:
    ImportResult 객체 (이미지 매핑 없음).
  """
  content = html_data.decode("utf-8", errors="replace")
  parsed = parse_notion_html(content)

  pages = [{
    "path": "",
    "title": parsed.title,
    "blocks": parsed.blocks,
    "sub_page_links": parsed.sub_page_links,
  }]

  return ImportResult(
    pages=pages,
    report=parsed.report,
    image_mappings={},
  )


def parse_single_markdown(md_data: bytes) -> ImportResult:
  """단일 Markdown 파일을 파싱합니다 (ZIP이 아닌 경우).

  Args:
    md_data: Markdown 파일의 바이트 데이터.

  Returns:
    ImportResult 객체 (이미지 매핑 없음).
  """
  content = md_data.decode("utf-8", errors="replace")
  parsed = parse_notion_markdown(content)

  pages = [{
    "path": "",
    "title": parsed.title,
    "blocks": parsed.blocks,
    "sub_page_links": parsed.sub_page_links,
  }]

  return ImportResult(
    pages=pages,
    report=parsed.report,
    image_mappings={},
  )


def _resolve_image_urls(
  blocks: list[dict[str, Any]],
  html_dir: str,
  image_mappings: dict[str, bytes],
) -> None:
  """블록 내 이미지 URL을 ZIP 내 절대 경로로 정규화합니다.

  Notion export HTML에서 이미지 src는 상대 경로로 작성됩니다.
  이를 ZIP 내부의 전체 경로로 변환하여 나중에 업로드 시 매칭할 수 있게 합니다.
  """
  for block in blocks:
    if block.get("type") == "image":
      url = block.get("url", "")
      if url and not url.startswith(("http://", "https://", "/")):
        decoded_url = unquote(url)
        resolved = str(PurePosixPath(html_dir) / decoded_url)
        # ZIP 내 실제 경로와 매칭 시도
        if resolved in image_mappings:
          block["url"] = resolved
        else:
          # 부분 매칭 시도 (파일명 기반)
          filename = PurePosixPath(decoded_url).name
          for key in image_mappings:
            if PurePosixPath(key).name == filename:
              block["url"] = key
              break

    # 재귀: 컨테이너 블록의 children 처리
    children = block.get("children")
    if children:
      _resolve_image_urls(children, html_dir, image_mappings)


def _is_image_file(filename: str) -> bool:
  """파일명이 이미지 확장자인지 판별합니다."""
  ext = PurePosixPath(filename).suffix.lower()
  return ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}


# ── Notion Markdown 파서 ───────────────────────────────────────────────────────
#
# Notion Markdown export 포맷:
#   - 제목: 파일 첫 줄 `# 제목`
#   - 소제목: `## / ###`
#   - 본문: 일반 텍스트 행
#   - 리스트: `- item` (bulleted), `1. item` (numbered)
#   - 할일: `- [ ] todo`, `- [x] done`
#   - 코드: ``` 블록
#   - 인용: `> text`
#   - 구분선: `---`
#   - 이미지: `![alt](path)`
#   - 링크: `[text](url)` — 하위 페이지 링크 포함
#   - 인라인: **bold**, *italic*, ~~strike~~, `code`
#
# Ref: https://www.notion.so/help/export-your-content

# Markdown 인라인 서식 → formatted_text 변환 패턴
_MD_INLINE_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
  # 순서 중요: bold(**) 를 italic(*) 보다 먼저 매칭
  (re.compile(r"\*\*(.+?)\*\*"), "<b>", "</b>"),
  (re.compile(r"__(.+?)__"), "<b>", "</b>"),
  (re.compile(r"\*(.+?)\*"), "<i>", "</i>"),
  (re.compile(r"_(.+?)_"), "<i>", "</i>"),
  (re.compile(r"~~(.+?)~~"), "<s>", "</s>"),
  (re.compile(r"`(.+?)`"), "<code>", "</code>"),
]

# Markdown 링크 패턴: [text](url)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Markdown 이미지 패턴: ![alt](path)
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _md_convert_inline(text: str) -> tuple[str, str | None]:
  """Markdown 인라인 서식을 plain text와 formatted_text로 변환합니다.

  Args:
    text: Markdown 인라인 서식이 포함된 문자열.

  Returns:
    (plain_text, formatted_text) 튜플. 서식이 없으면 formatted_text는 None.
  """
  # 이미지 패턴은 인라인 변환에서 제외 (별도 블록으로 처리)
  formatted = text

  # 링크 변환: [text](url) → <a href="url">text</a>
  formatted = _MD_LINK_RE.sub(r'<a href="\2">\1</a>', formatted)

  # 인라인 서식 변환
  for pattern, open_tag, close_tag in _MD_INLINE_PATTERNS:
    formatted = pattern.sub(rf"{open_tag}\1{close_tag}", formatted)

  # plain text: 모든 마크업 제거
  plain = text
  plain = _MD_LINK_RE.sub(r"\1", plain)
  for pattern, _, _ in _MD_INLINE_PATTERNS:
    plain = pattern.sub(r"\1", plain)

  if formatted == plain:
    return plain, None
  return plain, formatted


def parse_notion_markdown(md_content: str) -> ParsedPage:
  """단일 Notion Markdown 파일을 파싱하여 블록 구조로 변환합니다.

  Args:
    md_content: Notion에서 export한 Markdown 문자열.

  Returns:
    ParsedPage 객체 (제목, 블록 리스트, 하위 페이지 링크, 변환 리포트).
  """
  report = ConversionReport()
  blocks: list[dict[str, Any]] = []
  sub_page_links: list[str] = []
  title = "Untitled"

  lines = md_content.split("\n")
  i = 0

  while i < len(lines):
    line = lines[i]
    stripped = line.strip()

    # 빈 줄 건너뜀
    if not stripped:
      i += 1
      continue

    report.total_elements += 1

    # ── 제목: # / ## / ### ──────────────────────────────────────────────
    heading_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
    if heading_match:
      level = len(heading_match.group(1))
      heading_text = heading_match.group(2).strip()
      plain, formatted = _md_convert_inline(heading_text)

      # 파일의 첫 번째 h1은 페이지 제목으로 사용
      if level == 1 and title == "Untitled":
        title = plain
        report.converted += 1
        i += 1
        continue

      block = _make_block("text", text=plain, level=level)
      if formatted:
        block["formatted_text"] = formatted
      blocks.append(block)
      report.converted += 1
      i += 1
      continue

    # ── 이미지: ![alt](path) ────────────────────────────────────────────
    img_match = _MD_IMAGE_RE.match(stripped)
    if img_match:
      caption = img_match.group(1)
      url = unquote(img_match.group(2))
      blocks.append(_make_block("image", url=url, caption=caption))
      report.converted += 1
      i += 1
      continue

    # ── 코드 블록: ``` ──────────────────────────────────────────────────
    if stripped.startswith("```"):
      language = stripped[3:].strip() or "plain"
      code_lines: list[str] = []
      i += 1
      while i < len(lines):
        if lines[i].strip().startswith("```"):
          i += 1
          break
        code_lines.append(lines[i])
        i += 1
      code_text = "\n".join(code_lines)
      blocks.append(_make_block("code", code=code_text, language=language))
      report.converted += 1
      continue

    # ── 구분선: --- / *** / ___ ────────────────────────────────────────
    if re.match(r"^[-*_]{3,}\s*$", stripped):
      blocks.append(_make_block("divider"))
      report.converted += 1
      i += 1
      continue

    # ── 인용문: > ───────────────────────────────────────────────────────
    if stripped.startswith(">"):
      quote_lines: list[str] = []
      while i < len(lines) and lines[i].strip().startswith(">"):
        # > 접두사 제거
        quote_text = re.sub(r"^>\s?", "", lines[i].strip())
        quote_lines.append(quote_text)
        i += 1
      full_quote = "\n".join(quote_lines)
      plain, formatted = _md_convert_inline(full_quote)
      child = _make_block("text", text=plain)
      if formatted:
        child["formatted_text"] = formatted
      blocks.append(_make_block("quote", text=plain, children=[child]))
      report.converted += 1
      continue

    # ── 할일 리스트: - [ ] / - [x] ─────────────────────────────────────
    todo_match = re.match(r"^-\s+\[([ xX])\]\s*(.*)", stripped)
    if todo_match:
      checked = todo_match.group(1).lower() == "x"
      item_text = todo_match.group(2)
      plain, formatted = _md_convert_inline(item_text)
      prefix = "☑ " if checked else "☐ "
      block = _make_block("text", text=prefix + plain)
      if formatted:
        block["formatted_text"] = prefix + formatted
      blocks.append(block)
      report.converted += 1
      i += 1
      continue

    # ── 글머리 기호 리스트: - item ──────────────────────────────────────
    bullet_match = re.match(r"^[-*+]\s+(.+)", stripped)
    if bullet_match:
      item_text = bullet_match.group(1)
      # 하위 페이지 링크 감지: [text](path.md) 또는 [text](path.csv)
      link_match = _MD_LINK_RE.match(item_text)
      if link_match:
        href = unquote(link_match.group(2))
        if href.endswith((".md", ".csv")):
          sub_page_links.append(href)
          # 링크 항목은 일반 텍스트 블록으로 표시
          plain, formatted = _md_convert_inline(item_text)
          block = _make_block("text", text="• " + plain)
          if formatted:
            block["formatted_text"] = "• " + formatted
          blocks.append(block)
          report.converted += 1
          i += 1
          continue

      plain, formatted = _md_convert_inline(item_text)
      block = _make_block("text", text="• " + plain)
      if formatted:
        block["formatted_text"] = "• " + formatted
      blocks.append(block)
      report.converted += 1
      i += 1
      continue

    # ── 번호 리스트: 1. item ────────────────────────────────────────────
    num_match = re.match(r"^(\d+)\.\s+(.+)", stripped)
    if num_match:
      num = num_match.group(1)
      item_text = num_match.group(2)
      plain, formatted = _md_convert_inline(item_text)
      block = _make_block("text", text=f"{num}. " + plain)
      if formatted:
        block["formatted_text"] = f"{num}. " + formatted
      blocks.append(block)
      report.converted += 1
      i += 1
      continue

    # ── 일반 단락 ──────────────────────────────────────────────────────
    # 여러 줄이 빈 줄 없이 이어지면 하나의 단락으로 합침
    para_lines: list[str] = []
    while i < len(lines) and lines[i].strip():
      current = lines[i].strip()
      # 다음 블록 시작 패턴이면 단락 종료
      if (re.match(r"^#{1,3}\s", current)
          or current.startswith("```")
          or re.match(r"^[-*_]{3,}\s*$", current)
          or current.startswith(">")
          or re.match(r"^[-*+]\s+", current)
          or re.match(r"^\d+\.\s+", current)
          or _MD_IMAGE_RE.match(current)
          or re.match(r"^-\s+\[[ xX]\]", current)):
        break
      para_lines.append(current)
      i += 1

    if para_lines:
      full_text = " ".join(para_lines)

      # 단독 링크 행 → URL embed 또는 하위 페이지
      link_only = _MD_LINK_RE.fullmatch(full_text.strip())
      if link_only:
        href = unquote(link_only.group(2))
        if href.startswith(("http://", "https://")):
          blocks.append(_make_block(
            "url_embed",
            url=href,
            title=link_only.group(1),
            description="",
            logo="",
            provider="",
            fetched_at="",
            status="pending",
          ))
          report.converted += 1
          continue
        if href.endswith((".md", ".csv")):
          sub_page_links.append(href)

      plain, formatted = _md_convert_inline(full_text)
      block = _make_block("text", text=plain)
      if formatted:
        block["formatted_text"] = formatted
      blocks.append(block)
      report.converted += 1
      continue

    i += 1

  return ParsedPage(
    title=title,
    blocks=blocks,
    sub_page_links=sub_page_links,
    report=report,
  )


# ── CSV 파서 ────────────────────────────────────────────────────────────────────

def _parse_csv_to_blocks(csv_text: str) -> list[dict[str, Any]]:
  """Notion export CSV 파일을 텍스트 기반 블록으로 변환합니다.

  Notion 데이터베이스는 CSV로 export되며, 첫 행이 컬럼 헤더입니다.
  각 행을 파이프(|) 구분 텍스트 블록으로 변환합니다.

  Args:
    csv_text: CSV 파일 내용 문자열.

  Returns:
    블록 dict 리스트. 빈 CSV이면 빈 리스트.
  """
  reader = csv.reader(io.StringIO(csv_text))
  rows = list(reader)
  if not rows:
    return []

  blocks: list[dict[str, Any]] = []

  # 헤더 행
  header = rows[0]
  if any(cell.strip() for cell in header):
    blocks.append(_make_block("text", text=" | ".join(header), level=3))
    blocks.append(_make_block("divider"))

  # 데이터 행
  for row in rows[1:]:
    if any(cell.strip() for cell in row):
      blocks.append(_make_block("text", text=" | ".join(row)))

  return blocks


def _find_parent_page_for_csv(
  csv_dir: str,
  csv_title: str,
  pages: list[dict[str, Any]],
) -> dict[str, Any] | None:
  """CSV 파일의 부모 페이지를 찾습니다.

  Notion export에서 CSV 파일은 이를 참조하는 .md 파일과
  같은 디렉터리 또는 상위 디렉터리에 위치합니다.
  """
  # 같은 디렉터리의 페이지 중 이름이 유사한 것을 찾음
  for page in pages:
    page_dir = str(PurePosixPath(page["path"]).parent)
    if page_dir == csv_dir:
      return page

  # 상위 디렉터리의 페이지에서 탐색
  parent_dir = str(PurePosixPath(csv_dir).parent)
  for page in pages:
    page_dir = str(PurePosixPath(page["path"]).parent)
    if page_dir == parent_dir:
      return page

  return None
