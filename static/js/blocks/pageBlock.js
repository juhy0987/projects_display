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
  const iconEl = node.querySelector(".page-block-icon");

  titleEl.textContent = block.title || block.document_id;
  titleEl.dataset.docId = block.document_id;

  if (block.is_broken_ref) {
    node.classList.add("is-broken-ref");
    iconEl.textContent = "⚠";
    titleEl.textContent = block.title || "삭제된 페이지";
    node.setAttribute("aria-label", `삭제된 페이지: ${titleEl.textContent}`);
    node.setAttribute("aria-disabled", "true");
    node.removeAttribute("tabindex");
    return node;
  }

  node.setAttribute("tabindex", "0");
  node.setAttribute("aria-label", `페이지로 이동: ${titleEl.textContent}`);

  function navigate() {
    if (callbacks.navigateTo) callbacks.navigateTo(block.document_id);
  }

  node.addEventListener("click", navigate);
  node.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      navigate();
    }
  });

  return node;
}
