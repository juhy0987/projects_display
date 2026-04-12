from __future__ import annotations

from typing import Annotated, Literal

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


class PageBlock(BlockBase):
  """Block that links to another BlockDocument, enabling recursive page nesting."""

  type: Literal["page"]
  document_id: str
  title: str = ""  # populated at query time from the referenced document
  is_reference: bool = False  # True when linking to a pre-existing document (not auto-created)
  is_broken_ref: bool = False  # True when the target document no longer exists


Block = Annotated[
  TextBlock | ImageBlock | ToggleBlock | QuoteBlock | CodeBlock | CalloutBlock | DividerBlock | PageBlock,
  Field(discriminator="type"),
]


class BlockDocument(BaseModel):
  """A notion-like page represented as a block tree."""

  id: str
  title: str
  subtitle: str = ""
  blocks: list[Block]
