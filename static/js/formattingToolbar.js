// ── Formatting toolbar ────────────────────────────────────────────────────────
//
// Floating toolbar that appears over selected text inside a text block.
// Uses document.execCommand for basic formatting and custom logic for
// inline code, links, and colors.

const TEXT_COLORS = [
  { label: "기본", value: "" },
  { label: "회색", value: "#787774" },
  { label: "빨강", value: "#e03e3e" },
  { label: "주황", value: "#d9730d" },
  { label: "노랑", value: "#dfab01" },
  { label: "초록", value: "#0f7b6c" },
  { label: "파랑", value: "#0b6e99" },
  { label: "보라", value: "#6940a5" },
  { label: "분홍", value: "#ad1a72" },
];

const BG_COLORS = [
  { label: "기본", value: "" },
  { label: "회색", value: "#f1f1ef" },
  { label: "빨강", value: "#fbe4e4" },
  { label: "주황", value: "#faebdd" },
  { label: "노랑", value: "#fef3b8" },
  { label: "초록", value: "#ddedea" },
  { label: "파랑", value: "#ddebf1" },
  { label: "보라", value: "#eae4f2" },
  { label: "분홍", value: "#f4dfeb" },
];

// ── HTML sanitizer ────────────────────────────────────────────────────────────

const ALLOWED_TAGS = new Set(["strong", "b", "em", "i", "u", "s", "del", "code", "a", "span", "br"]);
const ALLOWED_ATTRS = { a: ["href"], span: ["style"] };

/**
 * Recursively sanitize a DOM node in-place, removing disallowed tags/attributes.
 * Disallowed elements are unwrapped (children kept); disallowed attributes removed.
 */
function sanitizeNode(node) {
  const children = [...node.childNodes];
  for (const child of children) {
    if (child.nodeType === Node.TEXT_NODE) continue;
    if (child.nodeType !== Node.ELEMENT_NODE) { child.remove(); continue; }

    const tag = child.tagName.toLowerCase();
    if (!ALLOWED_TAGS.has(tag)) {
      // Unwrap: keep children, discard wrapper element
      child.replaceWith(...child.childNodes);
      continue;
    }

    // Remove disallowed attributes
    const allowed = ALLOWED_ATTRS[tag] || [];
    for (const attr of [...child.attributes]) {
      if (!allowed.includes(attr.name)) child.removeAttribute(attr.name);
    }

    // Validate href: only http/https allowed
    if (tag === "a") {
      const href = child.getAttribute("href") || "";
      if (href && !/^https?:\/\//i.test(href)) child.removeAttribute("href");
    }

    // Restrict style to safe properties
    if (child.hasAttribute("style")) {
      const s = child.style;
      const safe = ["color", "background-color", "font-size"]
        .filter((p) => s.getPropertyValue(p))
        .map((p) => `${p}: ${s.getPropertyValue(p)}`)
        .join("; ");
      if (safe) child.setAttribute("style", safe);
      else child.removeAttribute("style");
    }

    sanitizeNode(child);
  }
}

export function sanitizeHtml(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  sanitizeNode(doc.body);
  return doc.body.innerHTML;
}

// ── Toolbar singleton ─────────────────────────────────────────────────────────

let toolbarEl = null;
let colorPanelEl = null;
let linkPanelEl = null;
let activeTextNode = null;
let savedRange = null;

function restoreSelection() {
  if (!savedRange) return;
  const sel = window.getSelection();
  if (sel) {
    sel.removeAllRanges();
    sel.addRange(savedRange);
  }
}

// ── Inline code toggle ────────────────────────────────────────────────────────
//
// - Entire selection in one <code>  → unwrap
// - Partial <code> or none          → strip any nested codes, wrap all in one <code>

function getCodeAncestor(node) {
  const el = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
  return el?.closest("code") ?? null;
}

function toggleInlineCode() {
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount || sel.isCollapsed) return;
  const range = sel.getRangeAt(0);

  const startCode = getCodeAncestor(range.startContainer);
  const endCode = getCodeAncestor(range.endContainer);

  // Entire selection is within the same <code> → unwrap it
  if (startCode && startCode === endCode) {
    startCode.replaceWith(...startCode.childNodes);
    return;
  }

  // Partial or no code → extract, flatten nested codes, wrap in one new <code>
  const frag = range.extractContents();
  frag.querySelectorAll("code").forEach((c) => c.replaceWith(...c.childNodes));
  const code = document.createElement("code");
  code.appendChild(frag);
  range.insertNode(code);
}

