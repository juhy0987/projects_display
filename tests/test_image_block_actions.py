"""이미지 블록 액션 UI 관련 단위 테스트 (이슈 #59).

커버리지 범위:
  1. Repository 레이어 — image 블록 생성·URL 수정·caption 수정·삭제
  2. API 레이어        — PATCH url/caption, DELETE, 잘못된 ID 처리
  3. process_image 서비스 — 압축·썸네일 생성·WebP 변환 검증
"""
from __future__ import annotations

import io

import pytest


# ── 1. Repository 레이어 ──────────────────────────────────────────────────────

class TestImageBlockRepository:
  """SQLiteBlockRepository에서 image 블록의 CRUD를 검증."""

  def test_create_image_block(self, repo):
    """image 블록 생성 시 기본 필드가 올바르게 초기화된다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "image")

    assert block is not None
    assert block["type"] == "image"
    assert block["url"] == ""
    assert block["caption"] == ""

  def test_create_image_block_returns_required_fields(self, repo):
    """image 블록에 url·caption 필드가 반드시 포함된다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "image")

    for field in ("id", "type", "url", "caption"):
      assert field in block, f"필드 누락: {field}"

  def test_update_image_url(self, repo):
    """url 필드 수정이 정상적으로 반영된다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "image")

    new_url = "https://example.com/photo.jpg"
    assert repo.update_block(block["id"], {"url": new_url})

    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].url == new_url

  def test_update_image_caption(self, repo):
    """caption 필드 수정이 정상적으로 반영된다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "image")

    assert repo.update_block(block["id"], {"caption": "고양이 사진"})

    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].caption == "고양이 사진"

  def test_update_url_and_caption_together(self, repo):
    """url과 caption을 동시에 수정해도 모두 반영된다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "image")

    repo.update_block(block["id"], {
      "url": "https://example.com/img.webp",
      "caption": "예시 이미지",
    })

    fetched = repo.get_document(doc["id"])
    img = fetched.blocks[0]
    assert img.url == "https://example.com/img.webp"
    assert img.caption == "예시 이미지"

  def test_update_nonexistent_block_returns_false(self, repo):
    """존재하지 않는 블록 수정 시 False를 반환한다."""
    result = repo.update_block("does-not-exist", {"url": "https://example.com/a.jpg"})
    assert result is False

  def test_delete_image_block(self, repo):
    """image 블록 삭제 후 문서에서 블록이 사라진다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "image")

    assert repo.delete_block(block["id"])

    fetched = repo.get_document(doc["id"])
    assert len(fetched.blocks) == 0

  def test_delete_nonexistent_block_returns_false(self, repo):
    """존재하지 않는 블록 삭제 시 False를 반환한다."""
    assert repo.delete_block("does-not-exist") is False

  def test_image_persists_across_document_reload(self, repo):
    """저장 후 문서를 다시 불러와도 url·caption이 유지된다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "image")
    repo.update_block(block["id"], {
      "url": "https://example.com/persist.png",
      "caption": "유지 테스트",
    })

    refetched = repo.get_document(doc["id"])
    img = refetched.blocks[0]
    assert img.url == "https://example.com/persist.png"
    assert img.caption == "유지 테스트"

  def test_change_type_to_image(self, repo):
    """다른 타입 블록을 image로 변환하면 url·caption이 기본값으로 초기화된다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "text")

    assert repo.change_block_type(block["id"], "image")

    fetched = repo.get_document(doc["id"])
    img = fetched.blocks[0]
    assert img.type == "image"
    assert img.url == ""
    assert img.caption == ""

  def test_change_type_from_image_to_text(self, repo):
    """image 블록을 text로 변환할 수 있다."""
    doc = repo.create_document()
    block = repo.create_block(doc["id"], "image")

    assert repo.change_block_type(block["id"], "text")

    fetched = repo.get_document(doc["id"])
    assert fetched.blocks[0].type == "text"


# ── 2. API 레이어 ─────────────────────────────────────────────────────────────

