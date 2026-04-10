"""Tests for container-type block interface extension (issue #27).

Covers toggle, quote, code, callout block creation, update, type change,
child nesting, and delete/subtree logic via both repository and API layers.
"""
from __future__ import annotations

import pytest


# ── Repository-level tests ────────────────────────────────────────────────────

class TestCreateContainerBlocks:
  """create_block returns correct defaults for each new type."""

  @pytest.mark.parametrize("block_type,expected_keys", [
    ("toggle", {"title", "is_open"}),
    ("quote", {"text"}),
    ("code", {"code", "language"}),
    ("callout", {"text", "emoji", "color"}),
  ])
  def test_create_returns_correct_fields(self, repo, block_type, expected_keys):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], block_type)
    assert block is not None
    assert block["type"] == block_type
    for key in expected_keys:
      assert key in block

  def test_toggle_defaults(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "toggle")
    assert block["title"] == ""
    assert block["is_open"] is False

  def test_code_defaults(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "code")
    assert block["code"] == ""
    assert block["language"] == "plain"

  def test_callout_defaults(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "callout")
    assert block["emoji"] == "💡"
    assert block["color"] == "yellow"


class TestUpdateContainerBlocks:
  """update_block persists type-specific fields correctly."""

  def test_update_toggle_title_and_open(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "toggle")
    assert repo.update_block(block["id"], {"title": "섹션 제목", "is_open": True})
    fetched = repo.get_document(doc["id"])
    toggle = fetched.blocks[0]
    assert toggle.title == "섹션 제목"
    assert toggle.is_open is True

  def test_update_quote_text(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "quote")
    assert repo.update_block(block["id"], {"text": "인용 문구"})
    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].text == "인용 문구"

  def test_update_code_content_and_language(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "code")
    assert repo.update_block(block["id"], {"code": "print('hi')", "language": "python"})
    fetched = repo.get_document(doc["id"])
    code_block = fetched.blocks[0]
    assert code_block.code == "print('hi')"
    assert code_block.language == "python"

  def test_update_callout_fields(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "callout")
    assert repo.update_block(block["id"], {"text": "주의", "emoji": "⚠️", "color": "red"})
    fetched = repo.get_document(doc["id"])
    callout = fetched.blocks[0]
    assert callout.text == "주의"
    assert callout.emoji == "⚠️"
    assert callout.color == "red"


class TestToggleChildNesting:
  """Children of toggle/quote/callout are loaded as nested Block objects."""

  def test_toggle_children_loaded(self, repo):
    doc = repo.create_document()
    parent = repo.create_block(doc["id"], "toggle")
    repo.create_block(doc["id"], "text", parent_block_id=parent["id"])
    repo.create_block(doc["id"], "text", parent_block_id=parent["id"])

    fetched = repo.get_document(doc["id"])
    toggle = fetched.blocks[0]
    assert toggle.type == "toggle"
    assert len(toggle.children) == 2

  def test_quote_children_loaded(self, repo):
    doc = repo.create_document()
    parent = repo.create_block(doc["id"], "quote")
    repo.create_block(doc["id"], "text", parent_block_id=parent["id"])

    fetched = repo.get_document(doc["id"])
    quote = fetched.blocks[0]
    assert quote.type == "quote"
    assert len(quote.children) == 1

  def test_callout_children_loaded(self, repo):
    doc = repo.create_document()
    parent = repo.create_block(doc["id"], "callout")
    repo.create_block(doc["id"], "text", parent_block_id=parent["id"])

    fetched = repo.get_document(doc["id"])
    callout = fetched.blocks[0]
    assert callout.type == "callout"
    assert len(callout.children) == 1

  def test_code_block_has_no_children_field(self, repo):
    from app.models.blocks import CodeBlock
    doc = repo.create_document()
    repo.create_block(doc["id"], "code")
    fetched = repo.get_document(doc["id"])
    assert isinstance(fetched.blocks[0], CodeBlock)
    assert not hasattr(fetched.blocks[0], "children")


