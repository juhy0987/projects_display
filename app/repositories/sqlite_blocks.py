from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session

from app.models.blocks import (
  Block,
  BlockDocument,
  CalloutBlock,
  DividerBlock,
  PageBlock,
  QuoteBlock,
  ToggleBlock,
)
from app.models.orm import BlockRow, DocumentRow


# Block types that act as containers: auto-create one child text block on creation
# and cascade-delete upward when their last child is removed.
_CHILD_BEARING_TYPES: frozenset[str] = frozenset({"toggle", "quote", "callout"})


class SQLiteBlockRepository:
  """SQLAlchemy-backed repository for notion-style block documents."""

  _block_adapter = TypeAdapter(Block)

  def __init__(self, session: Session) -> None:
    self._session = session

  # ── Documents ──────────────────────────────────────────────────────────────

  def document_exists(self, document_id: str) -> bool:
    """Return True if a document with the given id exists."""
    return self._session.get(DocumentRow, document_id) is not None

  def list_documents(self) -> list[dict]:
    """Return all documents as a parent-child tree sorted by title.

    Each root-level document has a ``children`` list; children are sorted
    alphabetically and may themselves contain further children.
    """
    rows = self._session.execute(
      select(DocumentRow).order_by(DocumentRow.title)
    ).scalars().all()

    all_docs: list[dict] = [
      {"id": r.id, "title": r.title, "subtitle": r.subtitle, "parent_id": r.parent_id, "children": []}
      for r in rows
    ]
    by_id = {d["id"]: d for d in all_docs}
    roots: list[dict] = []

    for doc in all_docs:
      pid = doc["parent_id"]
      if pid and pid in by_id:
        by_id[pid]["children"].append(doc)
      else:
        roots.append(doc)

    return roots

  def get_document(self, document_id: str) -> BlockDocument | None:
    doc_row = self._session.get(DocumentRow, document_id)
    if doc_row is None:
      return None

    block_rows = self._session.execute(
      select(BlockRow)
      .where(BlockRow.document_id == document_id)
      .order_by(BlockRow.parent_block_id.asc(), BlockRow.position.asc())
    ).scalars().all()

    parsed_blocks = [
      {
        "id": row.id,
        "parent_block_id": row.parent_block_id,
        "type": row.type,
        **json.loads(row.content_json),
      }
      for row in block_rows
    ]

    page_doc_ids = list({
      item["document_id"]
      for item in parsed_blocks
      if item["type"] == "page" and "document_id" in item
    })
    doc_titles: dict[str, str] = {}
    if page_doc_ids:
      title_rows = self._session.execute(
        select(DocumentRow.id, DocumentRow.title).where(DocumentRow.id.in_(page_doc_ids))
      ).all()
      doc_titles = {row.id: row.title for row in title_rows}

    children_by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for item in parsed_blocks:
      children_by_parent.setdefault(item["parent_block_id"], []).append(item)

    def build_nodes(parent_id: str | None) -> list[Block]:
      nodes: list[Block] = []
      for item in children_by_parent.get(parent_id, []):
        if item["type"] in _CHILD_BEARING_TYPES:
          model_cls = {"toggle": ToggleBlock, "quote": QuoteBlock, "callout": CalloutBlock}[item["type"]]
          nodes.append(model_cls.model_validate({**item, "children": build_nodes(item["id"])}))
        elif item["type"] == "container":
          # 레거시 container 블록 역호환 — toggle로 매핑하여 children 유지
          nodes.append(ToggleBlock.model_validate({
            **item,
            "type": "toggle",
            "text": item.get("title") or item.get("text") or "",
            "is_open": True,
            "children": build_nodes(item["id"]),
          }))
        elif item["type"] == "heading":
          # heading은 TextBlock으로 통합 — 기존 DB 데이터 하위 호환
          nodes.append(self._block_adapter.validate_python({**item, "type": "text"}))
        elif item["type"] == "divider":
          nodes.append(DividerBlock.model_validate(item))
        elif item["type"] == "page":
          doc_id = item.get("document_id", "")
          is_broken = bool(doc_id) and doc_id not in doc_titles
          nodes.append(PageBlock.model_validate({
            **item,
            "title": "" if is_broken else doc_titles.get(doc_id, ""),
            "is_broken_ref": is_broken,
          }))
        else:
          nodes.append(self._block_adapter.validate_python(item))
      return nodes

    return BlockDocument(
      id=doc_row.id,
      title=doc_row.title,
      subtitle=doc_row.subtitle,
      blocks=build_nodes(None),
    )

  def create_document(self) -> dict:
    doc_id = str(uuid.uuid4())
    title = "새 문서"
    self._session.add(DocumentRow(id=doc_id, title=title, subtitle="", parent_id=None))
    self._session.commit()
    return {"id": doc_id, "title": title, "subtitle": "", "parent_id": None, "children": []}

  def create_child_document(self, parent_id: str) -> dict | None:
    """Create a new document as a direct child of *parent_id*.

    Returns None if *parent_id* does not exist.
    """
    if self._session.get(DocumentRow, parent_id) is None:
      return None
    data = self._build_child_document_row(parent_id)
    self._session.commit()
    return data

  def _build_child_document_row(self, parent_id: str) -> dict:
    """Add a child DocumentRow to the session without committing.

    Callers are responsible for the commit so that the operation can be
    composed into a larger atomic transaction.
    """
    doc_id = str(uuid.uuid4())
    title = "새 문서"
    self._session.add(DocumentRow(id=doc_id, title=title, subtitle="", parent_id=parent_id))
    return {"id": doc_id, "title": title, "subtitle": "", "parent_id": parent_id, "children": []}

  def _is_descendant(self, ancestor_id: str, candidate_id: str) -> bool:
    """Return True if *candidate_id* is *ancestor_id* or a descendant of it.

    Guards against pre-existing cycles in the parent_id chain via a visited set
    so the loop always terminates.
    """
    visited: set[str] = set()
    current: str | None = candidate_id
    while current is not None:
      if current in visited:
        break  # cycle detected — stop traversal
      visited.add(current)
      if current == ancestor_id:
        return True
      row = self._session.get(DocumentRow, current)
      if row is None:
        break
      current = row.parent_id
    return False

  def update_document_title(self, document_id: str, title: str) -> bool:
    doc_row = self._session.get(DocumentRow, document_id)
    if doc_row is None:
      return False
    doc_row.title = title
    self._session.commit()
    return True

  def delete_document(self, document_id: str) -> bool:
    doc_row = self._session.get(DocumentRow, document_id)
    if doc_row is None:
      return False
    # Promote direct children to root so they are not orphaned
    self._session.execute(
      update(DocumentRow)
      .where(DocumentRow.parent_id == document_id)
      .values(parent_id=None)
    )
    self._session.delete(doc_row)
    self._session.commit()
    return True

  # ── Blocks ─────────────────────────────────────────────────────────────────

  def update_block(self, block_id: str, patch: dict[str, Any]) -> bool:
    """Merge patch fields into a block's content_json. Returns False if block not found."""
    block_row = self._session.get(BlockRow, block_id)
    if block_row is None:
      return False
    content = json.loads(block_row.content_json)
    content.update(patch)
    block_row.content_json = json.dumps(content, ensure_ascii=False)
    self._session.commit()
    return True

  def create_block(
    self,
    document_id: str,
    block_type: str,
    parent_block_id: str | None = None,
    target_document_id: str | None = None,
  ) -> dict[str, Any] | None:
    """Append a new block of the given type at the end of its sibling list.

    Returns the created block data, or None if document not found or type is unsupported.
    """
    if self._session.get(DocumentRow, document_id) is None:
      return None

    if parent_block_id is not None:
      parent_exists = self._session.execute(
        select(BlockRow.id).where(
          BlockRow.id == parent_block_id,
          BlockRow.document_id == document_id,
        )
      ).scalar_one_or_none()
      if parent_exists is None:
        return None

    # ── Page block: link to existing or auto-create a child document ─────────
    if block_type == "page":
      if target_document_id is not None:
        # Reference an existing document without changing its parent.
        if self._session.get(DocumentRow, target_document_id) is None:
          return None
        default_content: dict[str, Any] = {
          "document_id": target_document_id,
          "is_reference": True,
        }
        child_doc = None
      else:
        # Use _build_child_document_row (no commit) so both the new document and
        # the page block are committed together below, keeping the DB consistent.
        child_doc = self._build_child_document_row(document_id)
        default_content = {"document_id": child_doc["id"], "is_reference": False}
    else:
      match block_type:
        case "text":
          default_content = {"text": ""}
        case "image":
          default_content = {"url": "", "caption": ""}
        case "toggle":
          default_content = {"text": "", "is_open": True}
        case "quote":
          default_content = {"text": ""}
        case "code":
          default_content = {"code": "", "language": "plain"}
        case "callout":
          default_content = {"text": "", "emoji": "💡", "color": "yellow"}
        case "divider":
          default_content = {}
        case _:
          return None

    parent_filter = (
      BlockRow.parent_block_id.is_(None)
      if parent_block_id is None
      else BlockRow.parent_block_id == parent_block_id
    )
    max_pos = self._session.execute(
      select(func.coalesce(func.max(BlockRow.position), 0))
      .where(BlockRow.document_id == document_id, parent_filter)
    ).scalar_one()

    block_id = str(uuid.uuid4())
    self._session.add(BlockRow(
      id=block_id,
      document_id=document_id,
      parent_block_id=parent_block_id,
      type=block_type,
      position=max_pos + 1,
      content_json=json.dumps(default_content, ensure_ascii=False),
    ))

    # ── Container blocks: auto-create one child text block ────────────────────
    child_text_row: dict[str, Any] | None = None
    if block_type in _CHILD_BEARING_TYPES:
      child_id = str(uuid.uuid4())
      self._session.add(BlockRow(
        id=child_id,
        document_id=document_id,
        parent_block_id=block_id,
        type="text",
        position=1,
        content_json=json.dumps({"text": ""}, ensure_ascii=False),
      ))
      child_text_row = {"id": child_id, "type": "text", "text": ""}

    self._session.commit()

    result: dict[str, Any] = {"id": block_id, "type": block_type, **default_content}
    if block_type == "page":
      if child_doc is not None:
        result["title"] = child_doc["title"]
        result["child_document"] = child_doc
      else:
        ref_title = self._session.execute(
          select(DocumentRow.title).where(DocumentRow.id == target_document_id)
        ).scalar_one_or_none()
        result["title"] = ref_title or ""
    if child_text_row is not None:
      result["children"] = [child_text_row]
    return result

  def delete_block(self, block_id: str) -> bool:
    """Delete a block and all its descendants. Compacts sibling positions after deletion.

    For owned page blocks (is_reference=False) the referenced document is promoted
    to root (parent_id cleared) so it is not orphaned.
    Reference page blocks (is_reference=True) are removed without touching the
    target document's parent hierarchy.
    """
    block_row = self._session.get(BlockRow, block_id)
    if block_row is None:
      return False

    # Promote referenced document to root only when this page block owns it.
    # Reference blocks (is_reference=True) merely link to an existing document
    # whose parent hierarchy must not be disturbed.
    if block_row.type == "page":
      content = json.loads(block_row.content_json)
      ref_doc_id = content.get("document_id")
      if ref_doc_id and not content.get("is_reference", False):
        self._session.execute(
          update(DocumentRow)
          .where(DocumentRow.id == ref_doc_id)
          .values(parent_id=None)
        )

    document_id = block_row.document_id
    parent_block_id = block_row.parent_block_id
    position = block_row.position

    all_ids = self._collect_subtree_ids(block_id)
    self._session.execute(delete(BlockRow).where(BlockRow.id.in_(all_ids)))

    parent_filter = (
      BlockRow.parent_block_id.is_(None)
      if parent_block_id is None
      else BlockRow.parent_block_id == parent_block_id
    )
    self._session.execute(
      update(BlockRow)
      .where(BlockRow.document_id == document_id, parent_filter, BlockRow.position > position)
      .values(position=BlockRow.position - 1)
    )
    self._session.commit()

    # ── Cascade: if parent container is now empty, delete it too ─────────────
    if parent_block_id is not None:
      parent_row = self._session.get(BlockRow, parent_block_id)
      if parent_row is not None and parent_row.type in _CHILD_BEARING_TYPES:
        remaining = self._session.execute(
          select(func.count()).where(BlockRow.parent_block_id == parent_block_id)
        ).scalar_one()
        if remaining == 0:
          self.delete_block(parent_block_id)

    return True

  def _collect_subtree_ids(self, root_id: str) -> list[str]:
    """Collect root_id and all descendant block IDs via a single recursive CTE."""
    rows = self._session.execute(
      text("""
        WITH RECURSIVE subtree(id) AS (
          SELECT id FROM blocks WHERE id = :root_id
          UNION ALL
          SELECT b.id FROM blocks b
          INNER JOIN subtree s ON b.parent_block_id = s.id
        )
        SELECT id FROM subtree
      """),
      {"root_id": root_id},
    ).fetchall()
    return [row[0] for row in rows]

  def change_block_type(self, block_id: str, new_type: str) -> bool:
    """Change a block's type and reset its content to defaults.

    Deletes all descendant blocks (important when changing FROM container).
    Returns False if block_id not found or new_type is unsupported.
    """
    match new_type:
      case "text":
        default_content: dict[str, Any] = {"text": ""}
      case "image":
        default_content = {"url": "", "caption": ""}
      case "toggle":
        default_content = {"text": "", "is_open": True}
      case "quote":
        default_content = {"text": ""}
      case "code":
        default_content = {"code": "", "language": "plain"}
      case "callout":
        default_content = {"text": "", "emoji": "💡", "color": "yellow"}
      case "divider":
        default_content = {}
      case _:
        return False

    block_row = self._session.get(BlockRow, block_id)
    if block_row is None:
      return False

    document_id = block_row.document_id

    # Delete all descendants (covers container children)
    all_ids = self._collect_subtree_ids(block_id)
    descendant_ids = [i for i in all_ids if i != block_id]
    if descendant_ids:
      self._session.execute(delete(BlockRow).where(BlockRow.id.in_(descendant_ids)))

    block_row.type = new_type
    block_row.content_json = json.dumps(default_content, ensure_ascii=False)

    # Container types: auto-create one child text block
    if new_type in _CHILD_BEARING_TYPES:
      child_id = str(uuid.uuid4())
      self._session.add(BlockRow(
        id=child_id,
        document_id=document_id,
        parent_block_id=block_id,
        type="text",
        position=1,
        content_json=json.dumps({"text": ""}, ensure_ascii=False),
      ))

    self._session.commit()
    return True

  def move_block(self, block_id: str, before_block_id: str | None) -> bool | None:
    """Reorder a block among its siblings.

    Moves block_id to be immediately before before_block_id.
    If before_block_id is None, moves to the end of the sibling list.

    Returns:
      True   — success (including no-op when before_block_id == block_id)
      None   — block_id not found
      False  — before_block_id is not a valid sibling
    """
    block_row = self._session.get(BlockRow, block_id)
    if block_row is None:
      return None

    if before_block_id == block_id:
      return True

    document_id = block_row.document_id
    parent_block_id = block_row.parent_block_id

    parent_filter = (
      BlockRow.parent_block_id.is_(None)
      if parent_block_id is None
      else BlockRow.parent_block_id == parent_block_id
    )
    sibling_ids: list[str] = list(self._session.execute(
      select(BlockRow.id)
      .where(BlockRow.document_id == document_id, parent_filter, BlockRow.id != block_id)
      .order_by(BlockRow.position.asc())
    ).scalars().all())

    if before_block_id is None:
      sibling_ids.append(block_id)
    elif before_block_id in sibling_ids:
      sibling_ids.insert(sibling_ids.index(before_block_id), block_id)
    else:
      return False

    for i, sid in enumerate(sibling_ids, start=1):
      self._session.execute(update(BlockRow).where(BlockRow.id == sid).values(position=i))
    self._session.commit()
    return True

  # ── Seed ───────────────────────────────────────────────────────────────────

  def _seed_if_empty(self) -> None:
    count = self._session.execute(select(func.count()).select_from(DocumentRow)).scalar_one()
    if count > 0:
      return

    intro_id = "project-manager-intro"
    stack_id = "tech-stack"

    self._session.add_all([
      DocumentRow(id=intro_id, title="Project Manager 소개", subtitle="블록 기반 프로젝트 관리 도구"),
      DocumentRow(id=stack_id, title="기술 스택", subtitle="이 프로젝트에서 사용하는 기술 목록"),
    ])

    self._session.add_all([
      # ── intro document ──────────────────────────────────────────────────────
      BlockRow(id="b-overview-text", document_id=intro_id, parent_block_id=None, type="text", position=1,
               content_json=json.dumps({"text": "Project Manager는 노션 스타일의 블록 인터페이스로 프로젝트와 문서를 관리하는 도구입니다."})),
      BlockRow(id="b-overview-image", document_id=intro_id, parent_block_id=None, type="image", position=2,
               content_json=json.dumps({
                 "url": "https://images.unsplash.com/photo-1611532736597-de2d4265fba3?auto=format&fit=crop&w=1200&q=80",
                 "caption": "블록으로 구성하는 프로젝트 문서",
               })),
      BlockRow(id="b-block-text", document_id=intro_id, parent_block_id=None, type="text", position=3,
               content_json=json.dumps({"text": "텍스트 블록: 프로젝트 설명, 요구사항, 메모 등 텍스트 콘텐츠를 기록합니다."})),
      BlockRow(id="b-block-image", document_id=intro_id, parent_block_id=None, type="text", position=4,
               content_json=json.dumps({"text": "이미지 블록: 스크린샷, 다이어그램, 참고 이미지를 문서에 삽입합니다."})),
      BlockRow(id="b-page-stack", document_id=intro_id, parent_block_id=None, type="page", position=5,
               content_json=json.dumps({"document_id": stack_id})),
      # ── tech-stack document ─────────────────────────────────────────────────
      BlockRow(id="b-stack-fastapi", document_id=stack_id, parent_block_id=None, type="text", position=1,
               content_json=json.dumps({"text": "FastAPI — Python 기반 비동기 웹 프레임워크"})),
      BlockRow(id="b-stack-sqlite", document_id=stack_id, parent_block_id=None, type="text", position=2,
               content_json=json.dumps({"text": "SQLite — 경량 내장형 관계형 데이터베이스"})),
      BlockRow(id="b-stack-pydantic", document_id=stack_id, parent_block_id=None, type="text", position=3,
               content_json=json.dumps({"text": "Pydantic v2 — 타입 기반 데이터 검증"})),
      BlockRow(id="b-page-intro", document_id=stack_id, parent_block_id=None, type="page", position=4,
               content_json=json.dumps({"document_id": intro_id})),
    ])
    self._session.commit()
