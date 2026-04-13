"""Mermaid 코드 블록 기능 단위 테스트 (이슈 #46).

커버리지 범위:
  1. Model 레이어   — CodeBlock 모델이 language="mermaid" 를 올바르게 처리하는지 검증
  2. Repository 레이어 — mermaid 코드 블록 생성·업데이트·타입 변환
  3. API 레이어    — POST/GET/PATCH /api/documents/{id}/blocks, PATCH /api/blocks/{id}
"""
from __future__ import annotations

import pytest


# ── 1. Model 레이어 ───────────────────────────────────────────────────────────

class TestCodeBlockModel:
  """CodeBlock Pydantic 모델이 mermaid 언어 옵션을 올바르게 수락하는지 검증."""

  def _make(self, language: str, code: str = "") -> object:
    from app.models.blocks import CodeBlock
    return CodeBlock(id="test-id", type="code", code=code, language=language)

  def test_mermaid_language_accepted(self):
    """language="mermaid" 로 CodeBlock 을 생성할 수 있다."""
    block = self._make("mermaid")
    assert block.language == "mermaid"

  def test_mermaid_code_stored(self):
    """mermaid 소스 코드가 code 필드에 그대로 저장된다."""
    src = "erDiagram\n  USER ||--o{ ORDER : places"
    block = self._make("mermaid", src)
    assert block.code == src

  def test_plain_language_unaffected(self):
    """기존 plain 언어 블록이 영향을 받지 않는다."""
    block = self._make("plain", "hello world")
    assert block.language == "plain"
    assert block.code == "hello world"

  def test_other_languages_unaffected(self):
    """mermaid 외 다른 언어 블록도 그대로 동작한다."""
    for lang in ("python", "javascript", "sql"):
      block = self._make(lang, f"# {lang} code")
      assert block.language == lang


# ── 2. Repository 레이어 ──────────────────────────────────────────────────────

