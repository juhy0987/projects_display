from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class BlockBase(BaseModel):
  """Common fields shared by all block types."""

  id: str
  type: str


class TextBlock(BlockBase):
  """Plain text paragraph, optionally promoted to a heading via level."""

  type: Literal["text"]
  text: str
  level: Literal[1, 2, 3] | None = None


class ImageBlock(BlockBase):
  """Image block with optional caption text."""

  type: Literal["image"]
  url: str
  caption: str = ""


class ContainerBlock(BlockBase):
  """Container block that groups other blocks."""

  type: Literal["container"]
  title: str = ""
  layout: Literal["vertical", "grid"] = "vertical"
  children: list["Block"] = Field(default_factory=list)


class DividerBlock(BlockBase):
  """Horizontal divider block."""

  type: Literal["divider"]


class PageBlock(BlockBase):
  """Block that links to another BlockDocument, enabling recursive page nesting."""

  type: Literal["page"]
  document_id: str
  title: str = ""  # populated at query time from the referenced document


Block = Annotated[
  TextBlock | ImageBlock | ContainerBlock | DividerBlock | PageBlock,
  Field(discriminator="type"),
]


class BlockDocument(BaseModel):
  """A notion-like page represented as a block tree."""

  id: str
  title: str
  subtitle: str = ""
  blocks: list[Block]
