// ── URL Embed Block ───────────────────────────────────────────────────────────
//
// 상태 흐름:
//
//   [생성 직후 isNew=true]         [기존 블록 / 타입 변환]
//         ↓                                ↓
//    inputMode (자동 오픈)          placeholder (편집 유도)
//         ↓ Enter                          ↓ "✎ URL 입력" 버튼
//    fetch 요청                      inputMode
//     ├─ success → card               ↓ Enter
//     └─ error   → inputMode + error  fetch 요청
//                     ↓ 재시도         ├─ success → card
//                   fetch 요청         └─ error   → inputMode + error
//
//   [card 상태]
//     호버 → ✎ 버튼 → inputMode

import { apiFetchUrlEmbed } from "../api.js";

export const type = "url_embed";

/**
 * @param {object} block              - 서버에서 받은 블록 데이터
 * @param {{ isNew?: boolean }} opts  - isNew=true 이면 URL 입력창을 즉시 연다
 * @returns {HTMLElement}
 */
export function create(block, { isNew = false } = {}) {
  const template = document.getElementById("url-embed-block-template");
  const node = template.content.firstElementChild.cloneNode(true);

  const inputWrap       = node.querySelector(".url-embed-input-wrap");
  const input           = node.querySelector(".url-embed-input");
  const card            = node.querySelector(".url-embed-card");
  const titleEl         = node.querySelector(".url-embed-title");
  const descEl          = node.querySelector(".url-embed-description");
  const providerEl      = node.querySelector(".url-embed-provider");
  const logoEl          = node.querySelector(".url-embed-logo");
  const editBtn         = node.querySelector(".url-embed-edit-btn");
  const errorWrap       = node.querySelector(".url-embed-error");
  const errorMsg        = node.querySelector(".url-embed-error-msg");
  const retryBtn        = node.querySelector(".url-embed-retry-btn");
  const placeholder     = node.querySelector(".url-embed-placeholder");
  const placeholderEdit = node.querySelector(".url-embed-placeholder-edit-btn");

  // ── 상태 전환 헬퍼 ────────────────────────────────────────────────────────

  /** URL 입력 폼을 표시한다. */
  function showInputMode() {
    input.value        = block.url || "";
    inputWrap.hidden   = false;
    card.hidden        = true;
    placeholder.hidden = true;
    errorWrap.hidden   = true;
    input.focus();
  }

  /** 편집 유도 placeholder를 표시한다 (기존 블록이 URL 없는 경우). */
  function showPlaceholder() {
    placeholder.hidden  = false;
    inputWrap.hidden    = true;
    card.hidden         = true;
    errorWrap.hidden    = true;
  }

  /** 북마크 카드를 표시한다. */
  function showCard() {
    titleEl.textContent    = block.title       || block.url || "제목 없음";
    descEl.textContent     = block.description || "";
    providerEl.textContent = block.provider    || "";
    card.href              = block.url;

    if (block.logo) {
      logoEl.src    = block.logo;
      logoEl.hidden = false;
    } else {
      logoEl.hidden = true;
    }

    descEl.hidden     = !block.description;
    card.hidden       = false;
    inputWrap.hidden  = true;
    placeholder.hidden = true;
    errorWrap.hidden  = true;
  }

  /** 입력창 아래에 에러 메시지를 표시한다. 입력창은 그대로 열려 있다. */
  function showError(msg) {
    errorMsg.textContent  = msg || "메타데이터를 가져올 수 없습니다.";
    errorWrap.hidden      = false;
    inputWrap.hidden      = false;
    card.hidden           = true;
    placeholder.hidden    = true;
  }

  function setLoading(isLoading) {
    input.disabled    = isLoading;
    input.placeholder = isLoading ? "가져오는 중..." : "URL을 붙여넣으세요...";
  }

  // ── 초기 렌더링 ───────────────────────────────────────────────────────────

  if (block.status === "success" && block.url) {
    showCard();
  } else if (isNew) {
    // 생성 직후: 입력창 자동 오픈
    showInputMode();
  } else {
    // 타입 변환 후 리로드 or DB에서 불러온 미입력 블록: 편집 유도 placeholder
    showPlaceholder();
  }

  // ── URL fetch ─────────────────────────────────────────────────────────────

  async function fetchMeta(url) {
    if (!url) return;
    setLoading(true);
    try {
      const meta = await apiFetchUrlEmbed(url, block.id);
      Object.assign(block, meta);
      if (meta.status === "success") {
        showCard();
      } else {
        showError(meta.error);
      }
    } catch (err) {
      showError("서버 오류가 발생했습니다.");
      console.error("URL embed fetch 실패:", err);
    } finally {
      setLoading(false);
    }
  }

  // ── 이벤트 ───────────────────────────────────────────────────────────────

  // 입력 폼 — Enter: fetch / Escape: 이전 상태로 복귀
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const url = input.value.trim();
      if (url) fetchMeta(url);
    }
    if (e.key === "Escape") {
      // 이미 성공 상태가 있으면 카드로, 없으면 placeholder로
      if (block.status === "success" && block.url) showCard();
      else showPlaceholder();
    }
  });

  // 카드 편집 버튼 → 입력 폼으로 전환
  editBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    showInputMode();
  });

  // placeholder 편집 버튼 → 입력 폼으로 전환
  placeholderEdit.addEventListener("click", () => showInputMode());

  // 에러 상태 재시도 — 현재 입력창 값을 우선 사용
  retryBtn.addEventListener("click", () => {
    const url = input.value.trim() || block.url;
    if (url) fetchMeta(url);
  });

  // 로고 로드 실패 시 숨김
  logoEl.addEventListener("error", () => { logoEl.hidden = true; });

  return node;
}