class TestMermaidCodeBlockRepository:
  """SQLiteBlockRepository 에서 mermaid 코드 블록 CRUD 를 검증."""

  def test_create_mermaid_code_block(self, repo):
    """code 블록 생성 후 language 를 mermaid 로 변경할 수 있다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "code")
    assert block is not None
    assert block["type"] == "code"
    # 기본값은 plain
    assert block["language"] == "plain"

  def test_update_language_to_mermaid(self, repo):
    """update_block 으로 language 를 mermaid 로 업데이트할 수 있다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "code")
    assert repo.update_block(block["id"], {"language": "mermaid"})
    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].language == "mermaid"

  def test_update_mermaid_code_content(self, repo):
    """mermaid 소스 코드를 저장하고 다시 불러올 수 있다."""
    src = "erDiagram\n  USER ||--o{ ORDER : places\n  ORDER ||--|{ LINE-ITEM : contains"
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "code")
    repo.update_block(block["id"], {"language": "mermaid", "code": src})
    fetched = repo.get_document(doc["id"])
    code_block = fetched.blocks[0]
    assert code_block.language == "mermaid"
    assert code_block.code == src

  def test_mermaid_code_persists_across_reload(self, repo):
    """저장 후 문서를 다시 로드해도 mermaid 코드와 언어가 유지된다."""
    src = "graph TD\n  A --> B\n  B --> C"
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "code")
    repo.update_block(block["id"], {"language": "mermaid", "code": src})
    # 문서 재로드
    reloaded = repo.get_document(doc["id"])
    b = reloaded.blocks[0]
    assert b.language == "mermaid"
    assert b.code == src

  def test_change_code_block_type_from_mermaid_to_text(self, repo):
    """mermaid 코드 블록을 text 블록으로 타입 변경할 수 있다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "code")
    repo.update_block(block["id"], {"language": "mermaid", "code": "graph TD; A-->B"})
    assert repo.change_block_type(block["id"], "text")
    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].type == "text"

  def test_change_type_to_code_mermaid(self, repo):
    """text 블록을 code 블록으로 변경하고 language 를 mermaid 로 설정할 수 있다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "text")
    assert repo.change_block_type(block["id"], "code")
    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].type == "code"
    # 타입 변경 직후에는 기본 언어(plain) 이 설정된다
    assert fetched.blocks[0].language == "plain"
    # 이후 language 를 mermaid 로 업데이트할 수 있다
    assert repo.update_block(fetched.blocks[0].id, {"language": "mermaid"})

  def test_delete_mermaid_code_block(self, repo):
    """mermaid 코드 블록을 삭제할 수 있다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "code")
    repo.update_block(block["id"], {"language": "mermaid"})
    assert repo.delete_block(block["id"])
    fetched = repo.get_document(doc["id"])
    assert len(fetched.blocks) == 0

  def test_multiple_code_blocks_with_mixed_languages(self, repo):
    """mermaid 블록과 일반 코드 블록이 같은 문서에서 공존할 수 있다."""
    doc = repo.create_document()
    mermaid_block = repo.create_block(doc["id"], "code")
    plain_block = repo.create_block(doc["id"], "code")
    repo.update_block(mermaid_block["id"], {"language": "mermaid", "code": "graph LR; A-->B"})
    repo.update_block(plain_block["id"], {"language": "python", "code": "print('hi')"})
    fetched = repo.get_document(doc["id"])
    languages = [b.language for b in fetched.blocks]
    assert "mermaid" in languages
    assert "python" in languages


# ── 3. API 레이어 ─────────────────────────────────────────────────────────────

class TestMermaidCodeBlockAPI:
  """HTTP API 를 통한 mermaid 코드 블록 생성·조회·수정을 검증."""

  def test_create_code_block_via_api(self, client):
    """POST /api/documents/{id}/blocks 로 code 블록을 생성할 수 있다."""
    doc = client.post("/api/documents").json()
    resp = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "code"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "code"
    assert data["language"] == "plain"

  def test_patch_language_to_mermaid(self, client):
    """PATCH /api/blocks/{id} 로 language 를 mermaid 로 변경할 수 있다."""
    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "code"},
    ).json()
    resp = client.patch(f"/api/blocks/{block['id']}", json={"language": "mermaid"})
    assert resp.status_code == 200

  def test_get_document_returns_mermaid_language(self, client):
    """GET /api/documents/{id} 응답에 language=mermaid 가 포함된다."""
    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "code"},
    ).json()
    client.patch(f"/api/blocks/{block['id']}", json={"language": "mermaid"})
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert fetched["blocks"][0]["language"] == "mermaid"

  def test_patch_mermaid_code_content(self, client):
    """PATCH /api/blocks/{id} 로 mermaid 소스 코드를 저장할 수 있다."""
    src = "erDiagram\n  USER ||--o{ ORDER : places"
    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "code"},
    ).json()
    client.patch(f"/api/blocks/{block['id']}", json={"language": "mermaid", "code": src})
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    b = fetched["blocks"][0]
    assert b["language"] == "mermaid"
    assert b["code"] == src

  def test_mermaid_code_survives_roundtrip(self, client):
    """저장한 mermaid 소스가 다시 GET 했을 때 동일한 값으로 반환된다."""
    src = "sequenceDiagram\n  Alice->>Bob: Hello\n  Bob-->>Alice: Hi"
    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "code"},
    ).json()
    client.patch(f"/api/blocks/{block['id']}", json={"language": "mermaid", "code": src})
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert fetched["blocks"][0]["code"] == src

  def test_change_type_to_code_via_api(self, client):
    """PATCH /api/blocks/{id}/type 으로 text → code 타입 변경 후 language 를 mermaid 로 설정할 수 있다."""
    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "text"},
    ).json()
    resp = client.patch(f"/api/blocks/{block['id']}/type", json={"type": "code"})
    assert resp.status_code == 200
    resp2 = client.patch(f"/api/blocks/{block['id']}", json={"language": "mermaid"})
    assert resp2.status_code == 200

  def test_patch_mermaid_block_nonexistent_returns_404(self, client):
    """존재하지 않는 블록 ID로 PATCH 시 404 를 반환한다."""
    resp = client.patch("/api/blocks/nonexistent-id", json={"language": "mermaid"})
    assert resp.status_code == 404

  def test_existing_code_block_unaffected_by_mermaid_feature(self, client):
    """기존 code 블록(language=python)이 mermaid 기능 추가 후에도 정상 동작한다."""
    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "code"},
    ).json()
    client.patch(f"/api/blocks/{block['id']}", json={"language": "python", "code": "print('hello')"})
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    b = fetched["blocks"][0]
    assert b["language"] == "python"
    assert b["code"] == "print('hello')"