class TestChangeBlockType:
  """change_block_type resets content and deletes descendants for new types."""

  @pytest.mark.parametrize("new_type", ["toggle", "quote", "code", "callout"])
  def test_change_to_new_type_succeeds(self, repo, new_type):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "text")
    assert repo.change_block_type(block["id"], new_type)
    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].type == new_type

  def test_change_from_toggle_deletes_children(self, repo):
    doc = repo.create_document()
    parent = repo.create_block(doc["id"], "toggle")
    repo.create_block(doc["id"], "text", parent_block_id=parent["id"])

    repo.change_block_type(parent["id"], "text")
    fetched = repo.get_document(doc["id"])
    # After change, the former toggle is now a text block with no children
    assert fetched.blocks[0].type == "text"
    assert len(fetched.blocks) == 1

  def test_change_to_code_resets_to_defaults(self, repo):
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "text")
    repo.update_block(block["id"], {"text": "hello"})
    repo.change_block_type(block["id"], "code")
    fetched = repo.get_document(doc["id"])
    code = fetched.blocks[0]
    assert code.code == ""
    assert code.language == "plain"


class TestDeleteContainerBlocks:
  """delete_block removes the block and all its descendants."""

  def test_delete_toggle_removes_children(self, repo):
    doc = repo.create_document()
    parent = repo.create_block(doc["id"], "toggle")
    repo.create_block(doc["id"], "text", parent_block_id=parent["id"])
    repo.create_block(doc["id"], "text", parent_block_id=parent["id"])

    assert repo.delete_block(parent["id"])
    fetched = repo.get_document(doc["id"])
    assert len(fetched.blocks) == 0


# ── API-level tests ───────────────────────────────────────────────────────────

class TestContainerBlocksAPI:
  """HTTP API smoke tests for new block types."""

  def _create_doc_and_block(self, client, block_type):
    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": block_type},
    ).json()
    return doc, block

  def test_create_toggle_via_api(self, client):
    doc = client.post("/api/documents").json()
    resp = client.post(f"/api/documents/{doc['id']}/blocks", json={"type": "toggle"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "toggle"
    assert "is_open" in data

  def test_create_code_via_api(self, client):
    doc = client.post("/api/documents").json()
    resp = client.post(f"/api/documents/{doc['id']}/blocks", json={"type": "code"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "code"
    assert data["language"] == "plain"

  def test_create_callout_via_api(self, client):
    doc = client.post("/api/documents").json()
    resp = client.post(f"/api/documents/{doc['id']}/blocks", json={"type": "callout"})
    assert resp.status_code == 201
    assert resp.json()["type"] == "callout"

  def test_patch_toggle_is_open(self, client):
    doc, block = self._create_doc_and_block(client, "toggle")
    resp = client.patch(f"/api/blocks/{block['id']}", json={"is_open": True})
    assert resp.status_code == 200

  def test_patch_code_language(self, client):
    doc, block = self._create_doc_and_block(client, "code")
    resp = client.patch(f"/api/blocks/{block['id']}", json={"language": "python", "code": "pass"})
    assert resp.status_code == 200

  def test_patch_callout_color(self, client):
    doc, block = self._create_doc_and_block(client, "callout")
    resp = client.patch(f"/api/blocks/{block['id']}", json={"color": "blue"})
    assert resp.status_code == 200

  @pytest.mark.parametrize("new_type", ["toggle", "quote", "code", "callout"])
  def test_type_change_to_new_types(self, client, new_type):
    doc, block = self._create_doc_and_block(client, "text")
    resp = client.patch(f"/api/blocks/{block['id']}/type", json={"type": new_type})
    assert resp.status_code == 200

  def test_get_document_includes_toggle_children(self, client):
    doc = client.post("/api/documents").json()
    parent = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "toggle"},
    ).json()
    client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "text", "parent_block_id": parent["id"]},
    )
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    toggle = fetched["blocks"][0]
    assert toggle["type"] == "toggle"
    assert len(toggle["children"]) == 1
