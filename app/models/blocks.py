from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class BlockBase(BaseModel):
  """Common fields shared by all block types."""

  id: str
  type: str


class ContainerBlockBase(BlockBase):
  """Internal base for blocks that can contain child blocks.

  Not a user-visible block type — not included in the Block discriminated union.
  Blocks that accept child blocks (toggle, quote, callout) inherit from this base.
  """

  children: list["Block"] = Field(default_factory=list)


class TextBlock(BlockBase):
  """Plain text paragraph, optionally promoted to a heading via level."""

  type: Literal["text"]
  text: str
  level: Literal[1, 2, 3] | None = None
  formatted_text: str | None = None


class ImageBlock(BlockBase):
  """Image block with optional caption text."""

  type: Literal["image"]
  url: str
  caption: str = ""


class ToggleBlock(ContainerBlockBase):
  """Collapsible block with a title and nested child blocks."""

  type: Literal["toggle"]
  text: str = ""
  formatted_text: str | None = None
  level: Literal[1, 2, 3] | None = None
  is_open: bool = False


class QuoteBlock(ContainerBlockBase):
  """Blockquote with optional nested child blocks."""

  type: Literal["quote"]
  text: str = ""


class CodeBlock(BlockBase):
  """Code block with language selection and a copy action."""

  type: Literal["code"]
  code: str = ""
  language: str = "plain"


class CalloutBlock(ContainerBlockBase):
  """Highlighted callout box with an emoji icon and background colour."""

  type: Literal["callout"]
  text: str = ""
  emoji: str = "💡"
  color: Literal["yellow", "blue", "green", "red", "gray"] = "yellow"


class DividerBlock(BlockBase):
  """Horizontal divider block."""

  type: Literal["divider"]


class UrlEmbedBlock(BlockBase):
  """URL embed block that displays page metadata as a bookmark-style card.

  Metadata fields (title, description, logo, provider) are populated
  server-side by the /api/url-embed/fetch endpoint.

  Ref: Open Graph Protocol — https://ogp.me/
  """

  type: Literal["url_embed"]
  url: str = ""
  title: str = ""
  description: str = ""
  logo: str = ""        # resolved absolute URL: og:image / apple-touch-icon / favicon
  provider: str = ""    # hostname without "www." prefix
  fetched_at: str = ""  # ISO-8601 UTC timestamp of last fetch attempt
  status: Literal["pending", "success", "error"] = "pending"


class FileBlock(BlockBase):
  """첨부 파일 블록 — 업로드된 파일을 문서에 첨부합니다.

  file_id는 files 테이블의 FileRow.id를 참조합니다.
  original_filename·size_bytes·mime_type은 조회 시점에 FileRow에서 채워집니다.
  """

  type: Literal["file"]
  file_id: str = ""            # files 테이블의 row id
  original_filename: str = ""  # 표시용 파일명 (query-time 채움)
  size_bytes: int = 0          # 파일 크기 bytes (query-time 채움)
  mime_type: str = ""          # MIME type (query-time 채움)
  download_url: str = ""       # /api/files/{file_id} (query-time 채움)


class PageBlock(BlockBase):
  """Block that links to another BlockDocument, enabling recursive page nesting."""

  type: Literal["page"]
  document_id: str
  title: str = ""  # populated at query time from the referenced document
  is_reference: bool = False  # True when linking to a pre-existing document (not auto-created)
  is_broken_ref: bool = False  # True when the target document no longer exists


# ── Database block types ───────────────────────────────────────────────────────

class ColumnSchema(BaseModel):
  """Schema definition for a single database column."""

  id: str
  name: str
  type: Literal["text", "number", "select", "checkbox"] = "text"
  options: list[str] = Field(default_factory=list)  # for select type


class DbRowBlock(PageBlock):
  """Database row block — extends PageBlock so each row is also a page.

  Properties map column IDs to cell values.
  """

  type: Literal["db_row"]
  properties: dict[str, Any] = Field(default_factory=dict)


class DatabaseBlock(BlockBase):
  """Database block — renders as a table whose rows are pages."""

  type: Literal["database"]
  title: str = ""
  color: Literal["default", "gray", "brown", "orange", "yellow", "green", "blue", "purple", "pink", "red"] = "default"
  columns: list[ColumnSchema] = Field(default_factory=list)
  rows: list[DbRowBlock] = Field(default_factory=list)  # populated at query time


# ── Discriminated union of all block types ─────────────────────────────────────

Block = Annotated[
  TextBlock
  | ImageBlock
  | FileBlock
  | ToggleBlock
  | QuoteBlock
  | CodeBlock
  | CalloutBlock
  | DividerBlock
  | UrlEmbedBlock
  | PageBlock
  | DbRowBlock
  | DatabaseBlock,
  Field(discriminator="type"),
]


# ── Database row page context ──────────────────────────────────────────────────

class DbContext(BaseModel):
  """Attached to a BlockDocument when that document is a database row page.

  Provides the column schema from the parent DatabaseBlock so the page can
  render editable property fields below the title.
  """

  block_id: str       # the db_row block id
  db_block_id: str    # the parent DatabaseBlock id
  columns: list[ColumnSchema]
  properties: dict[str, Any]


class BlockDocument(BaseModel):
  """A notion-like page represented as a block tree."""

  id: str
  title: str
  subtitle: str = ""
  blocks: list[Block]
  db_context: DbContext | None = None
