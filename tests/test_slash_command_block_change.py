"""슬래시 커맨드 기반 블록 타입 전환 단위 테스트 (Issue #39).

인라인 슬래시 커맨드 메뉴에서 블록 타입을 전환할 때 백엔드에서 수행되는
change_block_type / patch_block 로직을 repository 레이어와 API 레이어 양쪽에서
검증한다.

테스트 범위:
  - 슬래시 커맨드가 지원하는 모든 전환 대상 타입 (SLASH_MENU_ITEMS 와 동기화)
  - 전환 후 콘텐츠 초기화 및 기본값 확인
  - heading level 변환 (text 타입 내부 level PATCH)
  - 지원하지 않는 타입으로의 전환 거부 (page / database / db_row)
  - 컨테이너 → 단순 타입 전환 시 자식 블록 삭제
  - 단순 타입 → 컨테이너 전환 시 자식 auto-생성
  - API 레이어: 허용/거부 응답 코드 검증
  - API 레이어: 전환 후 GET 문서에서 타입 반영 확인

참고:
  - Notion slash command UX: https://www.notion.so/help/guides
  - BlockTypeChange 리터럴 허용 타입: app/routers/blocks.py
  - change_block_type 구현: app/repositories/sqlite_blocks.py
"""
from __future__ import annotations

import pytest


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _create_doc(repo):
  """빈 문서를 하나 생성하고 반환한다."""
  return repo.create_document()


def _create_doc_and_block(repo, block_type="text"):
  """문서와 지정 타입 블록을 하나 생성해 (doc_dict, block_dict) 튜플로 반환한다.

  create_document() → {"id": ..., "title": ..., ...}
  create_block()    → {"id": ..., "type": ..., ...}  (document_id 미포함)
  """
  doc = _create_doc(repo)
  block = repo.create_block(doc["id"], block_type)
  return doc, block


# ── Repository 레이어 테스트 ──────────────────────────────────────────────────

class TestSlashMenuSupportedTypes:
  """슬래시 커맨드 메뉴가 노출하는 모든 전환 타입이 성공적으로 변환된다.

  SLASH_MENU_ITEMS (inlineSlashMenu.js) 와 일치하는 타입 목록:
    text, toggle, quote, code, callout, image, divider, url_embed
  """

  @pytest.mark.parametrize("target_type", [
    "text",
    "toggle",
    "quote",
    "code",
    "callout",
    "image",
    "divider",
    "url_embed",
  ])
  def test_change_from_text_to_supported_type(self, repo, target_type):
    """text 블록에서 슬래시 커맨드 지원 타입으로 전환이 성공한다."""
    doc, block = _create_doc_and_block(repo, "text")
    result = repo.change_block_type(block["id"], target_type)
    assert result is True

    fetched = repo.get_document(doc["id"])
    top_block = fetched.blocks[0]
    assert top_block.type == target_type

  @pytest.mark.parametrize("source_type,target_type", [
    ("toggle",  "text"),
    ("quote",   "text"),
    ("callout", "code"),
    ("code",    "toggle"),
    ("image",   "callout"),
    ("url_embed", "divider"),
  ])
  def test_cross_type_conversion(self, repo, source_type, target_type):
    """컨테이너·단순 블록 간 교차 전환이 모두 성공한다."""
    doc, block = _create_doc_and_block(repo, source_type)
    assert repo.change_block_type(block["id"], target_type)
    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].type == target_type


