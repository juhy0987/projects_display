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
 *
 * 렌더 결과에 따라 DOM을 갱신한다.
 * - 성공: previewEl 에 SVG 삽입, mediaWrapEl 표시, actionsEl 활성화
 * - 빈 입력: previewEl 초기화, mediaWrapEl 및 오류 숨김
 * - 실패: opreviewEl 초기화, errorMsgEl 에 오류 메시지 표시
 *
 * Ref: https://mermaid.js.org/config/usage.html#using-mermaid-render
 *
 * @param {string} blockId       - 블록 고유 ID (mermaid 렌더 ID 생성에 사용)
 * @param {string} source        - Mermaid 문법 소스 코드
 * @param {object} opts
 * @param {HTMLElement} opts.previewEl    - SVG를 삽입할 컨테이너
 * @param {HTMLElement} opts.errorEl      - 오류 영역 전체 컨테이너
 * @param {HTMLElement} opts.errorMsgEl   - 오류 메시지 텍스트 span
 * @param {HTMLElement} opts.mediaWrapEl  - 미리보기 래퍼 (hidden 관리)
 * @param {HTMLElement} opts.actionsEl    - 액션 버튼 overlay (hidden 관리)
 * @param {function(): boolean} opts.isCancelled
 *   true를 반환하면 DOM 갱신을 건너뛴다.
 *   blur → language change 순서로 이벤트가 발생할 때, blur 핸들러에서 시작된
 *   async 렌더가 language change 이후에 완료되며 previewEl을 다시 노출시키는
 *   경쟁 조건을 방지한다.
 */
async function renderMermaid(blockId, source, opts = {}) {
  const {
    previewEl,
    errorEl,
    errorMsgEl,
    mediaWrapEl,
    actionsEl,
    isCancelled = () => false,
  } = opts;

  if (!window.mermaid) {
    errorMsgEl.textContent = "Mermaid 라이브러리를 불러오지 못했습니다.";
    errorEl.hidden = false;
    mediaWrapEl.hidden = true;
    actionsEl.hidden = true;
    return;
  }

  const trimmed = source.trim();
  if (!trimmed) {
    previewEl.innerHTML = "";
    mediaWrapEl.hidden = true;
    actionsEl.hidden = true;
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

    mediaWrapEl.hidden = false;
    actionsEl.hidden = false; // CSS hover가 opacity 제어 — hidden 해제로 상호작용 허용
    errorEl.hidden = true;
  } catch (err) {
    if (isCancelled()) return;
    // mermaid.render()는 문법 오류 시 Error 객체 또는 문자열을 throw할 수 있다.
    // err?.message || err 순서로 평가해 두 경우를 모두 커버한다.
    previewEl.innerHTML = "";
    mediaWrapEl.hidden = true;
    actionsEl.hidden = true;
    errorMsgEl.textContent = "Mermaid 문법 오류: " + (err?.message || err || "알 수 없는 오류");
    errorEl.hidden = false;
  }
}

// ── Mermaid 크게 보기 (라이트박스) ───────────────────────────────────────────

/**
 * 현재 렌더된 SVG를 전체화면 오버레이에서 표시한다.
 *
 * 이미지 블록의 openLightbox 와 동일한 접근성 패턴을 따른다.
 *   - role="dialog" + aria-modal="true" 로 스크린리더에 모달임을 알림
 *   - 열릴 때 닫기 버튼으로 포커스 이동 (WCAG 2.4.3)
 *   - ESC 키 및 배경 클릭으로 닫기
 *   - 포커스 트랩 (ARIA Authoring Practices Guide — Modal Dialog Pattern)
 *   - 닫힐 때 트리거 요소로 포커스 복원
 *
 * Ref: https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
 *
 * @param {HTMLElement} previewEl - 미리보기 컨테이너 (SVG 포함)
 */
