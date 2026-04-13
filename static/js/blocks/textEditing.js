// ── Shared rich-text editing behaviour ───────────────────────────────────────
//
// makeTextEditable: 텍스트 블록·토글 타이틀 등 여러 블록이 공유하는
// contenteditable 편집 로직을 캡슐화한다.

import { apiPatchBlock, apiChangeBlockType } from "../api.js";
import { openInlineSlashMenu } from "./inlineSlashMenu.js";
import {
  sanitizeHtml,
  setEditingNode,
  clearEditingNode,
  isInsideToolbar,
} from "../formattingToolbar.js";

/**
 * Attach rich-text editing behaviour to a contenteditable element.
 *
 * @param {HTMLElement} node     - Element to make editable
 * @param {string}      blockId  - Block ID for PATCH calls
 * @param {object}      opts
 * @param {string}   [opts.textField='text']           - Plain-text field name
 * @param {string}   [opts.htmlField='formatted_text'] - Rich-HTML field name
 * @param {string}   [opts.levelField='level']         - Heading level field name
 * @param {Function} [opts.onEnter]                    - Called on Enter (instead of add block after)
 * @param {boolean}  [opts.enableSlash=true]           - Enable '/' inline slash menu trigger
 * @param {boolean}  [opts.enableHeading=true]         - Enable '# ' heading promotion
 * @param {boolean}  [opts.enableTypeShortcuts=true]   - Enable '> ' → toggle conversion
 * @param {string}   [opts.currentBlockType='text']    - Current block type (for heading conversion)
 * @param {Function} [opts.addBlock]                   - callbacks.addBlock
 * @param {Function} [opts.addBlockAfter]              - callbacks.addBlockAfter
 * @param {Function} [opts.reloadDocument]             - callbacks.reloadDocument
 */
