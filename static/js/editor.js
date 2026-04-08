// ── Inline editing helpers ────────────────────────────────────────────────────

import { apiPatchBlock } from "./api.js";

/**
 * Make an element contenteditable on click.
 * Saves via PATCH on blur/Enter; restores on Escape.
 * @param {HTMLElement} el        - The element to make editable
 * @param {string}      blockId   - Block ID for the API call
 * @param {string}      field     - JSON field name to patch (e.g. "text", "title")
 * @param {HTMLElement} notionBlock - The .notion-block ancestor for is-editing class
 */
export function enableContentEditable(el, blockId, field, notionBlock, { onEnter = null } = {}) {
  let originalText = '';
  let escaped = false;

  el.addEventListener('click', () => {
    if (el.contentEditable === 'true') return;
    originalText = el.textContent;
    escaped = false;
    el.contentEditable = 'true';
    notionBlock.classList.add('is-editing');
    el.focus();

    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    if (sel) {
      sel.removeAllRanges();
      sel.addRange(range);
    }
  });

  el.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      el.blur();
      if (onEnter) onEnter();
    } else if (e.key === 'Escape') {
      escaped = true;
      el.textContent = originalText;
      el.contentEditable = 'false';
      notionBlock.classList.remove('is-editing');
    }
  });

  el.addEventListener('blur', () => {
    if (el.contentEditable !== 'true') return;
    el.contentEditable = 'false';
    notionBlock.classList.remove('is-editing');
    if (escaped) { escaped = false; return; }
    const newText = el.textContent.trim();
    if (newText !== originalText) {
      apiPatchBlock(blockId, { [field]: newText }).catch(console.error);
    }
  });
}
