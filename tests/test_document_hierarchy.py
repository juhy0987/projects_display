"""Tests for document parent-child hierarchy (issue #28)."""
from __future__ import annotations

import pytest


# ── Repository-level tests ────────────────────────────────────────────────────

class TestListDocuments:
  def test_returns_empty_list_when_no_documents(self, repo):
    assert repo.list_documents() == []

  def test_root_documents_have_empty_children(self, repo):
    repo.create_document()
    docs = repo.list_documents()
    assert len(docs) == 1
    assert docs[0]["children"] == []
    assert docs[0]["parent_id"] is None

  def test_child_nested_under_parent(self, repo):
    parent = repo.create_document()
    child = repo.create_child_document(parent["id"])

    tree = repo.list_documents()
    assert len(tree) == 1  # only root
    assert tree[0]["id"] == parent["id"]
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["id"] == child["id"]

  def test_deep_nesting(self, repo):
    grandparent = repo.create_document()
    parent = repo.create_child_document(grandparent["id"])
    child = repo.create_child_document(parent["id"])

    tree = repo.list_documents()
    assert len(tree) == 1
    gp_node = tree[0]
    assert gp_node["id"] == grandparent["id"]
    p_node = gp_node["children"][0]
    assert p_node["id"] == parent["id"]
    c_node = p_node["children"][0]
    assert c_node["id"] == child["id"]

  def test_multiple_roots_and_children(self, repo):
    root1 = repo.create_document()
    root2 = repo.create_document()
    child1 = repo.create_child_document(root1["id"])
    child2 = repo.create_child_document(root1["id"])

    tree = repo.list_documents()
    root_ids = {d["id"] for d in tree}
    assert root_ids == {root1["id"], root2["id"]}

    root1_node = next(d for d in tree if d["id"] == root1["id"])
    child_ids = {c["id"] for c in root1_node["children"]}
    assert child_ids == {child1["id"], child2["id"]}


class TestCreateChildDocument:
  def test_returns_none_for_missing_parent(self, repo):
    result = repo.create_child_document("nonexistent-id")
    assert result is None

  def test_child_has_correct_parent_id(self, repo):
    parent = repo.create_document()
    child = repo.create_child_document(parent["id"])
    assert child["parent_id"] == parent["id"]

  def test_child_appears_in_tree(self, repo):
    parent = repo.create_document()
    child = repo.create_child_document(parent["id"])
    tree = repo.list_documents()
    assert tree[0]["children"][0]["id"] == child["id"]


class TestDeleteDocumentWithChildren:
  def test_children_promoted_to_root_on_parent_delete(self, repo):
    parent = repo.create_document()
    child = repo.create_child_document(parent["id"])

    repo.delete_document(parent["id"])

    tree = repo.list_documents()
    ids = {d["id"] for d in tree}
    assert parent["id"] not in ids
    assert child["id"] in ids

  def test_grandchildren_promoted_when_parent_deleted(self, repo):
    gp = repo.create_document()
    parent = repo.create_child_document(gp["id"])
    child = repo.create_child_document(parent["id"])

    # Delete middle node → child promoted to root; gp still exists
    repo.delete_document(parent["id"])
    tree = repo.list_documents()
    root_ids = {d["id"] for d in tree}
    assert gp["id"] in root_ids
    assert parent["id"] not in root_ids
    assert child["id"] in root_ids


class TestIsDescendant:
  def test_self_is_descendant(self, repo):
    doc = repo.create_document()
    assert repo._is_descendant(doc["id"], doc["id"]) is True

  def test_child_is_descendant(self, repo):
    parent = repo.create_document()
    child = repo.create_child_document(parent["id"])
    assert repo._is_descendant(parent["id"], child["id"]) is True

  def test_grandchild_is_descendant(self, repo):
    gp = repo.create_document()
    parent = repo.create_child_document(gp["id"])
    child = repo.create_child_document(parent["id"])
    assert repo._is_descendant(gp["id"], child["id"]) is True

  def test_unrelated_document_not_descendant(self, repo):
    doc1 = repo.create_document()
    doc2 = repo.create_document()
    assert repo._is_descendant(doc1["id"], doc2["id"]) is False

  def test_parent_not_descendant_of_child(self, repo):
    parent = repo.create_document()
    child = repo.create_child_document(parent["id"])
    assert repo._is_descendant(child["id"], parent["id"]) is False


# ── Page block → child document (issue #28 core feature) ─────────────────────