function openMermaidLightbox(previewEl) {
  const svgEl = previewEl.querySelector("svg");
  if (!svgEl) return; // 렌더된 SVG가 없으면 라이트박스를 열지 않는다.

  // 닫힌 후 포커스를 복원할 트리거 요소를 미리 저장 (WCAG 2.4.3)
  const previousFocus = document.activeElement;

  // 이미지 라이트박스와 동일한 overlay/close 스타일 재사용
  const overlay = document.createElement("div");
  overlay.className = "image-lightbox-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "다이어그램 크게 보기");

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "image-lightbox-close";
  closeBtn.setAttribute("aria-label", "닫기");
  closeBtn.textContent = "✕";

  // SVG를 복제해 라이트박스 내 독립적인 뷰어에 삽입
  const svgWrap = document.createElement("div");
  svgWrap.className = "mermaid-lightbox-svg";
  const svgClone = svgEl.cloneNode(true);
  // 라이트박스에서도 Mermaid 고정 크기 속성 제거
  svgClone.removeAttribute("width");
  svgClone.removeAttribute("height");
  svgClone.style.maxWidth = "";
  svgWrap.appendChild(svgClone);

  overlay.append(closeBtn, svgWrap);
  document.body.append(overlay);
  document.body.classList.add("lightbox-open");

  // 열릴 때 포커스를 닫기 버튼으로 이동
  closeBtn.focus();

  // 라이트박스가 열린 후 DOM이 변경되지 않으므로 focusable 목록을 1회만 계산한다.
  // onKeyDown 내부에서 매 Tab 이벤트마다 querySelectorAll 을 실행하면 불필요한
  // DOM 순회 비용이 발생한다. (ARIA APG — Managing Focus: Focusable Elements)
  // Ref: https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
  const focusable = [
    ...overlay.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    ),
  ].filter((el) => !el.disabled);
  const focusFirst = focusable[0] ?? null;
  const focusLast = focusable[focusable.length - 1] ?? null;

  function close() {
    overlay.remove();
    document.body.classList.remove("lightbox-open");
    document.removeEventListener("keydown", onKeyDown);
    // 닫힌 후 트리거 요소로 포커스 복원 (WCAG 2.4.3 Focus Order)
    previousFocus?.focus();
  }

  // 포커스 트랩 — overlay 내 포커스 가능 요소를 Tab/Shift+Tab으로 순환
  // (ARIA Authoring Practices Guide — Modal Dialog Pattern)
  function onKeyDown(e) {
    if (e.key === "Escape") {
      close();
      return;
    }

    if (e.key === "Tab") {
      if (focusable.length === 0) { e.preventDefault(); return; }

      if (e.shiftKey) {
        if (document.activeElement === focusFirst) {
          e.preventDefault();
          focusLast.focus();
        }
      } else {
        if (document.activeElement === focusLast) {
          e.preventDefault();
          focusFirst.focus();
        }
      }
    }
  }

  closeBtn.addEventListener("click", close);
  // 오버레이 배경(SVG 외부) 클릭 시 닫기
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });
  document.addEventListener("keydown", onKeyDown);
}

// ── Mermaid SVG 다운로드 ──────────────────────────────────────────────────────

/**
 * 현재 렌더된 SVG를 .svg 파일로 다운로드한다.
 *
 * 파일명: mermaid-diagram-<타임스탬프>.svg
 * 다운로드 실패 시 버튼 텍스트로 오류 안내를 제공한 뒤 원래 상태로 복원한다.
 *
 * Ref:
 *   - XMLSerializer: https://developer.mozilla.org/en-US/docs/Web/API/XMLSerializer
 *   - URL.createObjectURL: https://developer.mozilla.org/en-US/docs/Web/API/URL/createObjectURL
 *
 * @param {HTMLElement} previewEl   - 미리보기 컨테이너 (SVG 포함)
 * @param {HTMLButtonElement} downloadBtn - 다운로드 버튼 (피드백 표시용)
 */
