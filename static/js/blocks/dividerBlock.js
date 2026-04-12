// ── Divider Block ─────────────────────────────────────────────────────────────

export const type = "divider";

/**
 * @returns {HTMLElement}
 */
export function create() {
  const template = document.getElementById("divider-block-template");
  return template.content.firstElementChild.cloneNode(true);
}
