// ── Text Block ────────────────────────────────────────────────────────────────

import { sanitizeHtml } from "../formattingToolbar.js";
import { makeTextEditable } from "./textEditing.js";

export const type = "text";

/**
 * @param {object} block
 * @param {object} opts
 * @param {object} opts.callbacks
 * @returns {HTMLElement}
 */
export function create(block, { callbacks = {} } = {}) {
  const template = document.getElementById("text-block-template");
  const node = template.content.firstElementChild.cloneNode(true);

  if (block.formatted_text) {
    node.innerHTML = sanitizeHtml(block.formatted_text);
  } else {
    node.textContent = block.text;
  }

  if (block.level) node.dataset.level = String(block.level);

  makeTextEditable(node, block.id, {
    addBlock: callbacks.addBlock,
    addBlockAfter: callbacks.addBlockAfter,
    reloadDocument: callbacks.reloadDocument,
  });

  return node;
}
