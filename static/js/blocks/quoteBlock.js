// ── Quote Block ───────────────────────────────────────────────────────────────

import { enableContentEditable } from "../editor.js";

export const type = "quote";

/**
 * @param {object} block
 * @param {object} opts
 * @param {Function} opts.renderBlock - (block, parentBlockId) => HTMLElement
 * @returns {HTMLElement}
 */
export function create(block, { renderBlock } = {}) {
  const template = document.getElementById("quote-block-template");
  const node = template.content.firstElementChild.cloneNode(true);
  const textEl = node.querySelector(".quote-text");
  const childrenRoot = node.querySelector(".quote-children");

  textEl.textContent = block.text || "";
  enableContentEditable(textEl, block.id, "text", node);

  block.children.forEach((child) => {
    if (renderBlock) childrenRoot.appendChild(renderBlock(child, block.id));
  });

  return node;
}
