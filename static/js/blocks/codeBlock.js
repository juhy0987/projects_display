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

// ── Mermaid hljs 언어 정의 ────────────────────────────────────────────────────
// CDN 추가 없이 highlight.js에 mermaid 언어를 직접 등록한다.
// Ref: https://highlightjs.readthedocs.io/en/latest/language-guide.html

/**
 * highlight.js 언어 정의 객체를 반환한다.
 * @param {object} hljs - highlight.js 전역 객체
 */
function _mermaidHljsDefinition(hljs) {
  return {
    name: "Mermaid",
    case_insensitive: false,
    keywords: {
      // 다이어그램 선언 키워드 — 첫 줄에 등장하는 다이어그램 타입 식별자
      built_in:
        "graph flowchart sequenceDiagram erDiagram classDiagram " +
        "stateDiagram stateDiagram-v2 gantt pie gitGraph mindmap " +
        "timeline journey xychart-beta block",
      // 흐름/구조 제어 키워드
      keyword:
        "TD LR RL BT TB direction participant actor autonumber " +
        "loop alt else opt par and critical break rect note over as " +
        "end title accTitle accDescr section subgraph click call " +
        "style linkStyle classDef class",
    },
    contains: [
      // %% 단일 행 주석
      hljs.COMMENT("%%", "$"),
      // 큰따옴표 문자열 레이블
      hljs.QUOTE_STRING_MODE,
      // 대괄호 노드 레이블: A[label], A[/label/], A[\label\]
      {
        className: "string",
        begin: /\[/,
        end: /\]/,
        relevance: 0,
      },
      // 소괄호/이중소괄호 노드: B(label), C((label))
      {
        className: "string",
        begin: /\(/,
        end: /\)/,
        relevance: 0,
      },
      // 중괄호 노드: D{label}
      {
        className: "string",
        begin: /\{/,
        end: /\}/,
        relevance: 0,
      },
      // 화살표 · ER 관계 커넥터
      // flowchart: -->, -.->. ==>, ---, --
      // sequence:  ->>, ->>, -->> , -x, -), <<->>
      // ER:        ||--o{, }|--|{, |o--||  등
      {
        className: "operator",
        match: /\.{1,2}-{0,2}>?|-{2,3}>?|={2,3}>?|>{1,2}|<{1,2}|[|o*}{]{1,3}-{1,3}[|o*}{]{1,3}/,
      },
    ],
  };
}

/** hljs.registerLanguage 는 1회만 호출해야 하므로 등록 여부를 추적한다. */
let _mermaidHljsRegistered = false;

function _ensureMermaidHljs() {
  if (_mermaidHljsRegistered || !window.hljs) return;
  window.hljs.registerLanguage("mermaid", _mermaidHljsDefinition);
  _mermaidHljsRegistered = true;
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
 * @param {function(): boolean} isCancelled - true를 반환하면 DOM 갱신을 건너뛴다.
 *   blur → language change 순서로 이벤트가 발생할 때, blur 핸들러에서 시작된
 *   async 렌더가 language change 이후에 완료되며 previewEl을 다시 노출시키는
 *   경쟁 조건을 방지한다.
 */
async function renderMermaid(blockId, source, previewEl, errorEl, isCancelled = () => false) {
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

  // mermaid.render() 의 id는 호출 시점마다 DOM 내에서 고유해야 한다.
  // 동일 블록을 재렌더링(blur 후 수정 → blur)하면 이전 SVG가 동일 id를 가진 채 DOM에 남아
  // 충돌이 발생한다. Date.now() 를 접미사로 붙여 매 호출마다 고유 id를 보장한다.
  // Ref: https://mermaid.js.org/config/usage.html#using-mermaid-render
  const renderId = `mermaid-${blockId.replace(/-/g, "")}-${Date.now()}`;
  try {
    const { svg } = await window.mermaid.render(renderId, trimmed);
    if (isCancelled()) return; // 렌더 완료 전 언어 전환 등으로 mermaid 모드가 해제된 경우
    previewEl.innerHTML = svg;

    // Mermaid v10+ 는 SVG에 두 가지 방식으로 크기를 고정한다.
    //   1) HTML attribute: width="NNN" height="NNN"
    //   2) inline style:  style="max-width: NNNpx;"
    // 두 값 모두 외부 CSS보다 우선하므로 제거해야 CSS width/height:auto 가 적용된다.
    // viewBox 속성은 유지해 CSS width 기준으로 종횡비가 계산되도록 한다.
    const svgEl = previewEl.querySelector("svg");
    if (svgEl) {
      svgEl.removeAttribute("width");
      svgEl.removeAttribute("height");
      svgEl.style.width = "";
      svgEl.style.height = "";
      svgEl.style.maxWidth = "";
    }

    previewEl.hidden = false;
    errorEl.hidden = true;
  } catch (err) {
    if (isCancelled()) return;
    // mermaid.render()는 문법 오류 시 Error 객체 또는 문자열을 throw할 수 있다.
    // err?.message || err 순서로 평가해 두 경우를 모두 커버한다.
    previewEl.innerHTML = "";
    previewEl.hidden = true;
    errorEl.textContent = "Mermaid 문법 오류: " + (err?.message || err || "알 수 없는 오류");
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

  // 세대 카운터: applyMermaidMode(false) 시 증가해 in-flight 렌더를 무효화한다.
  // 각 렌더 시작 시 현재 세대를 캡처하고, 완료 시점에 세대가 바뀌었으면 DOM 갱신을 생략한다.
  let _renderGen = 0;

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
      const gen = ++_renderGen;
      renderMermaid(block.id, plainCode, previewEl, errorEl, () => _renderGen !== gen);
    } else {
      ++_renderGen; // 진행 중인 렌더 취소
      previewEl.hidden = true;
      errorEl.hidden = true;
    }
  }

  // ── Syntax highlighting ──────────────────────────────────────────────────
  function applyHighlight(code) {
    if (!window.hljs || currentLanguage === "plain") {
      codeEl.textContent = code;
      return;
    }
    // mermaid 언어가 아직 등록되지 않았을 경우 최초 호출 시 등록한다
    if (currentLanguage === "mermaid") _ensureMermaidHljs();
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
      const gen = ++_renderGen;
      renderMermaid(block.id, plainCode, previewEl, errorEl, () => _renderGen !== gen);
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