class TestPageBlockCreatesChildDocument:
  def test_page_block_auto_creates_child_document(self, repo):
    parent_doc = repo.create_document()
    result = repo.create_block(parent_doc["id"], "page")

    assert result is not None
    assert result["type"] == "page"
    assert "document_id" in result
    assert "child_document" in result

  def test_child_document_has_correct_parent_id(self, repo):
    parent_doc = repo.create_document()
    result = repo.create_block(parent_doc["id"], "page")

    child = result["child_document"]
    assert child["parent_id"] == parent_doc["id"]

  def test_child_document_appears_in_sidebar_tree(self, repo):
    parent_doc = repo.create_document()
    result = repo.create_block(parent_doc["id"], "page")
    child_id = result["document_id"]

    tree = repo.list_documents()
    parent_node = next(d for d in tree if d["id"] == parent_doc["id"])
    child_ids = {c["id"] for c in parent_node["children"]}
    assert child_id in child_ids

  def test_page_block_contains_child_doc_id(self, repo):
    parent_doc = repo.create_document()
    result = repo.create_block(parent_doc["id"], "page")

    assert result["document_id"] == result["child_document"]["id"]

  def test_page_block_returns_404_for_missing_document(self, repo):
    result = repo.create_block("nonexistent-id", "page")
    assert result is None


class TestPageBlockDeletePromotesChildDocument:
  def test_deleting_page_block_promotes_child_to_root(self, repo):
    parent_doc = repo.create_document()
    block = repo.create_block(parent_doc["id"], "page")
    child_id = block["document_id"]
    block_id = block["id"]

    # Child should currently be under parent
    tree = repo.list_documents()
    parent_node = next(d for d in tree if d["id"] == parent_doc["id"])
    assert any(c["id"] == child_id for c in parent_node["children"])

    # Delete the page block
    repo.delete_block(block_id)

    # Child should now be at root
    tree = repo.list_documents()
    root_ids = {d["id"] for d in tree}
    assert child_id in root_ids

    parent_node = next(d for d in tree if d["id"] == parent_doc["id"])
    assert not any(c["id"] == child_id for c in parent_node["children"])

  def test_child_document_content_preserved_after_block_delete(self, repo):
    parent_doc = repo.create_document()
    block = repo.create_block(parent_doc["id"], "page")
    child_id = block["document_id"]

    repo.delete_block(block["id"])

    # Child document still exists
    child = repo.get_document(child_id)
    assert child is not None
    assert child.id == child_id


# ── API-level tests ───────────────────────────────────────────────────────────

class TestDocumentListApi:
  def test_returns_tree_structure(self, client):
    r1 = client.post("/api/documents").json()
    r2 = client.post("/api/documents").json()
    # Create a child via page block
    client.post(f"/api/documents/{r1['id']}/blocks", json={"type": "page"})

    docs = client.get("/api/documents").json()
    root_ids = {d["id"] for d in docs}
    assert r2["id"] in root_ids
    r1_node = next(d for d in docs if d["id"] == r1["id"])
    assert len(r1_node["children"]) == 1

  def test_root_documents_have_children_field(self, client):
    client.post("/api/documents")
    docs = client.get("/api/documents").json()
    assert "children" in docs[0]


class TestPageBlockApi:
  def test_create_page_block_returns_201(self, client):
    doc = client.post("/api/documents").json()
    res = client.post(f"/api/documents/{doc['id']}/blocks", json={"type": "page"})
    assert res.status_code == 201

  def test_response_contains_child_document(self, client):
    doc = client.post("/api/documents").json()
    block = client.post(f"/api/documents/{doc['id']}/blocks", json={"type": "page"}).json()
    assert "child_document" in block
    assert block["child_document"]["parent_id"] == doc["id"]

  def test_child_document_visible_in_tree(self, client):
    doc = client.post("/api/documents").json()
    block = client.post(f"/api/documents/{doc['id']}/blocks", json={"type": "page"}).json()
    child_id = block["document_id"]

    docs = client.get("/api/documents").json()
    parent_node = next(d for d in docs if d["id"] == doc["id"])
    child_ids = {c["id"] for c in parent_node["children"]}
    assert child_id in child_ids

  def test_deleting_page_block_promotes_child_to_root(self, client):
    doc = client.post("/api/documents").json()
    block = client.post(f"/api/documents/{doc['id']}/blocks", json={"type": "page"}).json()
    child_id = block["document_id"]
    block_id = block["id"]

    client.delete(f"/api/blocks/{block_id}")

    docs = client.get("/api/documents").json()
    root_ids = {d["id"] for d in docs}
    assert child_id in root_ids


class TestDeleteDocumentApi:
  def test_children_become_roots_after_delete(self, client):
    parent = client.post("/api/documents").json()
    block = client.post(f"/api/documents/{parent['id']}/blocks", json={"type": "page"}).json()
    child_id = block["document_id"]

    client.delete(f"/api/documents/{parent['id']}")

    docs = client.get("/api/documents").json()
    root_ids = {d["id"] for d in docs}
    assert parent["id"] not in root_ids
    assert child_id in root_ids
