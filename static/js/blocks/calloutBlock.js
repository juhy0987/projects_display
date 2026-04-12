// ── Callout Block ─────────────────────────────────────────────────────────────

import { enableContentEditable } from "../editor.js";

export const type = "callout";

/**
 * @param {object} block
 * @param {object} opts
 * @param {Function} opts.renderBlock - (block, parentBlockId) => HTMLElement
 * @returns {HTMLElement}
 */
export function create(block, { renderBlock } = {}) {
  const template = document.getElementById("callout-block-template");
  const node = template.content.firstElementChild.cloneNode(true);
  const emojiEl = node.querySelector(".callout-emoji");
  const textEl = node.querySelector(".callout-text");
  const childrenRoot = node.querySelector(".callout-children");

  node.dataset.color = block.color || "yellow";
  emojiEl.textContent = block.emoji || "💡";
  textEl.textContent = block.text || "";
  enableContentEditable(textEl, block.id, "text", node);

  (block.children || []).forEach((child) => {
    if (renderBlock) childrenRoot.appendChild(renderBlock(child, block.id));
  });

  return node;
}
