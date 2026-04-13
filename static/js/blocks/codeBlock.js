// ── Code Block ────────────────────────────────────────────────────────────────

import { apiPatchBlock } from "../api.js";

export const type = "code";

const CODE_LANGUAGES = [
  "plain", "javascript", "typescript", "python", "bash", "html", "css",
  "json", "sql", "java", "go", "rust", "c", "cpp", "mermaid",
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

// ── Mermaid rendering ─────────────────────────────────────────────────────────

/**
 * Mermaid.js를 사용해 소스 코드를 SVG로 렌더링한다.
 * 렌더 성공 시 previewEl에 SVG를 삽입하고, 실패 시 errorEl에 오류 메시지를 표시한다.
 *
 * Ref: https://mermaid.js.org/config/usage.html#using-mermaid-render
 *
 * @param {string} blockId - 블록 고유 ID (mermaid 렌더 ID 생성에 사용)
 * @param {string} source  - Mermaid 문법 소스 코드
 * @param {HTMLElement} previewEl - SVG를 삽입할 컨테이너
 * @param {HTMLElement} errorEl   - 오류 메시지를 표시할 컨테이너
 */
async function renderMermaid(blockId, source, previewEl, errorEl) {
  if (!window.mermaid) {
    errorEl.textContent = "Mermaid 라이브러리를 불러오지 못했습니다.";
    errorEl.hidden = false;
    previewEl.hidden = true;
    return;
  }

  const trimmed = source.trim();
  if (!trimmed) {
    previewEl.innerHTML = "";
    previewEl.hidden = true;
    errorEl.hidden = true;
    return;
  }

  // mermaid.render() 의 id는 DOM에서 고유해야 하며, UUID의 하이픈을 제거해 유효한 HTML id로 변환
  const renderId = `mermaid-${blockId.replace(/-/g, "")}`;
  try {
    const { svg } = await window.mermaid.render(renderId, trimmed);
    previewEl.innerHTML = svg;
    previewEl.hidden = false;
    errorEl.hidden = true;
  } catch (err) {
    // mermaid.render()는 문법 오류 시 Error를 throw한다
    previewEl.innerHTML = "";
    previewEl.hidden = true;
    errorEl.textContent = `Mermaid 문법 오류: ${err?.message ?? "알 수 없는 오류"}`;
    errorEl.hidden = false;
  }
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
  const previewEl = node.querySelector(".mermaid-preview");
  const errorEl = node.querySelector(".mermaid-error");

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

  // ── Mermaid 모드 전환 ─────────────────────────────────────────────────────
  // isMermaid === true 일 때: 코드 에디터(소스 편집) + 미리보기 패널을 함께 표시한다.

  function applyMermaidMode(isMermaid) {
    node.classList.toggle("is-mermaid", isMermaid);
    if (isMermaid) {
      renderMermaid(block.id, plainCode, previewEl, errorEl);
    } else {
      previewEl.hidden = true;
      errorEl.hidden = true;
    }
  }

  // ── Syntax highlighting ──────────────────────────────────────────────────
  function applyHighlight(code) {
    // mermaid 소스는 hljs로 하이라이팅하지 않는다
    if (!window.hljs || currentLanguage === "plain" || currentLanguage === "mermaid") {
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

  // 초기 로드 시 mermaid 모드 적용
  if (currentLanguage === "mermaid") {
    applyMermaidMode(true);
  }

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

  // ── Blur → save + mermaid re-render ──────────────────────────────────────
  codeEl.addEventListener("blur", () => {
    if (codeEl.contentEditable !== "true") return;
    codeEl.contentEditable = "false";
    node.classList.remove("is-editing");
    if (plainCode !== originalCode) {
      originalCode = plainCode;
      apiPatchBlock(block.id, { code: plainCode }).catch(console.error);
    }
    // blur 시점에 mermaid 미리보기를 갱신한다
    if (currentLanguage === "mermaid") {
      renderMermaid(block.id, plainCode, previewEl, errorEl);
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
    const prev = currentLanguage;
    currentLanguage = select.value;
    apiPatchBlock(block.id, { language: currentLanguage }).catch(console.error);
    applyHighlight(plainCode);
    // mermaid ↔ 일반 모드 전환
    if (currentLanguage === "mermaid") {
      applyMermaidMode(true);
    } else if (prev === "mermaid") {
      applyMermaidMode(false);
    }
  });

  copyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(plainCode).then(() => {
      copyBtn.textContent = "복사됨";
      setTimeout(() => { copyBtn.textContent = "복사"; }, 1500);
    }).catch(console.error);
  });

  return node;
}
