from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class BlockBase(BaseModel):
  """Common fields shared by all block types."""

  id: str
  type: str


class TextBlock(BlockBase):
  """Plain text paragraph or heading-like block."""

  type: Literal["text"]
  text: str


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


Block = Annotated[TextBlock | ImageBlock | ContainerBlock, Field(discriminator="type")]


class BlockDocument(BaseModel):
  """A notion-like page represented as a block tree."""

  id: str
  title: str
  subtitle: str = ""
  blocks: list[Block]
