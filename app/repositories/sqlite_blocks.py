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
  ColumnSchema,
  DatabaseBlock,
  DbContext,
  DbRowBlock,
  DividerBlock,
  FileBlock,
  PageBlock,
  QuoteBlock,
  ToggleBlock,
)
from app.models.orm import BlockRow, DocumentRow, FileRow


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
    """Return all documents as a parent-child tree, with database blocks as virtual folder nodes.

    트리 구조:
      Document
        ├── Child Page          (page block 자식 문서)
        └── [db:block_id]       (is_database=True 가상 노드 — database 블록)
              └── db_row 문서   (is_db_row=True)

    db_row 문서의 parent_id는 "db:{database_block_id}" 형태로 가상 노드를 가리킨다.
    """
    doc_rows = self._session.execute(
      select(DocumentRow).order_by(DocumentRow.title)
    ).scalars().all()

    # ── database 블록 조회 ────────────────────────────────────────────────────
    db_blocks = self._session.execute(
      select(BlockRow).where(BlockRow.type == "database")
    ).scalars().all()

    # db_row 블록 조회 (parent = database 블록)
    db_block_ids = [b.id for b in db_blocks]
    db_row_block_to_db: dict[str, str] = {}  # db_row_block_id → database_block_id
    if db_block_ids:
      row_blocks = self._session.execute(
        select(BlockRow.id, BlockRow.parent_block_id).where(
          BlockRow.type == "db_row",
          BlockRow.parent_block_id.in_(db_block_ids),
        )
      ).all()
      db_row_block_to_db = {rb.id: rb.parent_block_id for rb in row_blocks}

    # source_block_id → database_block_id
    doc_to_db: dict[str, str] = {}
    for r in doc_rows:
      if r.source_block_id and r.source_block_id in db_row_block_to_db:
        doc_to_db[r.id] = db_row_block_to_db[r.source_block_id]

    # ── 가상 database 노드 생성 ───────────────────────────────────────────────
    db_virtual: dict[str, dict] = {}
    for b in db_blocks:
      content = json.loads(b.content_json)
      node_id = f"db:{b.id}"
      db_virtual[node_id] = {
        "id": node_id,
        "block_id": b.id,
        "title": content.get("title") or "데이터베이스",
        "is_database": True,
        "parent_id": b.document_id,
        "parent_doc_id": b.document_id,
        "children": [],
      }

    # ── 문서 노드 생성 ─────────────────────────────────────────────────────────
    all_items: list[dict] = list(db_virtual.values())
    for r in doc_rows:
      db_block_id = doc_to_db.get(r.id)
      parent_ref = f"db:{db_block_id}" if db_block_id else r.parent_id
      all_items.append({
        "id": r.id,
        "title": r.title,
        "subtitle": r.subtitle,
        "parent_id": parent_ref,
        "is_db_row": db_block_id is not None,
        "children": [],
      })

    # ── 트리 조립 ─────────────────────────────────────────────────────────────
    by_id = {item["id"]: item for item in all_items}
    roots: list[dict] = []
    for item in all_items:
      pid = item["parent_id"]
      if pid and pid in by_id:
        by_id[pid]["children"].append(item)
      elif not item.get("is_db_row") and not item.get("is_database"):
        roots.append(item)

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
      if item["type"] in ("page", "db_row") and "document_id" in item
    })
    doc_titles: dict[str, str] = {}
    if page_doc_ids:
      title_rows = self._session.execute(
        select(DocumentRow.id, DocumentRow.title).where(DocumentRow.id.in_(page_doc_ids))
      ).all()
      doc_titles = {row.id: row.title for row in title_rows}

    # file 블록 메타데이터 일괄 조회 — query-time 주입으로 FileBlock 필드를 채운다
    file_ids = list({
      item["file_id"]
      for item in parsed_blocks
      if item["type"] == "file" and item.get("file_id")
    })
    file_meta: dict[str, dict[str, Any]] = {}
    if file_ids:
      file_rows = self._session.execute(
        select(FileRow).where(FileRow.id.in_(file_ids))
      ).scalars().all()
      file_meta = {
        r.id: {
          "original_filename": r.original_filename,
          "size_bytes": r.size_bytes,
          "mime_type": r.mime_type,
          "download_url": f"/api/files/{r.id}",
        }
        for r in file_rows
      }

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
        elif item["type"] == "database":
          nodes.append(self._build_database_block(item))
        elif item["type"] == "db_row":
          # db_row는 database 블록 내부에서만 등장 (build_database_block 처리)
          # 최상위에 고아로 있는 경우 무시
          pass
        elif item["type"] == "file":
          # file_id가 있는 경우 FileRow에서 조회한 메타데이터를 병합한다
          fid = item.get("file_id", "")
          meta = file_meta.get(fid, {}) if fid else {}
          nodes.append(FileBlock.model_validate({**item, **meta}))
        else:
          nodes.append(self._block_adapter.validate_python(item))
      return nodes

    # ── db_context: 이 페이지가 db_row 페이지인지 확인 ────────────────────────
    db_context: DbContext | None = None
    if doc_row.source_block_id:
      db_context = self._build_db_context(doc_row.source_block_id)

    return BlockDocument(
      id=doc_row.id,
      title=doc_row.title,
      subtitle=doc_row.subtitle,
      blocks=build_nodes(None),
      db_context=db_context,
    )

  def _build_database_block(self, item: dict[str, Any]) -> DatabaseBlock:
    """DatabaseBlock을 조립: 자식 db_row 블록들을 rows로 채워 반환."""
    db_block_id = item["id"]
    schema_raw = item.get("columns", [])
    schema = [ColumnSchema.model_validate(c) for c in schema_raw]

    row_blocks = self._session.execute(
      select(BlockRow)
      .where(
        BlockRow.parent_block_id == db_block_id,
        BlockRow.type == "db_row",
      )
      .order_by(BlockRow.position.asc())
    ).scalars().all()

    # 행 문서 제목 일괄 조회
    row_doc_ids = [json.loads(r.content_json).get("document_id", "") for r in row_blocks]
    valid_ids = [did for did in row_doc_ids if did]
    title_map: dict[str, str] = {}
    if valid_ids:
      title_rows = self._session.execute(
        select(DocumentRow.id, DocumentRow.title).where(DocumentRow.id.in_(valid_ids))
      ).all()
      title_map = {r.id: r.title for r in title_rows}

    rows: list[DbRowBlock] = []
    for rb in row_blocks:
      content = json.loads(rb.content_json)
      doc_id = content.get("document_id", "")
      is_broken = bool(doc_id) and doc_id not in title_map
      rows.append(DbRowBlock.model_validate({
        "id": rb.id,
        "type": "db_row",
        "document_id": doc_id,
        "title": "" if is_broken else title_map.get(doc_id, ""),
        "is_reference": False,
        "is_broken_ref": is_broken,
        "properties": content.get("properties", {}),
      }))

    return DatabaseBlock.model_validate({
      **item,
      "columns": schema,
      "rows": rows,
    })

  def _build_db_context(self, db_row_block_id: str) -> DbContext | None:
    """db_row 블록 id로 DbContext를 조립. 블록이 없으면 None 반환."""
    row_block = self._session.get(BlockRow, db_row_block_id)
    if row_block is None or row_block.type != "db_row":
      return None

    content = json.loads(row_block.content_json)
    properties = content.get("properties", {})

    # 부모 DatabaseBlock 조회
    db_block_id = row_block.parent_block_id
    if db_block_id is None:
      return None
    db_block = self._session.get(BlockRow, db_block_id)
    if db_block is None or db_block.type != "database":
      return None

    db_content = json.loads(db_block.content_json)
    schema = [ColumnSchema.model_validate(c) for c in db_content.get("columns", [])]

    return DbContext(
      block_id=db_row_block_id,
      db_block_id=db_block_id,
      columns=schema,
      properties=properties,
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

  def _build_child_document_row(self, parent_id: str, source_block_id: str | None = None) -> dict:
    """Add a child DocumentRow to the session without committing.

    Callers are responsible for the commit so that the operation can be
    composed into a larger atomic transaction.
    """
    doc_id = str(uuid.uuid4())
    title = "새 문서"
    self._session.add(DocumentRow(
      id=doc_id,
      title=title,
      subtitle="",
      parent_id=parent_id,
      source_block_id=source_block_id,
    ))
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
      parent_block = self._session.execute(
        select(BlockRow.id, BlockRow.type).where(
          BlockRow.id == parent_block_id,
          BlockRow.document_id == document_id,
        )
      ).one_or_none()
      if parent_block is None:
        return None
      # db_row는 반드시 database 블록 아래에만 생성 가능
      if block_type == "db_row" and parent_block.type != "database":
        return None

    child_doc: dict[str, Any] | None = None

    # ── Page block: link to existing or auto-create a child document ─────────
    if block_type == "page":
      if target_document_id is not None:
        if self._session.get(DocumentRow, target_document_id) is None:
          return None
        default_content: dict[str, Any] = {
          "document_id": target_document_id,
          "is_reference": True,
        }
        child_doc = None
      else:
        child_doc = self._build_child_document_row(document_id)
        default_content = {"document_id": child_doc["id"], "is_reference": False}

    # ── Database block ────────────────────────────────────────────────────────
    elif block_type == "database":
      default_content = {"title": "", "color": "default", "columns": []}

    # ── db_row block: always creates a child document ─────────────────────────
    elif block_type == "db_row":
      if parent_block_id is None:
        return None  # db_row는 반드시 database 블록의 자식이어야 함
      # db_row 블록 id를 미리 생성해 두어야 source_block_id에 연결할 수 있음
      block_id = str(uuid.uuid4())
      child_doc = self._build_child_document_row(document_id, source_block_id=block_id)
      default_content = {
        "document_id": child_doc["id"],
        "is_reference": False,
        "properties": {},
      }
      # 나머지 로직(position 계산 / BlockRow 추가)을 아래에서 계속 처리하기 위해
      # block_id를 미리 확정한다
      parent_filter = (
        BlockRow.parent_block_id.is_(None)
        if parent_block_id is None
        else BlockRow.parent_block_id == parent_block_id
      )
      max_pos = self._session.execute(
        select(func.coalesce(func.max(BlockRow.position), 0))
        .where(BlockRow.document_id == document_id, parent_filter)
      ).scalar_one()
      self._session.add(BlockRow(
        id=block_id,
        document_id=document_id,
        parent_block_id=parent_block_id,
        type=block_type,
        position=max_pos + 1,
        content_json=json.dumps(default_content, ensure_ascii=False),
      ))
      self._session.commit()

      doc_title = child_doc["title"]
      child_doc["is_db_row"] = True
      child_doc["parent_sidebar_id"] = f"db:{parent_block_id}"
      result: dict[str, Any] = {
        "id": block_id,
        "type": "db_row",
        "document_id": child_doc["id"],
        "title": doc_title,
        "is_reference": False,
        "is_broken_ref": False,
        "properties": {},
        "child_document": child_doc,
      }
      return result

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
        case "url_embed":
          default_content = {
            "url": "",
            "title": "",
            "description": "",
            "logo": "",
            "provider": "",
            "fetched_at": "",
            "status": "pending",
          }
        case "file":
          default_content = {"file_id": ""}
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

    result = {"id": block_id, "type": block_type, **default_content}
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

    For owned page/db_row blocks the referenced document is promoted to root
    so it is not orphaned.
    Reference page blocks (is_reference=True) are removed without touching the
    target document's parent hierarchy.
    """
    block_row = self._session.get(BlockRow, block_id)
    if block_row is None:
      return False

    # Promote referenced document to root only when this block owns it.
    if block_row.type in ("page", "db_row"):
      content = json.loads(block_row.content_json)
      ref_doc_id = content.get("document_id")
      if ref_doc_id and not content.get("is_reference", False):
        self._session.execute(
          update(DocumentRow)
          .where(DocumentRow.id == ref_doc_id)
          .values(parent_id=None, source_block_id=None)
        )

    # database 블록 삭제: 모든 db_row 자식의 문서를 root로 승격
    if block_row.type == "database":
      row_blocks = self._session.execute(
        select(BlockRow).where(
          BlockRow.parent_block_id == block_id,
          BlockRow.type == "db_row",
        )
      ).scalars().all()
      for rb in row_blocks:
        content = json.loads(rb.content_json)
        ref_doc_id = content.get("document_id")
        if ref_doc_id:
          self._session.execute(
            update(DocumentRow)
            .where(DocumentRow.id == ref_doc_id)
            .values(parent_id=None, source_block_id=None)
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
      case "url_embed":
        default_content = {
          "url": "",
          "title": "",
          "description": "",
          "logo": "",
          "provider": "",
          "fetched_at": "",
          "status": "pending",
        }
      case "file":
        default_content = {"file_id": ""}
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

  # ── Database-specific operations ───────────────────────────────────────────

  def update_db_row_properties(self, block_id: str, properties: dict[str, Any]) -> bool:
    """Replace all properties on a db_row block. Returns False if not found."""
    block_row = self._session.get(BlockRow, block_id)
    if block_row is None or block_row.type != "db_row":
      return False
    content = json.loads(block_row.content_json)
    content["properties"] = properties
    block_row.content_json = json.dumps(content, ensure_ascii=False)
    self._session.commit()
    return True

  def add_db_column(self, db_block_id: str, column: dict[str, Any]) -> bool:
    """Append a new column to the database block. Returns False if not found."""
    block_row = self._session.get(BlockRow, db_block_id)
    if block_row is None or block_row.type != "database":
      return False
    content = json.loads(block_row.content_json)
    cols: list[dict] = content.get("columns", [])
    cols.append(column)
    content["columns"] = cols
    block_row.content_json = json.dumps(content, ensure_ascii=False)
    self._session.commit()
    return True

  def update_db_column(self, db_block_id: str, col_id: str, patch: dict[str, Any]) -> bool:
    """Update a column's name/type/options. Returns False if not found."""
    block_row = self._session.get(BlockRow, db_block_id)
    if block_row is None or block_row.type != "database":
      return False
    content = json.loads(block_row.content_json)
    cols: list[dict] = content.get("columns", [])
    col = next((c for c in cols if c["id"] == col_id), None)
    if col is None:
      return False
    col.update({k: v for k, v in patch.items() if v is not None})
    block_row.content_json = json.dumps(content, ensure_ascii=False)
    self._session.commit()
    return True

  def remove_db_column(self, db_block_id: str, col_id: str) -> bool:
    """Remove a column and wipe its values from all rows."""
    block_row = self._session.get(BlockRow, db_block_id)
    if block_row is None or block_row.type != "database":
      return False
    content = json.loads(block_row.content_json)
    cols: list[dict] = content.get("columns", [])
    new_cols = [c for c in cols if c["id"] != col_id]
    if len(new_cols) == len(cols):
      return False  # column not found
    content["columns"] = new_cols
    block_row.content_json = json.dumps(content, ensure_ascii=False)

    # Remove property values for this column from all db_row children
    row_blocks = self._session.execute(
      select(BlockRow).where(
        BlockRow.parent_block_id == db_block_id,
        BlockRow.type == "db_row",
      )
    ).scalars().all()
    for rb in row_blocks:
      row_content = json.loads(rb.content_json)
      props: dict = row_content.get("properties", {})
      props.pop(col_id, None)
      row_content["properties"] = props
      rb.content_json = json.dumps(row_content, ensure_ascii=False)

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