function downloadMermaidSvg(previewEl, downloadBtn) {
  const svgEl = previewEl.querySelector("svg");
  if (!svgEl) return;

  try {
    // SVG 직렬화 시 xmlns 선언이 누락되면 일부 뷰어에서 렌더링 불가.
    // cloneNode 후 속성을 추가해 원본 DOM에 영향을 주지 않는다.
    const svgCopy = svgEl.cloneNode(true);
    if (!svgCopy.getAttribute("xmlns")) {
      svgCopy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    }
    const svgStr = new XMLSerializer().serializeToString(svgCopy);
    const blob = new Blob([svgStr], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `mermaid-diagram-${Date.now()}.svg`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error("SVG 다운로드 실패:", err);
    // 다운로드 실패 시 버튼 텍스트로 사용자에게 안내
    const original = downloadBtn.textContent;
    downloadBtn.textContent = "다운로드 실패";
    setTimeout(() => { downloadBtn.textContent = original; }, 2000);
  }
}

// ── Block create ─────────────────────────────────────────────────────────────

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

  // ── Mermaid 전용 패널 요소 ────────────────────────────────────────────────
  const panelEl = node.querySelector(".mermaid-panel");
  const mediaWrapEl = node.querySelector(".mermaid-media-wrap");
  const previewEl = node.querySelector(".mermaid-preview");
  const actionsEl = node.querySelector(".mermaid-actions");
  const viewBtn = node.querySelector(".mermaid-view-btn");
  const downloadBtn = node.querySelector(".mermaid-download-btn");
  const errorEl = node.querySelector(".mermaid-error");
  const errorMsgEl = node.querySelector(".mermaid-error-msg");
  const retryBtn = node.querySelector(".mermaid-retry-btn");

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

  // ── renderMermaid opts 빌더 ───────────────────────────────────────────────
  // 매 호출마다 동일한 opts 구조를 생성하는 헬퍼로 코드 중복을 줄인다.
  function buildRenderOpts(gen) {
    return {
      previewEl,
      errorEl,
      errorMsgEl,
      mediaWrapEl,
      actionsEl,
      isCancelled: () => _renderGen !== gen,
    };
  }

  // ── Mermaid 모드 전환 ─────────────────────────────────────────────────────
  // isMermaid === true 일 때: 코드 에디터(소스 편집) + 미리보기 패널을 함께 표시한다.

  function applyMermaidMode(isMermaid) {
    node.classList.toggle("is-mermaid", isMermaid);
    panelEl.hidden = !isMermaid;

    if (isMermaid) {
      const gen = ++_renderGen;
      renderMermaid(block.id, plainCode, buildRenderOpts(gen));
    } else {
      ++_renderGen; // 진행 중인 렌더 취소
      // 패널 자체가 hidden 이므로 내부 상태는 재진입 시 renderMermaid 가 덮어쓴다.
      // 그러나 명시적으로 초기화해 DOM을 일관된 상태로 유지한다.
      previewEl.innerHTML = "";
      mediaWrapEl.hidden = true;
      actionsEl.hidden = true;
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
      renderMermaid(block.id, plainCode, buildRenderOpts(gen));
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

  // ── 복사 버튼 ────────────────────────────────────────────────────────────
  copyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(plainCode).then(() => {
      copyBtn.textContent = "복사됨";
      setTimeout(() => { copyBtn.textContent = "복사"; }, 1500);
    }).catch(console.error);
  });

  // ── 크게 보기 버튼 ───────────────────────────────────────────────────────
  viewBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    openMermaidLightbox(previewEl);
  });

  // ── 다운로드 버튼 ────────────────────────────────────────────────────────
  downloadBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    downloadMermaidSvg(previewEl, downloadBtn);
  });

  // ── 재시도 버튼 ──────────────────────────────────────────────────────────
  // 렌더 실패 시 표시되는 "재시도" 버튼 — 현재 소스 코드로 renderMermaid 를 재호출한다.
  retryBtn.addEventListener("click", () => {
    const gen = ++_renderGen;
    renderMermaid(block.id, plainCode, buildRenderOpts(gen));
  });

  return node;
}
