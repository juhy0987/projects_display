"""Tests for document rename feature (issue #29)."""
from __future__ import annotations


# ── Repository-level tests ────────────────────────────────────────────────────

class TestUpdateDocumentTitle:
  def test_rename_success(self, repo):
    doc = repo.create_document()
    result = repo.update_document_title(doc["id"], "새 이름")
    assert result is True

  def test_renamed_title_persisted(self, repo):
    doc = repo.create_document()
    repo.update_document_title(doc["id"], "변경된 제목")
    fetched = repo.get_document(doc["id"])
    assert fetched.title == "변경된 제목"

  def test_rename_nonexistent_returns_false(self, repo):
    result = repo.update_document_title("nonexistent-id", "제목")
    assert result is False

  def test_rename_reflected_in_list_documents(self, repo):
    doc = repo.create_document()
    repo.update_document_title(doc["id"], "목록 반영 테스트")
    tree = repo.list_documents()
    assert tree[0]["title"] == "목록 반영 테스트"

  def test_rename_reflected_in_page_block_title(self, repo):
    """page 블록이 참조하는 문서의 제목이 바뀌면 get_document 조회 시 반영된다."""
    parent = repo.create_document()
    block = repo.create_block(parent["id"], "page")
    child_id = block["document_id"]

    repo.update_document_title(child_id, "변경된 자식 제목")

    parent_doc = repo.get_document(parent["id"])
    page_block = next(b for b in parent_doc.blocks if b.type == "page")
    assert page_block.title == "변경된 자식 제목"


# ── API-level tests ───────────────────────────────────────────────────────────

class TestRenameDocumentApi:
  def test_patch_returns_200(self, client):
    doc = client.post("/api/documents").json()
    res = client.patch(f"/api/documents/{doc['id']}", json={"title": "API 제목"})
    assert res.status_code == 200

  def test_patch_returns_updated_title(self, client):
    doc = client.post("/api/documents").json()
    res = client.patch(f"/api/documents/{doc['id']}", json={"title": "응답 제목"})
    assert res.json()["title"] == "응답 제목"

  def test_patch_nonexistent_returns_404(self, client):
    res = client.patch("/api/documents/nonexistent-id", json={"title": "제목"})
    assert res.status_code == 404

  def test_blank_title_falls_back_to_default(self, client):
    doc = client.post("/api/documents").json()
    res = client.patch(f"/api/documents/{doc['id']}", json={"title": "   "})
    assert res.status_code == 200
    assert res.json()["title"] == "새 문서"

  def test_title_over_max_length_returns_422(self, client):
    doc = client.post("/api/documents").json()
    long_title = "가" * 101
    res = client.patch(f"/api/documents/{doc['id']}", json={"title": long_title})
    assert res.status_code == 422

  def test_title_at_max_length_succeeds(self, client):
    doc = client.post("/api/documents").json()
    exact_title = "가" * 100
    res = client.patch(f"/api/documents/{doc['id']}", json={"title": exact_title})
    assert res.status_code == 200
    assert res.json()["title"] == exact_title

  def test_rename_persisted_on_get(self, client):
    doc = client.post("/api/documents").json()
    client.patch(f"/api/documents/{doc['id']}", json={"title": "저장 확인"})
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert fetched["title"] == "저장 확인"

  def test_rename_reflected_in_document_list(self, client):
    doc = client.post("/api/documents").json()
    client.patch(f"/api/documents/{doc['id']}", json={"title": "목록 반영"})
    docs = client.get("/api/documents").json()
    titles = {d["title"] for d in docs}
    assert "목록 반영" in titles

  def test_rename_reflected_in_page_block(self, client):
    """참조 문서의 제목 변경이 page 블록 조회 시 반영된다."""
    parent = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{parent['id']}/blocks", json={"type": "page"}
    ).json()
    child_id = block["document_id"]

    client.patch(f"/api/documents/{child_id}", json={"title": "전파 테스트"})

    parent_doc = client.get(f"/api/documents/{parent['id']}").json()
    page_block = next(b for b in parent_doc["blocks"] if b["type"] == "page")
    assert page_block["title"] == "전파 테스트"
