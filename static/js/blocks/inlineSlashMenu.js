// ── Inline Slash Command Menu ─────────────────────────────────────────────────
//
// 텍스트 블록에서 '/' 입력 시 포커스를 유지한 상태로 인라인 드롭다운을 노출한다.
// 기본적으로 앵커 요소 위쪽(top)에 표시하며, 상단 공간이 부족하면 아래로 fallback한다.
//
// 참고: Notion slash command UX — https://www.notion.so/help/guides
// ARIA 패턴: WAI-ARIA 1.2 Listbox Pattern — https://www.w3.org/WAI/ARIA/apg/patterns/listbox/

import { apiChangeBlockType, apiPatchBlock } from "../api.js";

// ── 슬래시 메뉴 아이템 정의 ───────────────────────────────────────────────────
//
// type: API 타입 문자열 (BlockTypeChange.type 허용 목록 기반)
// label: 드롭다운에 표시할 한국어 레이블
// icon: 단순 텍스트/이모지 아이콘
// keywords: 영어 필터링 키워드 (사용자가 영문으로 검색할 때 매핑)
// level: text 블록의 heading 레벨 (1~3, text 타입 전용 옵션)
//
// 제한: page·database·db_row 는 별도 생성 흐름이 필요하므로 제외
// (PATCH /api/blocks/{id}/type 에서도 허용하지 않음 — BlockTypeChange 리터럴 참고)

/** @type {Array<{type:string, label:string, icon:string, keywords:string[], level?:number}>} */
export const SLASH_MENU_ITEMS = [
  { type: "text",      label: "텍스트",      icon: "T",   keywords: ["text", "paragraph", "plain", "텍스트"] },
  { type: "text",      label: "제목 1",      icon: "H1",  keywords: ["h1", "heading1", "제목1", "heading"], level: 1 },
  { type: "text",      label: "제목 2",      icon: "H2",  keywords: ["h2", "heading2", "제목2"],            level: 2 },
  { type: "text",      label: "제목 3",      icon: "H3",  keywords: ["h3", "heading3", "제목3"],            level: 3 },
  { type: "toggle",    label: "토글",        icon: "▶",   keywords: ["toggle", "collapsible", "토글"] },
  { type: "quote",     label: "인용",        icon: "\"",  keywords: ["quote", "blockquote", "인용"] },
  { type: "code",      label: "코드",        icon: "⟨⟩",  keywords: ["code", "snippet", "pre", "코드"] },
  { type: "callout",   label: "콜아웃",      icon: "💡",  keywords: ["callout", "note", "tip", "콜아웃"] },
  { type: "image",     label: "이미지",      icon: "▣",   keywords: ["image", "photo", "picture", "이미지"] },
  { type: "divider",   label: "구분선",      icon: "—",   keywords: ["divider", "separator", "hr", "rule", "구분선"] },
  { type: "url_embed", label: "URL 임베드", icon: "🔗",   keywords: ["url", "link", "embed", "bookmark", "임베드"] },
];

// ── 필터링 ────────────────────────────────────────────────────────────────────

/**
 * query 문자열로 슬래시 메뉴 아이템을 필터링한다.
 * 대소문자·완전일치 구분 없이 label 또는 keywords에 포함되면 통과.
 *
 * @param {string} query
 * @returns {typeof SLASH_MENU_ITEMS}
 */
export function filterSlashItems(query) {
  if (!query) return SLASH_MENU_ITEMS;
  const q = query.toLowerCase();
  return SLASH_MENU_ITEMS.filter(
    (item) =>
      item.label.toLowerCase().includes(q) ||
      item.keywords.some((k) => k.includes(q)),
  );
}

// ── 드롭다운 배치 ─────────────────────────────────────────────────────────────

const MENU_ESTIMATED_HEIGHT = 300; // px — 정확한 높이를 DOM 삽입 전에 추정하는 값

/**
 * 메뉴 요소를 앵커 요소 기준으로 viewport 안에 배치한다.
 * 기본 방향: 위쪽. 상단 공간이 부족하면 아래쪽으로 fallback.
 *
 * @param {HTMLElement} menuEl
 * @param {HTMLElement} anchorEl - 텍스트 블록의 contentEditable 요소
 */