class TestDefaultValuesAfterConversion:
  """전환 후 각 타입의 기본값이 올바르게 초기화된다.

  change_block_type 은 content_json 을 새 타입의 기본값으로 리셋한다.
  (기존 내용을 보존하지 않음 — 슬래시 커맨드 전환 의도와 일치)
  """

  def test_to_text_resets_text_and_level(self, repo):
    """text 로 전환하면 text 필드가 빈 문자열로 초기화된다."""
    doc, block = _create_doc_and_block(repo, "code")
    repo.update_block(block["id"], {"code": "print('hi')", "language": "python"})
    repo.change_block_type(block["id"], "text")
    fetched = repo.get_document(doc["id"])
    text_block = fetched.blocks[0]
    assert text_block.type == "text"
    assert text_block.text == ""

  def test_to_code_resets_code_and_language(self, repo):
    """code 로 전환하면 code·language 가 기본값으로 초기화된다."""
    doc, block = _create_doc_and_block(repo, "text")
    repo.change_block_type(block["id"], "code")
    fetched = repo.get_document(doc["id"])
    code = fetched.blocks[0]
    assert code.code == ""
    assert code.language == "plain"

  def test_to_callout_resets_emoji_and_color(self, repo):
    """callout 로 전환하면 emoji·color 가 기본값으로 초기화된다."""
    doc, block = _create_doc_and_block(repo, "text")
    repo.change_block_type(block["id"], "callout")
    fetched = repo.get_document(doc["id"])
    callout = fetched.blocks[0]
    assert callout.emoji == "💡"
    assert callout.color == "yellow"

  def test_to_url_embed_resets_status_to_pending(self, repo):
    """url_embed 로 전환하면 status 가 'pending' 으로 초기화된다."""
    doc, block = _create_doc_and_block(repo, "text")
    repo.change_block_type(block["id"], "url_embed")
    fetched = repo.get_document(doc["id"])
    embed = fetched.blocks[0]
    assert embed.status == "pending"
    assert embed.url == ""

  def test_to_image_resets_url_and_caption(self, repo):
    """image 로 전환하면 url·caption 이 빈 문자열로 초기화된다."""
    doc, block = _create_doc_and_block(repo, "text")
    repo.change_block_type(block["id"], "image")
    fetched = repo.get_document(doc["id"])
    image = fetched.blocks[0]
    assert image.url == ""
    assert image.caption == ""

  def test_to_divider_has_no_content_fields(self, repo):
    """divider 로 전환하면 내용 없이 type 만 변경된다."""
    doc, block = _create_doc_and_block(repo, "text")
    repo.change_block_type(block["id"], "divider")
    fetched = repo.get_document(doc["id"])
    divider = fetched.blocks[0]
    assert divider.type == "divider"


class TestHeadingLevelConversion:
  """슬래시 커맨드 H1~H3 전환: text 타입 + level PATCH 조합.

  인라인 슬래시 메뉴에서 heading 아이템 선택 시의 흐름:
    1. 이미 text 타입 → change_block_type 생략, level PATCH 만 수행
    2. 다른 타입   → change_block_type("text") 후 level PATCH

  이 테스트는 각 단계를 개별적으로 검증한다.
  """

  @pytest.mark.parametrize("level", [1, 2, 3])
  def test_patch_level_on_text_block(self, repo, level):
    """text 블록의 level PATCH 가 올바르게 저장된다."""
    doc, block = _create_doc_and_block(repo, "text")
    repo.update_block(block["id"], {"level": level, "text": "", "formatted_text": ""})
    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].level == level

  @pytest.mark.parametrize("source_type", ["code", "toggle", "quote", "callout"])
  def test_change_to_text_then_patch_level(self, repo, source_type):
    """비-text 블록에서 text 로 전환한 뒤 level PATCH 를 적용할 수 있다."""
    doc, block = _create_doc_and_block(repo, source_type)
    # Step 1: type 전환
    assert repo.change_block_type(block["id"], "text")
    # Step 2: heading level 설정
    assert repo.update_block(block["id"], {"level": 1, "text": "", "formatted_text": ""})
    fetched = repo.get_document(doc["id"])
    top = fetched.blocks[0]
    assert top.type == "text"
    assert top.level == 1

  def test_heading_level_is_cleared_when_converting_away(self, repo):
    """heading 블록을 다른 타입으로 전환하면 level 정보가 content_json 에 남지 않는다."""
    doc, block = _create_doc_and_block(repo, "text")
    repo.update_block(block["id"], {"level": 2})
    repo.change_block_type(block["id"], "code")
    fetched = repo.get_document(doc["id"])
    code = fetched.blocks[0]
    assert code.type == "code"
    # CodeBlock 에는 level 속성 자체가 없어야 한다.
    assert not hasattr(code, "level")


