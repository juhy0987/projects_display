// ── Page Block ────────────────────────────────────────────────────────────────

export const type = "page";

/**
 * @param {object} block
 * @param {object} opts
 * @param {object} opts.callbacks
 * @returns {HTMLElement}
 */
export function create(block, { callbacks = {} } = {}) {
  const template = document.getElementById("page-block-template");
  const node = template.content.firstElementChild.cloneNode(true);
  const titleEl = node.querySelector(".page-block-title");

  titleEl.textContent = block.title || block.document_id;
  titleEl.dataset.docId = block.document_id;

  node.addEventListener("click", () => {
    if (callbacks.navigateTo) callbacks.navigateTo(block.document_id);
  });

  return node;
}
