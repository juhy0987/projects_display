// ── Code Block ────────────────────────────────────────────────────────────────

import { apiPatchBlock } from "../api.js";

export const type = "code";

const CODE_LANGUAGES = [
  "plain", "javascript", "typescript", "python", "bash", "html", "css",
  "json", "sql", "java", "go", "rust", "c", "cpp",
];

// ── Caret offset helpers ──────────────────────────────────────────────────────

function getCaretOffset(el) {
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount) return 0;
  const range = sel.getRangeAt(0).cloneRange();
  range.selectNodeContents(el);
  range.setEnd(sel.getRangeAt(0).endContainer, sel.getRangeAt(0).endOffset);
  return range.toString().length;
}

function setCaretOffset(el, offset) {
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let remaining = offset;
  let node;
  while ((node = walker.nextNode())) {
    if (remaining <= node.textContent.length) {
      const range = document.createRange();
      range.setStart(node, remaining);
      range.collapse(true);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
      return;
    }
    remaining -= node.textContent.length;
  }
  // Fallback: place cursor at end
  const range = document.createRange();
  range.selectNodeContents(el);
  range.collapse(false);
  window.getSelection()?.removeAllRanges();
  window.getSelection()?.addRange(range);
}

/**
 * @param {object} block
 * @returns {HTMLElement}
 */
export function create(block) {
  const template = document.getElementById("code-block-template");
  const node = template.content.firstElementChild.cloneNode(true);
  const select = node.querySelector(".code-language-select");
  const codeEl = node.querySelector(".code-content");
  const copyBtn = node.querySelector(".code-copy-btn");

  let currentLanguage = block.language || "plain";
  let plainCode = block.code || "";
  let originalCode = plainCode;

  CODE_LANGUAGES.forEach((lang) => {
    const opt = document.createElement("option");
    opt.value = lang;
    opt.textContent = lang;
    if (lang === currentLanguage) opt.selected = true;
    select.appendChild(opt);
  });

  // ── Syntax highlighting ──────────────────────────────────────────────────
  function applyHighlight(code) {
    if (!window.hljs || currentLanguage === "plain") {
      codeEl.textContent = code;
      return;
    }
    try {
      const result = window.hljs.highlight(code, {
        language: currentLanguage,
        ignoreIllegals: true,
      });
      codeEl.innerHTML = result.value;
    } catch {
      codeEl.textContent = code;
    }
  }

  applyHighlight(plainCode);

  // ── IME 조합 상태 추적 ──────────────────────────────────────────────────
  let isComposing = false;
  codeEl.addEventListener("compositionstart", () => { isComposing = true; });
  codeEl.addEventListener("compositionend", () => {
    isComposing = false;
    const offset = getCaretOffset(codeEl);
    plainCode = codeEl.textContent;
    applyHighlight(plainCode);
    setCaretOffset(codeEl, offset);
  });

  // ── Click → activate editing ─────────────────────────────────────────────
  codeEl.addEventListener("click", () => {
    if (codeEl.contentEditable === "true") return;
    codeEl.contentEditable = "true";
    node.classList.add("is-editing");
    codeEl.focus();
    const range = document.createRange();
    range.selectNodeContents(codeEl);
    range.collapse(false);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
  });

  // ── Input → live highlight ────────────────────────────────────────────────
  codeEl.addEventListener("input", () => {
    if (isComposing) {
      plainCode = codeEl.textContent;
      return;
    }
    const offset = getCaretOffset(codeEl);
    plainCode = codeEl.textContent;
    applyHighlight(plainCode);
    setCaretOffset(codeEl, offset);
  });

  // ── Blur → save ──────────────────────────────────────────────────────────
  codeEl.addEventListener("blur", () => {
    if (codeEl.contentEditable !== "true") return;
    codeEl.contentEditable = "false";
    node.classList.remove("is-editing");
    if (plainCode !== originalCode) {
      originalCode = plainCode;
      apiPatchBlock(block.id, { code: plainCode }).catch(console.error);
    }
  });

  codeEl.addEventListener("keydown", (e) => {
    if (e.key === "Tab") {
      e.preventDefault();
      document.execCommand("insertText", false, "  ");
    }
    if (e.key === "Escape") codeEl.blur();
  });

  // ── Language change ───────────────────────────────────────────────────────
  select.addEventListener("change", () => {
    currentLanguage = select.value;
    apiPatchBlock(block.id, { language: currentLanguage }).catch(console.error);
    applyHighlight(plainCode);
  });

  copyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(plainCode).then(() => {
      copyBtn.textContent = "복사됨";
      setTimeout(() => { copyBtn.textContent = "복사"; }, 1500);
    }).catch(console.error);
  });

  return node;
}