function positionMenu(menuEl, anchorEl) {
  // block-wrapper 전체 영역을 앵커 기준으로 삼는다.
  const wrapperEl = anchorEl.closest(".block-wrapper") ?? anchorEl;
  const rect = wrapperEl.getBoundingClientRect();

  const spaceAbove = rect.top;
  const spaceBelow = window.innerHeight - rect.bottom;

  // position: fixed 로 viewport 좌표 직접 지정
  menuEl.style.position = "fixed";
  menuEl.style.left = `${rect.left}px`;
  menuEl.style.minWidth = `${rect.width}px`;
  menuEl.style.maxWidth = "320px";
  menuEl.style.zIndex = "9999";

  if (spaceAbove >= MENU_ESTIMATED_HEIGHT || spaceAbove >= spaceBelow) {
    // 위쪽에 충분한 공간이 있거나, 위쪽이 더 넓음 → 위쪽 표시
    menuEl.style.bottom = `${window.innerHeight - rect.top + 4}px`;
    menuEl.style.top = "auto";
    menuEl.dataset.direction = "up";
  } else {
    // 아래쪽 fallback
    menuEl.style.top = `${rect.bottom + 4}px`;
    menuEl.style.bottom = "auto";
    menuEl.dataset.direction = "down";
  }
}

// ── 핵심 공개 API ─────────────────────────────────────────────────────────────

/**
 * 인라인 슬래시 커맨드 메뉴를 연다.
 * 메뉴가 이미 열려 있으면 기존 것을 닫고 새로 연다.
 *
 * @param {HTMLElement} anchorEl   - 포커스를 유지해야 하는 contentEditable 요소
 * @param {string}      blockId    - 대상 블록 ID
 * @param {string}      currentBlockType - 현재 블록 타입 (heading level 분기에 사용)
 * @param {object}      opts
 * @param {Function}   [opts.reloadDocument] - 블록 전환 완료 후 문서 재렌더링 콜백
 *
 * @returns {{ updateQuery: (q:string)=>void, close: ()=>void }}
 *   열린 메뉴의 제어 핸들을 반환한다 (textEditing.js 에서 query 업데이트에 사용).
 */