export function makeTextEditable(node, blockId, {
  textField = "text",
  htmlField = "formatted_text",
  levelField = "level",
  onEnter = null,
  enableSlash = true,
  enableHeading = true,
  enableTypeShortcuts = true,
  currentBlockType = "text",
  addBlock = null,
  addBlockAfter = null,
  reloadDocument = null,
} = {}) {
  let originalHtml = node.innerHTML;
  let originalText = node.textContent;
  let currentLevel = node.dataset.level ? Number(node.dataset.level) : null;
  let escaped = false;

  // ── 인라인 슬래시 메뉴 상태 ───────────────────────────────────────────────
  // slashMenu: openInlineSlashMenu() 가 반환하는 { updateQuery, close } 핸들
  // slashPreText: '/' 입력 직전의 textContent 스냅샷 (blur 시 저장 복원에 사용)
  // slashPreHtml:  '/' 입력 직전의 innerHTML 스냅샷 (Esc·blur 시 인라인 포맷 보존 복원에 사용)
  let slashMenu = null;
  let slashPreText = "";
  let slashPreHtml = "";

  // is-editing 은 가장 가까운 .notion-block 에 적용
  const editingTarget = node.closest(".notion-block") ?? node;

  // ── Click: activate editing ──────────────────────────────────────────────
  node.addEventListener("click", (e) => {
    if (node.contentEditable !== "true") {
      const anchor = e.target.closest("a[href]");
      if (anchor) {
        e.stopPropagation();
        window.open(anchor.href, "_blank", "noopener,noreferrer");
        return;
      }
    }
    if (node.contentEditable === "true") return;
    // Viewer 모드에서는 편집 진입을 차단한다
    if (document.body.classList.contains("viewer-mode")) return;
    originalHtml = node.innerHTML;
    originalText = node.textContent;
    escaped = false;
    node.contentEditable = "true";
    editingTarget.classList.add("is-editing");
    setEditingNode(node);
    node.focus();
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(node);
    range.collapse(false);
    if (sel) { sel.removeAllRanges(); sel.addRange(range); }
  });

  // ── Blur: save and deactivate ────────────────────────────────────────────
  node.addEventListener("blur", (e) => {
    if (isInsideToolbar(e.relatedTarget)) return;
    if (node.contentEditable !== "true") return;

    // 슬래시 메뉴가 열려 있을 때 blur 가 발생하면 메뉴를 닫고 HTML 을 복원한다.
    // ─ 두 가지 상황에서 이 경로가 실행된다:
    //   ① 메뉴 항목 클릭 시: mousedown preventDefault 로 blur 자체가 막히므로 도달 안 함
    //   ② 외부 요소로 포커스 이동 또는 executeItem→reloadDocument 가 DOM 을 재구성해
    //      node 가 제거될 때 브라우저가 blur 를 발생시키는 경우
    // ─ '/' 이후 query 텍스트 및 인라인 포맷이 손실되지 않도록 slashPreHtml 로 복원한 뒤
    //   아래 일반 저장 로직으로 fall-through 해 슬래시 이전 내용을 정상 저장한다.
    if (slashMenu) {
      slashMenu.close(); // onClose 콜백이 slashMenu = null 을 처리한다
      node.innerHTML = slashPreHtml; // '/' 이전 HTML 복원 (query 텍스트 + 포맷 보존)
      // return 없이 fall-through → 아래 일반 저장 로직이 slashPreHtml 내용을 저장한다
    }

    node.contentEditable = "false";
    editingTarget.classList.remove("is-editing");
    clearEditingNode();

    if (escaped) { escaped = false; return; }

    if (enableHeading) {
      const raw = node.textContent;
      const headingMatch = raw.match(/^(#{1,3})\s+(\S.*)?$/);
      if (headingMatch) {
        const newLevel = headingMatch[1].length;
        const newText = (headingMatch[2] ?? "").trimEnd();
        node.textContent = newText;
        node.dataset.level = String(newLevel);
        const patch = {};
        if (newLevel !== currentLevel) patch[levelField] = newLevel;
        if (newText !== originalText) patch[textField] = newText;
        patch[htmlField] = "";
        currentLevel = newLevel;
        originalText = newText;
        originalHtml = node.innerHTML;
        apiPatchBlock(blockId, patch).catch(console.error);
        return;
      }
    }

    const newText = node.textContent.trim();
    const newHtml = sanitizeHtml(node.innerHTML);
    const patch = {};
    if (newText !== originalText) patch[textField] = newText;
    if (newHtml !== sanitizeHtml(originalHtml)) patch[htmlField] = newHtml;
    if (Object.keys(patch).length) {
      originalText = newText;
      originalHtml = node.innerHTML;
      apiPatchBlock(blockId, patch).catch(console.error);
    }
  });

  // ── Input: 인라인 슬래시 메뉴 트리거 및 query 업데이트 ────────────────────
  //
  // '/' 문자를 keydown 에서 preventDefault 하지 않고 실제 텍스트에 입력되게 허용한다.
  // input 이벤트에서 텍스트에 '/'가 새로 추가됐는지 감지해 메뉴를 연다.
  // 이후 타이핑은 '/' 이후의 query 를 추출해 필터링에 반영한다.
  node.addEventListener("input", () => {
    if (!enableSlash || node.contentEditable !== "true") return;

    const text = node.textContent;

    if (slashMenu) {
      // 메뉴가 이미 열려 있는 상태: '/' 이후 query 를 추출해 업데이트
      const slashIdx = text.lastIndexOf("/");
      if (slashIdx === -1) {
        // '/'가 지워지면 메뉴 닫기. onClose 콜백이 slashMenu = null 을 처리한다.
        slashMenu.close();
      } else {
        slashMenu.updateQuery(text.slice(slashIdx + 1));
      }
      return;
    }

    // 슬래시가 새로 입력됐는지 확인 — lastIndexOf 로 마지막 '/' 위치를 찾는다.
    // 기존 텍스트에 '/'가 없었고 지금 있다면 방금 입력된 것으로 간주한다.
    if (text.endsWith("/") && !originalText.includes("/")) {
      slashPreText = text.slice(0, -1); // '/' 이전 텍스트 스냅샷 저장

      // TreeWalker 로 마지막 텍스트 노드에서 '/' 를 제거한 innerHTML 스냅샷을 저장한다.
      // textContent 복원은 <b>·<a> 등 인라인 포맷을 제거하므로 innerHTML 로 보존한다.
      const clone = node.cloneNode(true);
      const walker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT);
      let lastTextNode = null;
      while (walker.nextNode()) lastTextNode = walker.currentNode;
      if (lastTextNode?.textContent.endsWith("/")) {
        lastTextNode.textContent = lastTextNode.textContent.slice(0, -1);
      }
      slashPreHtml = clone.innerHTML;

      slashMenu = openInlineSlashMenu(node, blockId, currentBlockType, {
        reloadDocument,
        // 메뉴가 자체적으로 닫힐 때(외부 클릭·Enter·Esc) slashMenu 를 null 로 동기화.
        // 이 콜백이 없으면 메뉴가 닫힌 뒤에도 input 핸들러가 updateQuery 를 계속
        // 호출하거나 Enter 처리가 차단된 상태로 남는 상태 불일치가 발생한다.
        onClose: () => { slashMenu = null; },
      });
    }
  });

  // ── Keydown: formatting shortcuts + heading promotion ────────────────────
  node.addEventListener("keydown", (e) => {
    if (node.contentEditable !== "true") return;

    if (e.key === "Escape") {
      e.preventDefault();

      // 슬래시 메뉴가 열려 있으면 메뉴만 닫고 텍스트를 슬래시 이전 상태로 복원.
      // onClose 콜백이 slashMenu = null 을 처리하므로 여기서는 별도 설정 불필요.
      if (slashMenu) {
        slashMenu.close();
        // '/' 이후 query 텍스트를 제거하고 슬래시 입력 전 HTML 로 복원한다.
        // textContent 복원은 <b>·<a> 등 인라인 포맷을 제거하므로 innerHTML 로 복원한다.
        node.innerHTML = slashPreHtml;
        return;
      }

      escaped = true;
      node.innerHTML = originalHtml;
      node.contentEditable = "false";
      editingTarget.classList.remove("is-editing");
      clearEditingNode();
      return;
    }

    if (e.key === "Enter" && !e.shiftKey) {
      // 슬래시 메뉴가 열려 있는 경우, Enter 는 inlineSlashMenu.js 의 keydown
      // 핸들러(capture)가 먼저 처리한다. 이 핸들러는 나중에 등록됐으므로
      // 여기서는 건너뛰어 이중 실행을 방지한다.
      if (slashMenu) return;

      if (enableHeading) {
        const raw = node.textContent;
        const exactPrefix = raw.match(/^(#{1,3})$/);
        if (exactPrefix) {
          e.preventDefault();
          e.stopImmediatePropagation();
          const newLevel = exactPrefix[1].length;
          node.textContent = "";
          node.dataset.level = String(newLevel);
          const patch = { [levelField]: newLevel, [textField]: "", [htmlField]: "" };
          currentLevel = newLevel;
          originalText = "";
          originalHtml = "";
          apiPatchBlock(blockId, patch).catch(console.error);
          return;
        }
      }
      e.preventDefault();
      if (onEnter) {
        onEnter();
      } else {
        node.blur();
        const parentBlockId = node.closest(".block-wrapper")?.dataset.parentBlockId || null;
        if (addBlockAfter) {
          addBlockAfter("text", blockId, parentBlockId).catch(console.error);
        }
      }
      return;
    }

    if (e.key === " ") {
      const raw = node.textContent;

      // '> ' → convert block to toggle
      if (enableTypeShortcuts && raw === ">") {
        e.preventDefault();
        e.stopImmediatePropagation();
        node.contentEditable = "false";
        editingTarget.classList.remove("is-editing");
        clearEditingNode();
        apiChangeBlockType(blockId, "toggle")
          .then(() => reloadDocument?.())
          .catch(console.error);
        return;
      }

      // '# ' / '## ' / '### ' → heading promotion
      if (enableHeading) {
        const exactPrefix = raw.match(/^(#{1,3})$/);
        if (!exactPrefix) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        const newLevel = exactPrefix[1].length;
        node.textContent = "";
        node.dataset.level = String(newLevel);
        const patch = { [levelField]: newLevel, [textField]: "", [htmlField]: "" };
        currentLevel = newLevel;
        originalText = "";
        originalHtml = "";
        apiPatchBlock(blockId, patch).catch(console.error);
      }
    }

    if (e.ctrlKey || e.metaKey) {
      if (e.key === "b") { e.preventDefault(); document.execCommand("bold", false); }
      else if (e.key === "i") { e.preventDefault(); document.execCommand("italic", false); }
      else if (e.key === "u") { e.preventDefault(); document.execCommand("underline", false); }
    }
  }, { capture: true });
}