class TestImageBlockAPI:
  """HTTP API를 통한 image 블록 생성·조회·수정·삭제를 검증."""

  def _create_image_block(self, client) -> tuple[dict, dict]:
    """테스트용 문서와 image 블록을 생성해 반환하는 헬퍼."""
    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "image"},
    ).json()
    return doc, block

  def test_create_image_block_returns_201(self, client):
    """image 블록 생성 요청은 201을 반환한다."""
    doc = client.post("/api/documents").json()
    resp = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "image"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "image"

  def test_get_document_includes_image_block(self, client):
    """생성된 image 블록이 문서 조회 결과에 포함된다."""
    doc, _ = self._create_image_block(client)
    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert fetched["blocks"][0]["type"] == "image"

  def test_patch_image_url(self, client):
    """PATCH /api/blocks/{id} 로 url 수정이 200을 반환한다."""
    _, block = self._create_image_block(client)
    resp = client.patch(
      f"/api/blocks/{block['id']}",
      json={"url": "https://example.com/new.jpg"},
    )
    assert resp.status_code == 200

  def test_patch_image_caption(self, client):
    """PATCH /api/blocks/{id} 로 caption 수정이 200을 반환한다."""
    _, block = self._create_image_block(client)
    resp = client.patch(
      f"/api/blocks/{block['id']}",
      json={"caption": "수정된 캡션"},
    )
    assert resp.status_code == 200

  def test_patch_url_reflected_in_document(self, client):
    """url 수정 후 문서 재조회 시 변경 값이 반영된다."""
    doc, block = self._create_image_block(client)
    new_url = "https://example.com/updated.webp"

    client.patch(f"/api/blocks/{block['id']}", json={"url": new_url})

    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert fetched["blocks"][0]["url"] == new_url

  def test_patch_caption_reflected_in_document(self, client):
    """caption 수정 후 문서 재조회 시 변경 값이 반영된다."""
    doc, block = self._create_image_block(client)

    client.patch(f"/api/blocks/{block['id']}", json={"caption": "갱신된 캡션"})

    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert fetched["blocks"][0]["caption"] == "갱신된 캡션"

  def test_patch_nonexistent_block_returns_404(self, client):
    """존재하지 않는 블록 수정 시 404를 반환한다."""
    resp = client.patch(
      "/api/blocks/nonexistent-id",
      json={"url": "https://example.com/x.jpg"},
    )
    assert resp.status_code == 404

  def test_patch_no_fields_returns_422(self, client):
    """수정 필드가 없는 PATCH 요청은 422를 반환한다."""
    _, block = self._create_image_block(client)
    resp = client.patch(f"/api/blocks/{block['id']}", json={})
    assert resp.status_code == 422

  def test_delete_image_block_returns_204(self, client):
    """DELETE /api/blocks/{id} 는 204를 반환한다."""
    _, block = self._create_image_block(client)
    resp = client.delete(f"/api/blocks/{block['id']}")
    assert resp.status_code == 204

  def test_delete_removes_block_from_document(self, client):
    """블록 삭제 후 문서 재조회 시 블록이 목록에서 사라진다."""
    doc, block = self._create_image_block(client)

    client.delete(f"/api/blocks/{block['id']}")

    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert len(fetched["blocks"]) == 0

  def test_delete_nonexistent_block_returns_404(self, client):
    """존재하지 않는 블록 삭제 시 404를 반환한다."""
    resp = client.delete("/api/blocks/nonexistent-id")
    assert resp.status_code == 404

  def test_change_type_to_image_via_api(self, client):
    """PATCH /api/blocks/{id}/type 으로 image 타입 전환이 200을 반환한다."""
    doc = client.post("/api/documents").json()
    block = client.post(
      f"/api/documents/{doc['id']}/blocks",
      json={"type": "text"},
    ).json()

    resp = client.patch(f"/api/blocks/{block['id']}/type", json={"type": "image"})
    assert resp.status_code == 200

    fetched = client.get(f"/api/documents/{doc['id']}").json()
    assert fetched["blocks"][0]["type"] == "image"


# ── 3. process_image 서비스 ───────────────────────────────────────────────────

