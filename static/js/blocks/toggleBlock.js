// ── Toggle Block ──────────────────────────────────────────────────────────────

import { apiPatchBlock } from "../api.js";
import { sanitizeHtml } from "../formattingToolbar.js";
import { makeTextEditable } from "./textEditing.js";

export const type = "toggle";

/**
 * @param {object} block
 * @param {object} opts
 * @param {object} opts.callbacks
 * @param {Function} opts.renderBlock   - (block, parentBlockId) => HTMLElement
 * @param {Function} [opts.focusBlock]  - (wrapperEl) => void
 * @returns {HTMLElement}
 */
export function create(block, { callbacks = {}, renderBlock, focusBlock } = {}) {
  const template = document.getElementById("toggle-block-template");
  const node = template.content.firstElementChild.cloneNode(true);
  const arrowBtn = node.querySelector(".toggle-arrow-btn");
  const titleEl = node.querySelector(".toggle-title");
  const childrenRoot = node.querySelector(".toggle-children");

  let isOpen = !!block.is_open;

  function applyOpen(open) {
    isOpen = open;
    childrenRoot.hidden = !open;
    arrowBtn.setAttribute("aria-expanded", String(open));
    arrowBtn.classList.toggle("is-open", open);
  }

  applyOpen(isOpen);

  if (block.formatted_text) {
    titleEl.innerHTML = sanitizeHtml(block.formatted_text);
  } else {
    titleEl.textContent = block.text || "";
  }
  if (block.level) titleEl.dataset.level = String(block.level);

  // ── Arrow button: open/close ─────────────────────────────────────────────
  arrowBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    applyOpen(!isOpen);
    apiPatchBlock(block.id, { is_open: isOpen }).catch(console.error);
  });

  // ── Title editing ────────────────────────────────────────────────────────
  makeTextEditable(titleEl, block.id, {
    enableSlash: false,
    enableTypeShortcuts: false,
    addBlock: callbacks.addBlock,
    addBlockAfter: callbacks.addBlockAfter,
    reloadDocument: callbacks.reloadDocument,
    onEnter: () => {
      titleEl.blur();
      if (!isOpen) {
        applyOpen(true);
        apiPatchBlock(block.id, { is_open: true }).catch(console.error);
      }
      const firstChild = childrenRoot.querySelector(":scope > .block-wrapper");
      if (firstChild && focusBlock) focusBlock(firstChild);
    },
  });

  block.children.forEach((child) => {
    if (renderBlock) childrenRoot.appendChild(renderBlock(child, block.id));
  });

  return node;
}
