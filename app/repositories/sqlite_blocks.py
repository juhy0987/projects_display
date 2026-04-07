from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from app.models.blocks import Block, BlockDocument, ContainerBlock


class SQLiteBlockRepository:
  """SQLite-backed repository for notion-style block documents."""

  _block_adapter = TypeAdapter(Block)

  def __init__(self, db_path: Path) -> None:
    self._db_path = db_path
    self._db_path.parent.mkdir(parents=True, exist_ok=True)

  def initialize(self) -> None:
    with sqlite3.connect(self._db_path) as conn:
      cursor = conn.cursor()

      cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          subtitle TEXT NOT NULL DEFAULT ''
        )
        """
      )

      cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS blocks (
          id TEXT PRIMARY KEY,
          document_id TEXT NOT NULL,
          parent_block_id TEXT,
          type TEXT NOT NULL,
          position INTEGER NOT NULL,
          content_json TEXT NOT NULL,
          FOREIGN KEY (document_id) REFERENCES documents(id)
        )
        """
      )

      cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_blocks_document_parent_pos ON blocks(document_id, parent_block_id, position)"
      )

      conn.commit()

    self._seed_if_empty()

  def list_documents(self) -> list[dict[str, str]]:
    with sqlite3.connect(self._db_path) as conn:
      conn.row_factory = sqlite3.Row
      rows = conn.execute(
        "SELECT id, title, subtitle FROM documents ORDER BY title ASC"
      ).fetchall()

    return [dict(row) for row in rows]

  def get_document(self, document_id: str) -> BlockDocument | None:
    with sqlite3.connect(self._db_path) as conn:
      conn.row_factory = sqlite3.Row
      doc_row = conn.execute(
        "SELECT id, title, subtitle FROM documents WHERE id = ?",
        (document_id,),
      ).fetchone()

      if doc_row is None:
        return None

      block_rows = conn.execute(
        """
        SELECT id, parent_block_id, type, content_json
        FROM blocks
        WHERE document_id = ?
        ORDER BY parent_block_id ASC, position ASC
        """,
        (document_id,),
      ).fetchall()

    children_by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for row in block_rows:
      parent_key = row["parent_block_id"]
      children_by_parent.setdefault(parent_key, []).append(
        {
          "id": row["id"],
          "type": row["type"],
          **json.loads(row["content_json"]),
        }
      )

    def build_nodes(parent_id: str | None) -> list[Block]:
      nodes: list[Block] = []
      for item in children_by_parent.get(parent_id, []):
        if item["type"] == "container":
          container_payload = {
            **item,
            "children": build_nodes(item["id"]),
          }
          nodes.append(ContainerBlock.model_validate(container_payload))
        else:
          nodes.append(self._block_adapter.validate_python(item))
      return nodes

    blocks = build_nodes(None)
    return BlockDocument(
      id=doc_row["id"],
      title=doc_row["title"],
      subtitle=doc_row["subtitle"],
      blocks=blocks,
    )

  def create_document(self) -> dict[str, str]:
    doc_id = str(uuid.uuid4())
    title = "새 문서"
    with sqlite3.connect(self._db_path) as conn:
      conn.execute(
        "INSERT INTO documents(id, title, subtitle) VALUES (?, ?, ?)",
        (doc_id, title, ""),
      )
      conn.commit()
    return {"id": doc_id, "title": title, "subtitle": ""}

  def update_document_title(self, document_id: str, title: str) -> bool:
    with sqlite3.connect(self._db_path) as conn:
      cursor = conn.execute(
        "UPDATE documents SET title = ? WHERE id = ?",
        (title, document_id),
      )
      conn.commit()
    return cursor.rowcount > 0

  def delete_document(self, document_id: str) -> bool:
    with sqlite3.connect(self._db_path) as conn:
      cursor = conn.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
      if cursor.fetchone() is None:
        return False
      conn.execute("DELETE FROM blocks WHERE document_id = ?", (document_id,))
      conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
      conn.commit()
    return True

  def _seed_if_empty(self) -> None:
    with sqlite3.connect(self._db_path) as conn:
      existing_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
      if existing_count > 0:
        return

      doc_id = "project-manager-intro"
      conn.execute(
        "INSERT INTO documents(id, title, subtitle) VALUES (?, ?, ?)",
        (doc_id, "Project Manager 소개", "블록 기반 프로젝트 관리 도구"),
      )

      blocks = [
        ("b-overview", doc_id, None, "container", 1, {"title": "개요", "layout": "vertical"}),
        (
          "b-overview-text",
          doc_id,
          "b-overview",
          "text",
          1,
          {
            "text": "Project Manager는 노션 스타일의 블록 인터페이스로 프로젝트와 문서를 관리하는 도구입니다.",
          },
        ),
        (
          "b-overview-image",
          doc_id,
          "b-overview",
          "image",
          2,
          {
            "url": "https://images.unsplash.com/photo-1611532736597-de2d4265fba3?auto=format&fit=crop&w=1200&q=80",
            "caption": "블록으로 구성하는 프로젝트 문서",
          },
        ),
        (
          "b-block-types",
          doc_id,
          None,
          "container",
          2,
          {"title": "블록 타입", "layout": "grid"},
        ),
        (
          "b-block-text",
          doc_id,
          "b-block-types",
          "text",
          1,
          {"text": "텍스트 블록: 프로젝트 설명, 요구사항, 메모 등 텍스트 콘텐츠를 기록합니다."},
        ),
        (
          "b-block-image",
          doc_id,
          "b-block-types",
          "text",
          2,
          {"text": "이미지 블록: 스크린샷, 다이어그램, 참고 이미지를 문서에 삽입합니다."},
        ),
        (
          "b-block-container",
          doc_id,
          "b-block-types",
          "text",
          3,
          {"text": "컨테이너 블록: 블록 묶음에 레이아웃(vertical / grid)을 적용해 섹션을 구조화합니다."},
        ),
      ]

      conn.executemany(
        """
        INSERT INTO blocks(id, document_id, parent_block_id, type, position, content_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
          (block_id, document_id, parent_id, block_type, position, json.dumps(content, ensure_ascii=False))
          for block_id, document_id, parent_id, block_type, position, content in blocks
        ],
      )

      conn.commit()