// ── Link insert / remove ──────────────────────────────────────────────────────

function applyLink(url) {
  restoreSelection();
  if (!url) {
    document.execCommand("unlink", false);
    return;
  }
  document.execCommand("createLink", false, url);
  // Force target="_blank" on created link
  const sel = window.getSelection();
  if (sel && sel.rangeCount) {
    const anchor = sel.getRangeAt(0).commonAncestorContainer.parentElement?.closest("a");
    if (anchor) anchor.target = "_blank";
  }
}

// ── Color application ─────────────────────────────────────────────────────────

function applyTextColor(color) {
  restoreSelection();
  if (!color) {
    document.execCommand("foreColor", false, "inherit");
    return;
  }
  document.execCommand("foreColor", false, color);
}

function applyBgColor(color) {
  restoreSelection();
  if (!color) {
    document.execCommand("hiliteColor", false, "transparent");
    return;
  }
  document.execCommand("hiliteColor", false, color);
}

// ── Build toolbar DOM ─────────────────────────────────────────────────────────

function buildColorSwatches(colors, onSelect) {
  const wrap = document.createElement("div");
  wrap.className = "fmt-color-swatches";
  for (const { label, value } of colors) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.title = label;
    btn.className = "fmt-color-swatch-btn" + (value === "" ? " is-default" : "");
    if (value) btn.style.background = value;
    btn.addEventListener("mousedown", (e) => { e.preventDefault(); onSelect(value); });
    wrap.appendChild(btn);
  }
  return wrap;
}

function buildColorPanel() {
  const panel = document.createElement("div");
  panel.className = "fmt-color-panel";

  const textLabel = document.createElement("div");
  textLabel.className = "fmt-color-section-label";
  textLabel.textContent = "텍스트 색상";

  const textSwatches = buildColorSwatches(TEXT_COLORS, (v) => { applyTextColor(v); closeColorPanel(); });

  const bgLabel = document.createElement("div");
  bgLabel.className = "fmt-color-section-label";
  bgLabel.textContent = "배경 색상";

  const bgSwatches = buildColorSwatches(BG_COLORS, (v) => { applyBgColor(v); closeColorPanel(); });

  panel.append(textLabel, textSwatches, bgLabel, bgSwatches);
  return panel;
}

function buildLinkPanel() {
  const panel = document.createElement("div");
  panel.className = "fmt-link-panel";

  const input = document.createElement("input");
  input.type = "url";
  input.className = "fmt-link-input";
  input.placeholder = "https://...";

  const confirm = document.createElement("button");
  confirm.type = "button";
  confirm.className = "fmt-link-confirm";
  confirm.textContent = "적용";

  function commit() {
    applyLink(input.value.trim());
    closeLinkPanel();
  }

  confirm.addEventListener("mousedown", (e) => { e.preventDefault(); commit(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); commit(); }
    if (e.key === "Escape") { e.preventDefault(); closeLinkPanel(); }
  });

  panel.append(input, confirm);
  panel._input = input; // expose for focus
  return panel;
}

function closeColorPanel() {
  if (colorPanelEl) colorPanelEl.classList.remove("is-open");
}

function closeLinkPanel() {
  if (linkPanelEl) linkPanelEl.classList.remove("is-open");
}

function makeFmtBtn(label, title, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "fmt-btn";
  btn.title = title;
  btn.innerHTML = label;
  btn.addEventListener("mousedown", (e) => {
    e.preventDefault(); // keep selection alive
    onClick(e, btn);
  });
  return btn;
}

function makeDivider() {
  const d = document.createElement("div");
  d.className = "fmt-divider";
  return d;
}

// ── Active node tracking (prevents per-block selectionchange listeners) ────────

let currentEditingNode = null;

export function setEditingNode(node) {
  currentEditingNode = node;
}

export function clearEditingNode() {
  currentEditingNode = null;
  hideFormattingToolbar();
}