class TestUnsupportedTypeConversion:
  """슬래시 커맨드에서 허용되지 않는 타입으로의 전환이 거부된다.

  page·database·db_row 는 별도 생성 흐름이 필요하며
  PATCH /api/blocks/{id}/type 에서 허용하지 않는다.
  (BlockTypeChange 리터럴 타입에 포함되지 않음)
  """

  @pytest.mark.parametrize("blocked_type", ["page", "database", "db_row"])
  def test_change_to_blocked_type_returns_false(self, repo, blocked_type):
    """page / database / db_row 로의 전환 시도는 False 를 반환한다."""
    _, block = _create_doc_and_block(repo, "text")
    result = repo.change_block_type(block["id"], blocked_type)
    assert result is False

  def test_change_to_unknown_type_returns_false(self, repo):
    """완전히 알 수 없는 타입으로의 전환도 False 를 반환한다."""
    _, block = _create_doc_and_block(repo, "text")
    assert repo.change_block_type(block["id"], "nonexistent_type") is False

  def test_block_unchanged_after_rejected_conversion(self, repo):
    """거부된 전환 후에도 블록 타입이 원래 값을 유지한다."""
    doc, block = _create_doc_and_block(repo, "text")
    repo.change_block_type(block["id"], "page")
    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].type == "text"


class TestContainerChildHandling:
  """컨테이너 블록 전환 시 자식 블록 정리 및 auto-생성 규칙 검증."""

  def test_converting_from_container_deletes_all_children(self, repo):
    """toggle → text 전환 시 toggle 의 자식 블록이 모두 삭제된다."""
    doc = _create_doc(repo)
    parent = repo.create_block(doc["id"], "toggle")
    # auto-child 1개 포함 상태에서 추가 자식 2개 생성
    repo.create_block(doc["id"], "text", parent_block_id=parent["id"])
    repo.create_block(doc["id"], "code", parent_block_id=parent["id"])

    repo.change_block_type(parent["id"], "text")
    fetched = repo.get_document(doc["id"])
    assert len(fetched.blocks) == 1
    assert fetched.blocks[0].type == "text"

  def test_converting_to_container_auto_creates_one_child(self, repo):
    """text → toggle 전환 시 자식 텍스트 블록이 1개 자동 생성된다."""
    doc, block = _create_doc_and_block(repo, "text")
    repo.change_block_type(block["id"], "toggle")
    fetched = repo.get_document(doc["id"])
    toggle = fetched.blocks[0]
    assert toggle.type == "toggle"
    assert len(toggle.children) == 1
    assert toggle.children[0].type == "text"

  @pytest.mark.parametrize("container_type", ["toggle", "quote", "callout"])
  def test_all_container_types_auto_create_child_on_conversion(self, repo, container_type):
    """toggle·quote·callout 모두 전환 후 자식 텍스트 블록 1개를 auto-생성한다."""
    doc, block = _create_doc_and_block(repo, "text")
    repo.change_block_type(block["id"], container_type)
    fetched = repo.get_document(doc["id"])
    container = fetched.blocks[0]
    assert container.type == container_type
    assert len(container.children) == 1


class TestNonExistentBlock:
  """존재하지 않는 블록 ID 로 전환 시도 시 False 를 반환한다."""

  def test_change_type_of_nonexistent_block(self, repo):
    assert repo.change_block_type("does-not-exist", "text") is False


# ── API 레이어 테스트 ─────────────────────────────────────────────────────────

