// ── Shared rich-text editing behaviour ───────────────────────────────────────
//
// makeTextEditable: 텍스트 블록·토글 타이틀 등 여러 블록이 공유하는
// contenteditable 편집 로직을 캡슐화한다.

import { apiPatchBlock, apiChangeBlockType } from "../api.js";
import { openBlockPalette } from "../blockPalette.js";
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
 * @param {boolean}  [opts.enableSlash=true]           - Enable '/' block palette trigger
 * @param {boolean}  [opts.enableHeading=true]         - Enable '# ' heading promotion
 * @param {boolean}  [opts.enableTypeShortcuts=true]   - Enable '> ' → toggle conversion
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
  addBlock = null,
  addBlockAfter = null,
  reloadDocument = null,
} = {}) {
  let originalHtml = node.innerHTML;
  let originalText = node.textContent;
  let currentLevel = node.dataset.level ? Number(node.dataset.level) : null;
  let escaped = false;

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

  // ── Keydown: formatting shortcuts + heading promotion + slash ────────────
  node.addEventListener("keydown", (e) => {
    if (enableSlash && e.key === "/" && node.contentEditable === "true" && !node.textContent.trim()) {
      e.preventDefault();
      node.blur();
      const slashParentId = node.closest(".block-wrapper")?.dataset.parentBlockId || null;
      openBlockPalette(node, slashParentId, null, addBlock);
      return;
    }

    if (node.contentEditable !== "true") return;

    if (e.key === "Escape") {
      e.preventDefault();
      escaped = true;
      node.innerHTML = originalHtml;
      node.contentEditable = "false";
      editingTarget.classList.remove("is-editing");
      clearEditingNode();
      return;
    }

    if (e.key === "Enter" && !e.shiftKey) {
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
        node.classList.remove("is-editing");
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