export function initFormattingToolbar() {
  if (toolbarEl) return; // already initialised

  toolbarEl = document.createElement("div");
  toolbarEl.className = "formatting-toolbar";
  toolbarEl.setAttribute("role", "toolbar");
  toolbarEl.setAttribute("aria-label", "텍스트 서식");

  // Bold
  toolbarEl.appendChild(makeFmtBtn("<b>B</b>", "굵게 (Ctrl+B)", () => {
    document.execCommand("bold", false);
  }));

  // Italic
  toolbarEl.appendChild(makeFmtBtn("<i>I</i>", "기울임 (Ctrl+I)", () => {
    document.execCommand("italic", false);
  }));

  // Underline
  toolbarEl.appendChild(makeFmtBtn("<u>U</u>", "밑줄 (Ctrl+U)", () => {
    document.execCommand("underline", false);
  }));

  // Strikethrough
  toolbarEl.appendChild(makeFmtBtn("<s>S</s>", "취소선", () => {
    document.execCommand("strikeThrough", false);
  }));

  toolbarEl.appendChild(makeDivider());

  // Inline code
  toolbarEl.appendChild(makeFmtBtn("<code style='font-size:0.78rem;background:rgba(255,255,255,0.15);padding:1px 4px;border-radius:3px;color:#f8f8f2'>&lt;/&gt;</code>", "인라인 코드", () => {
    toggleInlineCode();
  }));

  toolbarEl.appendChild(makeDivider());

  // Link
  const linkBtn = makeFmtBtn("🔗", "링크 삽입", () => {
    closeColorPanel();
    if (linkPanelEl.classList.contains("is-open")) {
      closeLinkPanel();
      return;
    }
    // Prefill if selection is inside a link
    const sel = window.getSelection();
    if (sel && sel.rangeCount) {
      savedRange = sel.getRangeAt(0).cloneRange();
      const anchor = sel.getRangeAt(0).commonAncestorContainer.parentElement?.closest("a");
      linkPanelEl._input.value = anchor ? anchor.href : "";
    }
    linkPanelEl.classList.add("is-open");
    setTimeout(() => linkPanelEl._input.focus(), 0);
  });
  linkBtn.style.fontSize = "0.9rem";
  linkBtn.appendChild(linkPanelEl = buildLinkPanel());
  toolbarEl.appendChild(linkBtn);

  toolbarEl.appendChild(makeDivider());

  // Text/background color
  const colorBtn = makeFmtBtn("A", "색상", () => {
    closeLinkPanel();
    if (colorPanelEl.classList.contains("is-open")) {
      closeColorPanel();
      return;
    }
    const sel = window.getSelection();
    if (sel && sel.rangeCount) savedRange = sel.getRangeAt(0).cloneRange();
    colorPanelEl.classList.add("is-open");
  });
  colorBtn.style.textDecoration = "underline";
  colorBtn.style.textDecorationColor = "#e03e3e";
  colorBtn.style.textDecorationThickness = "2px";
  colorBtn.className += " fmt-color-btn";
  colorBtn.appendChild(colorPanelEl = buildColorPanel());
  toolbarEl.appendChild(colorBtn);

  document.body.appendChild(toolbarEl);

  // Single shared selectionchange listener — updates toolbar for active node only
  document.addEventListener("selectionchange", () => {
    if (!currentEditingNode) return;
    showFormattingToolbar(currentEditingNode);
  });

  // Close sub-panels when clicking outside the toolbar
  document.addEventListener("mousedown", (e) => {
    if (!toolbarEl.contains(e.target)) {
      closeColorPanel();
      closeLinkPanel();
    }
  });
}

// ── Show / hide ───────────────────────────────────────────────────────────────

export function showFormattingToolbar(textNode) {
  if (!toolbarEl) return;
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) { hideFormattingToolbar(); return; }

  const range = sel.getRangeAt(0);
  if (!textNode.contains(range.commonAncestorContainer)) { hideFormattingToolbar(); return; }

  const rect = range.getBoundingClientRect();
  if (rect.width === 0) { hideFormattingToolbar(); return; }

  activeTextNode = textNode;
  toolbarEl.classList.add("is-visible");

  // Reflow needed to get toolbarEl dimensions
  const tw = toolbarEl.offsetWidth;
  const th = toolbarEl.offsetHeight;
  const scrollX = window.scrollX;
  const scrollY = window.scrollY;

  let top = rect.top + scrollY - th - 10;
  let left = rect.left + scrollX + rect.width / 2 - tw / 2;

  // Clamp to viewport
  if (top < scrollY + 8) top = rect.bottom + scrollY + 8;
  left = Math.max(scrollX + 8, Math.min(left, scrollX + window.innerWidth - tw - 8));

  toolbarEl.style.top = `${top}px`;
  toolbarEl.style.left = `${left}px`;
}

export function hideFormattingToolbar() {
  if (!toolbarEl) return;
  toolbarEl.classList.remove("is-visible");
  closeColorPanel();
  closeLinkPanel();
  activeTextNode = null;
}