export function openInlineSlashMenu(anchorEl, blockId, currentBlockType, { reloadDocument = null } = {}) {
  // 기존 메뉴 제거 (중복 방지)
  closeAllInlineSlashMenus();

  let filteredItems = SLASH_MENU_ITEMS;
  let highlightedIdx = 0;

  // ── DOM 생성 ───────────────────────────────────────────────────────────────

  const menuEl = document.createElement("div");
  menuEl.className = "inline-slash-menu";
  // ARIA listbox 역할: 키보드-only 사용자가 옵션 목록임을 인식할 수 있도록 한다.
  // 참고: WAI-ARIA 1.2 §6.12 listbox — https://www.w3.org/TR/wai-aria-1.2/#listbox
  menuEl.setAttribute("role", "listbox");
  menuEl.setAttribute("aria-label", "블록 타입 선택");

  // 빈 상태 메시지 (필터 결과 없을 때 표시)
  const emptyEl = document.createElement("div");
  emptyEl.className = "inline-slash-menu__empty";
  emptyEl.textContent = "일치하는 블록이 없습니다";
  emptyEl.hidden = true;

  document.body.appendChild(menuEl);
  positionMenu(menuEl, anchorEl);

  // ── 렌더링 ────────────────────────────────────────────────────────────────

  function render() {
    menuEl.innerHTML = "";

    if (filteredItems.length === 0) {
      menuEl.appendChild(emptyEl);
      emptyEl.hidden = false;
      return;
    }

    emptyEl.hidden = true;

    // highlightedIdx 가 범위를 벗어나지 않도록 보정
    if (highlightedIdx >= filteredItems.length) highlightedIdx = 0;

    filteredItems.forEach((item, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "inline-slash-menu__item";
      // ARIA option 역할: listbox 내의 선택 가능한 항목
      btn.setAttribute("role", "option");
      btn.setAttribute("aria-selected", String(idx === highlightedIdx));

      const iconEl = document.createElement("span");
      iconEl.className = "inline-slash-menu__icon";
      iconEl.textContent = item.icon;
      iconEl.setAttribute("aria-hidden", "true");

      const labelEl = document.createElement("span");
      labelEl.className = "inline-slash-menu__label";
      labelEl.textContent = item.label;

      btn.appendChild(iconEl);
      btn.appendChild(labelEl);

      if (idx === highlightedIdx) btn.classList.add("is-highlighted");

      // mousedown preventDefault: 클릭해도 anchorEl 포커스를 빼앗지 않는다.
      // (blur → 저장 로직이 실행되지 않도록 막는 핵심 처리)
      btn.addEventListener("mousedown", (e) => e.preventDefault());
      btn.addEventListener("mousemove", () => {
        if (highlightedIdx === idx) return;
        highlightedIdx = idx;
        render();
      });
      btn.addEventListener("click", () => executeItem(item));

      menuEl.appendChild(btn);
    });

    // 선택된 항목이 스크롤 영역 안에 보이도록 스크롤
    const highlighted = menuEl.querySelector(".is-highlighted");
    highlighted?.scrollIntoView({ block: "nearest" });
  }

  render();

  // ── 블록 타입 실행 ────────────────────────────────────────────────────────

  /**
   * 선택된 아이템에 따라 블록 타입을 변환한다.
   *
   * heading(H1~H3) 처리:
   *   - 이미 text 타입이면 level 만 PATCH
   *   - 다른 타입이면 type change → text 로 변환 후 level PATCH
   *
   * 참고: PATCH /api/blocks/{id}/type 은 page·database·db_row 를 허용하지 않음
   * (BlockTypeChange 리터럴 타입 참고 — app/routers/blocks.py)
   */
  async function executeItem(item) {
    close();
    try {
      if (item.level != null) {
        // heading 전환: text 타입 + level 변경
        if (currentBlockType !== "text") {
          await apiChangeBlockType(blockId, "text");
        }
        await apiPatchBlock(blockId, { level: item.level, text: "", formatted_text: "" });
      } else {
        await apiChangeBlockType(blockId, item.type);
      }
    } catch (err) {
      console.error("[InlineSlashMenu] 블록 타입 변환 실패:", err);
    } finally {
      reloadDocument?.();
    }
  }

  // ── 키보드 내비게이션 ─────────────────────────────────────────────────────

  /**
   * anchorEl 에서 발생한 keydown 이벤트를 가로채 메뉴 내비게이션을 처리한다.
   * capture 단계에서 등록해 다른 핸들러보다 먼저 실행된다.
   */
  function onKeydown(e) {
    if (!menuEl.isConnected) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        e.stopImmediatePropagation();
        highlightedIdx = (highlightedIdx + 1) % Math.max(filteredItems.length, 1);
        render();
        break;

      case "ArrowUp":
        e.preventDefault();
        e.stopImmediatePropagation();
        highlightedIdx =
          (highlightedIdx - 1 + Math.max(filteredItems.length, 1)) %
          Math.max(filteredItems.length, 1);
        render();
        break;

      case "Enter":
        // 필터 결과가 있을 때만 Enter 로 확정
        if (filteredItems.length > 0) {
          e.preventDefault();
          e.stopImmediatePropagation();
          executeItem(filteredItems[highlightedIdx]);
        }
        break;

      case "Escape":
        // Esc: 메뉴 닫기. textEditing.js 의 Esc 핸들러로 전파하지 않도록 막는다.
        e.stopImmediatePropagation();
        close();
        break;

      default:
        break;
    }
  }

  anchorEl.addEventListener("keydown", onKeydown, { capture: true });

  // ── 외부 클릭 닫기 ────────────────────────────────────────────────────────

  // setTimeout 0: openInlineSlashMenu 를 트리거한 input 이벤트가 끝난 뒤 등록해
  // 즉시 닫히는 경쟁 조건을 방지한다.
  let removeOutsideListener = () => {};
  setTimeout(() => {
    if (!menuEl.isConnected) return;
    function onOutside(e) {
      if (menuEl.contains(e.target) || anchorEl.contains(e.target)) return;
      close();
    }
    document.addEventListener("mousedown", onOutside, true);
    removeOutsideListener = () => document.removeEventListener("mousedown", onOutside, true);
  }, 0);

  // ── 공개 제어 핸들 ────────────────────────────────────────────────────────

  function updateQuery(query) {
    filteredItems = filterSlashItems(query);
    highlightedIdx = 0;
    render();
    // 내용이 바뀌면 위치도 재계산 (메뉴 높이 변화 대응)
    positionMenu(menuEl, anchorEl);
  }

  function close() {
    if (!menuEl.isConnected) return;
    menuEl.remove();
    anchorEl.removeEventListener("keydown", onKeydown, { capture: true });
    removeOutsideListener();
  }

  return { updateQuery, close };
}

/**
 * 페이지에 열려 있는 모든 인라인 슬래시 메뉴를 제거한다.
 * (예: 다른 블록 클릭 시 기존 메뉴 정리)
 */
export function closeAllInlineSlashMenus() {
  document.querySelectorAll(".inline-slash-menu").forEach((el) => el.remove());
}