class TestSlashCommandAPI:
  """HTTP PATCH /api/blocks/{id}/type 엔드포인트 동작 검증.

  슬래시 커맨드는 프론트엔드에서 이 엔드포인트를 호출한다.
  """

  def _setup(self, client, block_type="text"):
    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": block_type},
    ).json()
    return doc, block

  # ── 정상 전환 ────────────────────────────────────────────────────────────

  @pytest.mark.parametrize("target_type", [
    "text", "toggle", "quote", "code", "callout", "image", "divider", "url_embed",
  ])
  def test_supported_type_returns_200(self, client, target_type):
    """슬래시 커맨드 지원 타입으로의 전환은 HTTP 200 을 반환한다."""
    _, block = self._setup(client)
    resp = client.patch(f"/api/blocks/{block['id']}/type", json={"type": target_type})
    assert resp.status_code == 200

  def test_response_body_contains_block_id(self, client):
    """전환 성공 응답 본문에 블록 id 가 포함된다."""
    _, block = self._setup(client)
    resp = client.patch(f"/api/blocks/{block['id']}/type", json={"type": "toggle"})
    assert resp.json()["id"] == block["id"]

  def test_get_document_reflects_new_type(self, client):
    """전환 후 GET /api/documents/{id} 에서 변경된 타입이 반환된다."""
    doc, block = self._setup(client)
    client.patch(f"/api/blocks/{block['id']}/type", json={"type": "code"})
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert fetched["blocks"][0]["type"] == "code"

  # ── heading level PATCH (슬래시 커맨드 H1~H3 흐름의 두 번째 단계) ─────────

  @pytest.mark.parametrize("level", [1, 2, 3])
  def test_patch_heading_level_returns_200(self, client, level):
    """text 블록에 heading level PATCH 가 성공한다."""
    _, block = self._setup(client, "text")
    resp = client.patch(
      f"/api/blocks/{block['id']}",
      json={"level": level, "text": "", "formatted_text": ""},
    )
    assert resp.status_code == 200

  def test_heading_level_persisted_after_patch(self, client):
    """level PATCH 후 GET 문서에서 heading level 이 반영된다."""
    doc, block = self._setup(client, "text")
    client.patch(f"/api/blocks/{block['id']}", json={"level": 2})
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert fetched["blocks"][0]["level"] == 2

  # ── 허용하지 않는 타입 거부 ───────────────────────────────────────────────

  @pytest.mark.parametrize("blocked_type", ["page", "database", "db_row"])
  def test_blocked_types_return_422(self, client, blocked_type):
    """page / database / db_row 로의 전환 요청은 HTTP 422 를 반환한다.

    BlockTypeChange 리터럴에 포함되지 않으므로 Pydantic 검증에서 거부된다.
    """
    _, block = self._setup(client)
    resp = client.patch(f"/api/blocks/{block['id']}/type", json={"type": blocked_type})
    assert resp.status_code == 422

  def test_unknown_type_returns_422(self, client):
    """알 수 없는 타입 문자열은 HTTP 422 를 반환한다."""
    _, block = self._setup(client)
    resp = client.patch(f"/api/blocks/{block['id']}/type", json={"type": "banana"})
    assert resp.status_code == 422

  def test_nonexistent_block_returns_404(self, client):
    """존재하지 않는 블록 ID 로의 전환 요청은 HTTP 404 를 반환한다."""
    resp = client.patch("/api/blocks/no-such-id/type", json={"type": "text"})
    assert resp.status_code == 404

  # ── 복합 시나리오 ─────────────────────────────────────────────────────────

  def test_toggle_to_text_then_verify_no_children(self, client):
    """슬래시 커맨드로 toggle → text 전환 후 문서에 자식 블록이 남지 않는다."""
    doc, block = self._setup(client, "toggle")
    # toggle 생성 시 auto-child 1개 포함
    client.patch(f"/api/blocks/{block['id']}/type", json={"type": "text"})
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert len(fetched["blocks"]) == 1
    text_block = fetched["blocks"][0]
    assert text_block["type"] == "text"
    assert "children" not in text_block or text_block.get("children") == []

  def test_text_to_callout_auto_creates_child(self, client):
    """슬래시 커맨드로 text → callout 전환 후 자식 텍스트 블록이 자동 생성된다."""
    doc, block = self._setup(client, "text")
    client.patch(f"/api/blocks/{block['id']}/type", json={"type": "callout"})
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    callout = fetched["blocks"][0]
    assert callout["type"] == "callout"
    assert len(callout["children"]) == 1
    assert callout["children"][0]["type"] == "text"

  def test_multiple_conversions_in_sequence(self, client):
    """동일 블록에 대해 여러 번 연속 전환이 각각 성공한다 (슬래시 커맨드 재실행)."""
    _, block = self._setup(client, "text")
    block_id = block["id"]

    for target in ["code", "quote", "image", "text"]:
      resp = client.patch(f"/api/blocks/{block_id}/type", json={"type": target})
      assert resp.status_code == 200