class TestProcessImageService:
  """app.services.image.process_image 의 압축·썸네일·형식 변환을 검증."""

  def _make_png_bytes(self, width: int = 100, height: int = 80) -> bytes:
    """PIL로 단색 PNG 이미지를 생성해 bytes로 반환하는 헬퍼."""
    from PIL import Image as PilImage
    img = PilImage.new("RGB", (width, height), color=(120, 200, 150))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

  def test_returns_url_and_thumbnail_url(self, tmp_path, monkeypatch):
    """process_image가 url과 thumbnail_url 두 키를 반환한다."""
    from app.services import image as img_svc

    monkeypatch.setattr(img_svc, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(img_svc, "THUMBNAILS_DIR", tmp_path / "thumbnails")

    result = img_svc.process_image(self._make_png_bytes())

    assert "url" in result
    assert "thumbnail_url" in result

  def test_output_is_webp(self, tmp_path, monkeypatch):
    """압축된 원본 이미지는 WebP 형식으로 저장된다."""
    from PIL import Image as PilImage
    from app.services import image as img_svc

    monkeypatch.setattr(img_svc, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(img_svc, "THUMBNAILS_DIR", tmp_path / "thumbnails")

    result = img_svc.process_image(self._make_png_bytes())
    # url 경로: /static/uploads/<name>.webp
    assert result["url"].endswith(".webp")

  def test_thumbnail_is_webp(self, tmp_path, monkeypatch):
    """썸네일 이미지도 WebP 형식으로 저장된다."""
    from app.services import image as img_svc

    monkeypatch.setattr(img_svc, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(img_svc, "THUMBNAILS_DIR", tmp_path / "thumbnails")

    result = img_svc.process_image(self._make_png_bytes())
    assert result["thumbnail_url"].endswith(".webp")

  def test_large_image_downscaled(self, tmp_path, monkeypatch):
    """MAX_DIMENSION을 초과하는 이미지는 지정 크기 이내로 축소된다."""
    from PIL import Image as PilImage
    from app.services import image as img_svc

    monkeypatch.setattr(img_svc, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(img_svc, "THUMBNAILS_DIR", tmp_path / "thumbnails")

    # MAX_DIMENSION(1920)보다 큰 이미지 생성
    big_png = self._make_png_bytes(width=3000, height=2000)
    result = img_svc.process_image(big_png)

    # 저장된 파일을 열어 실제 크기 확인
    saved_name = result["url"].split("/")[-1]
    saved_path = tmp_path / saved_name
    with PilImage.open(saved_path) as saved:
      assert max(saved.size) <= img_svc.MAX_DIMENSION

  def test_small_image_not_upscaled(self, tmp_path, monkeypatch):
    """MAX_DIMENSION보다 작은 이미지는 확대되지 않는다."""
    from PIL import Image as PilImage
    from app.services import image as img_svc

    monkeypatch.setattr(img_svc, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(img_svc, "THUMBNAILS_DIR", tmp_path / "thumbnails")

    small_png = self._make_png_bytes(width=200, height=150)
    result = img_svc.process_image(small_png)

    saved_name = result["url"].split("/")[-1]
    saved_path = tmp_path / saved_name
    with PilImage.open(saved_path) as saved:
      assert saved.size == (200, 150)

  def test_thumbnail_fits_within_thumbnail_size(self, tmp_path, monkeypatch):
    """썸네일은 THUMBNAIL_SIZE 이내 크기로 생성된다."""
    from PIL import Image as PilImage
    from app.services import image as img_svc

    monkeypatch.setattr(img_svc, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(img_svc, "THUMBNAILS_DIR", tmp_path / "thumbnails")

    big_png = self._make_png_bytes(width=1000, height=800)
    result = img_svc.process_image(big_png)

    thumb_name = result["thumbnail_url"].split("/")[-1]
    thumb_path = tmp_path / "thumbnails" / thumb_name
    with PilImage.open(thumb_path) as thumb:
      max_side = max(thumb.size)
      assert max_side <= max(img_svc.THUMBNAIL_SIZE)

  def test_rgba_image_processed_without_error(self, tmp_path, monkeypatch):
    """RGBA (투명도 있는) 이미지도 오류 없이 처리된다."""
    from PIL import Image as PilImage
    from app.services import image as img_svc

    monkeypatch.setattr(img_svc, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(img_svc, "THUMBNAILS_DIR", tmp_path / "thumbnails")

    img = PilImage.new("RGBA", (100, 100), color=(255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    result = img_svc.process_image(buf.getvalue())
    assert "url" in result

  def test_url_path_has_correct_prefix(self, tmp_path, monkeypatch):
    """반환된 url은 /static/uploads/ 로 시작한다."""
    from app.services import image as img_svc

    monkeypatch.setattr(img_svc, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(img_svc, "THUMBNAILS_DIR", tmp_path / "thumbnails")

    result = img_svc.process_image(self._make_png_bytes())
    assert result["url"].startswith("/static/uploads/")

  def test_thumbnail_url_path_has_correct_prefix(self, tmp_path, monkeypatch):
    """반환된 thumbnail_url은 /static/uploads/thumbnails/ 로 시작한다."""
    from app.services import image as img_svc

    monkeypatch.setattr(img_svc, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(img_svc, "THUMBNAILS_DIR", tmp_path / "thumbnails")

    result = img_svc.process_image(self._make_png_bytes())
    assert result["thumbnail_url"].startswith("/static/uploads/thumbnails/")

  def test_each_call_generates_unique_filename(self, tmp_path, monkeypatch):
    """두 번 호출하면 서로 다른 파일 이름이 생성된다."""
    from app.services import image as img_svc

    monkeypatch.setattr(img_svc, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(img_svc, "THUMBNAILS_DIR", tmp_path / "thumbnails")

    r1 = img_svc.process_image(self._make_png_bytes())
    r2 = img_svc.process_image(self._make_png_bytes())
    assert r1["url"] != r2["url"]
