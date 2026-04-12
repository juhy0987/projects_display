// ── Block renderers ──────────────────────────────────────────────────────────

import { apiPatchBlock, apiUploadImage, apiChangeBlockType } from "./api.js";
import { enableContentEditable } from "./editor.js";
import { openBlockPalette } from "./blockPalette.js";
import { wrapBlock } from "./blockWrapper.js";
import {
  initFormattingToolbar,
  sanitizeHtml,
  setEditingNode,
  clearEditingNode,
  isInsideToolbar,
} from "./formattingToolbar.js";

// Initialise singleton toolbar once
initFormattingToolbar();

/**
 * Callbacks set by main.js before rendering begins.
 * Block renderers use these to trigger navigation and block creation without
 * knowing about the active document or load function.
 */
export const callbacks = {
  navigateTo: null,         // (documentId) => void
  addBlock: null,           // (type, parentBlockId?) => Promise<void>
  addBlockAfter: null,      // (type, afterBlockId, parentBlockId?) => Promise<void>
  reloadDocument: null,     // () => void
  onPageBlockAdded: null,   // (childDoc) => void — update sidebar after page block creation
  reloadSidebar: null,      // () => Promise<void> — full sidebar refresh
  onTitleChanged: null,     // (documentId, newTitle) => void — propagate title change to page blocks
};

// ── Shared text-editing behaviour ────────────────────────────────────────────

/**
 * Attach text-block–style editing behaviour to any element.
 *
 * @param {HTMLElement} node      - Element to make editable
 * @param {string}      blockId   - Block ID for PATCH calls
 * @param {object}      opts
 * @param {string}   [opts.textField='text']           - Plain-text field name
 * @param {string}   [opts.htmlField='formatted_text'] - Rich-HTML field name
 * @param {string}   [opts.levelField='level']         - Heading level field name
 * @param {Function} [opts.onEnter]                    - Called on Enter instead of default (add block after)
 * @param {boolean}  [opts.enableSlash=true]           - Enable '/' block palette trigger
 * @param {boolean}  [opts.enableHeading=true]         - Enable '# ' heading promotion
 * @param {boolean}  [opts.enableTypeShortcuts=true]   - Enable '> ' → toggle conversion
 */
function makeTextEditable(node, blockId, {
  textField = 'text',
  htmlField = 'formatted_text',
  levelField = 'level',
  onEnter = null,
  enableSlash = true,
  enableHeading = true,
  enableTypeShortcuts = true,
} = {}) {
  let originalHtml = node.innerHTML;
  let originalText = node.textContent;
  let currentLevel = node.dataset.level ? Number(node.dataset.level) : null;
  let escaped = false;

  // is-editing은 가장 가까운 .notion-block에 적용 (toggle-title처럼 node 자체가
  // .notion-block이 아닌 경우에도 편집 상태 스타일이 일관되게 동작하도록)
  const editingTarget = node.closest('.notion-block') ?? node;

  // ── Click: activate editing (but let link clicks open the URL) ──────────
  node.addEventListener('click', (e) => {
    if (node.contentEditable !== 'true') {
      const anchor = e.target.closest('a[href]');
      if (anchor) {
        e.stopPropagation();
        window.open(anchor.href, '_blank', 'noopener,noreferrer');
        return;
      }
    }
    if (node.contentEditable === 'true') return;
    originalHtml = node.innerHTML;
    originalText = node.textContent;
    escaped = false;
    node.contentEditable = 'true';
    editingTarget.classList.add('is-editing');
    setEditingNode(node);
    node.focus();
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(node);
    range.collapse(false);
    if (sel) { sel.removeAllRanges(); sel.addRange(range); }
  });

  // ── Blur: save and deactivate ────────────────────────────────────────────
  node.addEventListener('blur', (e) => {
    if (isInsideToolbar(e.relatedTarget)) return;
    if (node.contentEditable !== 'true') return;
    node.contentEditable = 'false';
    editingTarget.classList.remove('is-editing');
    clearEditingNode();

    if (escaped) { escaped = false; return; }

    if (enableHeading) {
      const raw = node.textContent;
      const headingMatch = raw.match(/^(#{1,3})\s+(\S.*)?$/);
      if (headingMatch) {
        const newLevel = headingMatch[1].length;
        const newText = (headingMatch[2] ?? '').trimEnd();
        node.textContent = newText;
        node.dataset.level = String(newLevel);
        const patch = {};
        if (newLevel !== currentLevel) patch[levelField] = newLevel;
        if (newText !== originalText) patch[textField] = newText;
        patch[htmlField] = '';
        currentLevel = newLevel;
        originalText = newText;
        originalHtml = node.innerHTML;
        apiPatchBlock(blockId, patch).catch(console.error);
        return;
      }
    }

    const newText = node.textContent.trim();
    const newHtml = sanitizeHtml(node.innerHTML);
    const patch = {};
    if (newText !== originalText) patch[textField] = newText;
    if (newHtml !== sanitizeHtml(originalHtml)) patch[htmlField] = newHtml;
    if (Object.keys(patch).length) {
      originalText = newText;
      originalHtml = node.innerHTML;
      apiPatchBlock(blockId, patch).catch(console.error);
    }
  });

  // ── Keydown: formatting shortcuts + heading promotion + slash command ────
  // Capture phase: intercepts Enter/Space for heading promotion before bubble handlers
  node.addEventListener('keydown', (e) => {
    if (enableSlash && e.key === '/' && node.contentEditable === 'true' && !node.textContent.trim()) {
      e.preventDefault();
      node.blur();
      const slashParentId = node.closest('.block-wrapper')?.dataset.parentBlockId || null;
      openBlockPalette(node, slashParentId, null, callbacks.addBlock);
      return;
    }

    if (node.contentEditable !== 'true') return;

    if (e.key === 'Escape') {
      e.preventDefault();
      escaped = true;
      node.innerHTML = originalHtml;
      node.contentEditable = 'false';
      editingTarget.classList.remove('is-editing');
      clearEditingNode();
      return;
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      if (enableHeading) {
        const raw = node.textContent;
        const exactPrefix = raw.match(/^(#{1,3})$/);
        if (exactPrefix) {
          e.preventDefault();
          e.stopImmediatePropagation();
          const newLevel = exactPrefix[1].length;
          node.textContent = '';
          node.dataset.level = String(newLevel);
          const patch = { [levelField]: newLevel, [textField]: '', [htmlField]: '' };
          currentLevel = newLevel;
          originalText = '';
          originalHtml = '';
          apiPatchBlock(blockId, patch).catch(console.error);
          return;
        }
      }
      e.preventDefault();
      if (onEnter) {
        onEnter();
      } else {
        node.blur();
        const parentBlockId = node.closest('.block-wrapper')?.dataset.parentBlockId || null;
        if (callbacks.addBlockAfter) {
          callbacks.addBlockAfter('text', blockId, parentBlockId).catch(console.error);
        }
      }
      return;
    }

    if (e.key === ' ') {
      const raw = node.textContent;

      // '> ' → convert block to toggle
      if (enableTypeShortcuts && raw === '>') {
        e.preventDefault();
        e.stopImmediatePropagation();
        node.contentEditable = 'false';
        node.classList.remove('is-editing');
        clearEditingNode();
        apiChangeBlockType(blockId, 'toggle')
          .then(() => callbacks.reloadDocument?.())
          .catch(console.error);
        return;
      }

      // '# ' / '## ' / '### ' → heading promotion
      if (enableHeading) {
        const exactPrefix = raw.match(/^(#{1,3})$/);
        if (!exactPrefix) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        const newLevel = exactPrefix[1].length;
        node.textContent = '';
        node.dataset.level = String(newLevel);
        const patch = { [levelField]: newLevel, [textField]: '', [htmlField]: '' };
        currentLevel = newLevel;
        originalText = '';
        originalHtml = '';
        apiPatchBlock(blockId, patch).catch(console.error);
      }
    }

    if (e.ctrlKey || e.metaKey) {
      if (e.key === 'b') { e.preventDefault(); document.execCommand('bold', false); }
      else if (e.key === 'i') { e.preventDefault(); document.execCommand('italic', false); }
      else if (e.key === 'u') { e.preventDefault(); document.execCommand('underline', false); }
    }
  }, { capture: true });
}

// ── Individual block creators ─────────────────────────────────────────────────

function createTextBlock(block) {
  const template = document.getElementById('text-block-template');
  const node = template.content.firstElementChild.cloneNode(true);

  if (block.formatted_text) {
    node.innerHTML = sanitizeHtml(block.formatted_text);
  } else {
    node.textContent = block.text;
  }

  if (block.level) node.dataset.level = String(block.level);

  makeTextEditable(node, block.id);

  return node;
}

function createImageBlock(block) {
  const template = document.getElementById('image-block-template');
  const node = template.content.firstElementChild.cloneNode(true);
  const image = node.querySelector('.notion-image');
  const caption = node.querySelector('.notion-caption');

  let currentUrl = block.url || '';
  image.src = currentUrl;
  image.alt = block.caption || '';
  caption.textContent = block.caption || '';

  if (!block.caption) {
    caption.classList.add('is-empty');
  }

  // URL 없으면 플레이스홀더를 img 자리에 초기 표시
  const placeholder = document.createElement('div');
  placeholder.className = 'image-placeholder';
  placeholder.textContent = '이미지를 추가하려면 클릭하세요';
  if (!currentUrl) image.replaceWith(placeholder);

  function openEditPanel(anchorEl) {
    const panel = buildImageEditPanel({
      currentUrl,
      onCommit(newUrl) {
        if (newUrl && newUrl !== currentUrl) {
          currentUrl = newUrl;
          image.src = newUrl;
          apiPatchBlock(block.id, { url: newUrl }).catch(console.error);
        }
        // currentUrl이 있으면 img, 없으면 placeholder로 복귀
        panel.replaceWith(currentUrl ? image : placeholder);
        node.classList.remove('is-editing');
      },
      onCancel() {
        panel.replaceWith(currentUrl ? image : placeholder);
        node.classList.remove('is-editing');
      },
    });
    node.classList.add('is-editing');
    anchorEl.replaceWith(panel);
  }

  image.addEventListener('click', () => openEditPanel(image));
  placeholder.addEventListener('click', () => openEditPanel(placeholder));

  // 캡션 contenteditable 편집
  let originalCaption = block.caption || '';
  let captionEscaped = false;
  caption.contentEditable = 'true';

  caption.addEventListener('focus', () => {
    captionEscaped = false;
    node.classList.add('is-editing');
    caption.classList.remove('is-empty');
  });

  caption.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); caption.blur(); }
    if (e.key === 'Escape') {
      captionEscaped = true;
      caption.textContent = originalCaption;
      if (!originalCaption) caption.classList.add('is-empty');
      caption.blur();
    }
  });

  caption.addEventListener('blur', () => {
    node.classList.remove('is-editing');
    if (captionEscaped) { captionEscaped = false; return; }
    const newCaption = caption.textContent.trim();
    caption.textContent = newCaption;
    if (!newCaption) caption.classList.add('is-empty');
    if (newCaption !== originalCaption) {
      originalCaption = newCaption;
      image.alt = newCaption;
      apiPatchBlock(block.id, { caption: newCaption }).catch(console.error);
    }
  });

  return node;
}

function createToggleBlock(block) {
  const template = document.getElementById('toggle-block-template');
  const node = template.content.firstElementChild.cloneNode(true);
  const arrowBtn = node.querySelector('.toggle-arrow-btn');
  const titleEl = node.querySelector('.toggle-title');
  const childrenRoot = node.querySelector('.toggle-children');

  let isOpen = !!block.is_open;

  function applyOpen(open) {
    isOpen = open;
    childrenRoot.hidden = !open;
    arrowBtn.setAttribute('aria-expanded', String(open));
    arrowBtn.classList.toggle('is-open', open);
  }

  applyOpen(isOpen);

  // Render: identical to text block (formatted_text / text / level)
  if (block.formatted_text) {
    titleEl.innerHTML = sanitizeHtml(block.formatted_text);
  } else {
    titleEl.textContent = block.text || '';
  }
  if (block.level) titleEl.dataset.level = String(block.level);

  // ── Arrow button: only way to open/close ────────────────────────────────
  arrowBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    applyOpen(!isOpen);
    apiPatchBlock(block.id, { is_open: isOpen }).catch(console.error);
  });

  // ── Title editing: identical interface to text block ─────────────────────
  makeTextEditable(titleEl, block.id, {
    enableSlash: false,
    enableTypeShortcuts: false,
    onEnter: () => {
      titleEl.blur();
      // Open toggle if closed, then focus first child block
      if (!isOpen) {
        applyOpen(true);
        apiPatchBlock(block.id, { is_open: true }).catch(console.error);
      }
      const firstChild = childrenRoot.querySelector(':scope > .block-wrapper');
      if (firstChild) focusBlock(firstChild);
    },
  });

  block.children.forEach((child) => {
    childrenRoot.appendChild(renderBlock(child, block.id));
  });

  return node;
}

const CODE_LANGUAGES = [
  'plain', 'javascript', 'typescript', 'python', 'bash', 'html', 'css',
  'json', 'sql', 'java', 'go', 'rust', 'c', 'cpp',
];

// ── Caret offset helpers for contenteditable (plain-text character index) ────

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

function createCodeBlock(block) {
  const template = document.getElementById('code-block-template');
  const node = template.content.firstElementChild.cloneNode(true);
  const select = node.querySelector('.code-language-select');
  const codeEl = node.querySelector('.code-content');
  const copyBtn = node.querySelector('.code-copy-btn');

  let currentLanguage = block.language || 'plain';
  let plainCode = block.code || '';
  let originalCode = plainCode;

  CODE_LANGUAGES.forEach((lang) => {
    const opt = document.createElement('option');
    opt.value = lang;
    opt.textContent = lang;
    if (lang === currentLanguage) opt.selected = true;
    select.appendChild(opt);
  });

  // ── Syntax highlighting ──────────────────────────────────────────────────
  function applyHighlight(code) {
    if (!window.hljs || currentLanguage === 'plain') {
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

  // ── IME 조합 상태 추적 (한국어 등 조합형 입력 중 innerHTML 교체 방지) ────────
  let isComposing = false;
  codeEl.addEventListener('compositionstart', () => { isComposing = true; });
  codeEl.addEventListener('compositionend', () => {
    isComposing = false;
    // 조합 완료 후 한 번 하이라이팅 적용
    const offset = getCaretOffset(codeEl);
    plainCode = codeEl.textContent;
    applyHighlight(plainCode);
    setCaretOffset(codeEl, offset);
  });

  // ── Click → activate editing ─────────────────────────────────────────────
  codeEl.addEventListener('click', () => {
    if (codeEl.contentEditable === 'true') return;
    codeEl.contentEditable = 'true';
    node.classList.add('is-editing');
    codeEl.focus();
    // Place cursor at end
    const range = document.createRange();
    range.selectNodeContents(codeEl);
    range.collapse(false);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
  });

  // ── Input → live highlight with cursor preservation ──────────────────────
  codeEl.addEventListener('input', () => {
    if (isComposing) {
      // 조합 중에는 plainCode만 갱신하고 innerHTML 교체는 compositionend에서 수행
      plainCode = codeEl.textContent;
      return;
    }
    const offset = getCaretOffset(codeEl);
    plainCode = codeEl.textContent;
    applyHighlight(plainCode);
    setCaretOffset(codeEl, offset);
  });

  // ── Blur → save ──────────────────────────────────────────────────────────
  codeEl.addEventListener('blur', () => {
    if (codeEl.contentEditable !== 'true') return;
    codeEl.contentEditable = 'false';
    node.classList.remove('is-editing');
    if (plainCode !== originalCode) {
      originalCode = plainCode;
      apiPatchBlock(block.id, { code: plainCode }).catch(console.error);
    }
  });

  codeEl.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      document.execCommand('insertText', false, '  ');
    }
    if (e.key === 'Escape') codeEl.blur();
  });

  // ── Language change → re-highlight ──────────────────────────────────────
  select.addEventListener('change', () => {
    currentLanguage = select.value;
    apiPatchBlock(block.id, { language: currentLanguage }).catch(console.error);
    applyHighlight(plainCode);
  });

  copyBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(plainCode).then(() => {
      copyBtn.textContent = '복사됨';
      setTimeout(() => { copyBtn.textContent = '복사'; }, 1500);
    }).catch(console.error);
  });

  return node;
}

function createQuoteBlock(block) {
  const template = document.getElementById('quote-block-template');
  const node = template.content.firstElementChild.cloneNode(true);
  const textEl = node.querySelector('.quote-text');
  const childrenRoot = node.querySelector('.quote-children');

  textEl.textContent = block.text || '';
  enableContentEditable(textEl, block.id, 'text', node);

  block.children.forEach((child) => {
    childrenRoot.appendChild(renderBlock(child, block.id));
  });


  return node;
}

function createCalloutBlock(block) {
  const template = document.getElementById('callout-block-template');
  const node = template.content.firstElementChild.cloneNode(true);
  const emojiEl = node.querySelector('.callout-emoji');
  const textEl = node.querySelector('.callout-text');
  const childrenRoot = node.querySelector('.callout-children');

  node.dataset.color = block.color || 'yellow';
  emojiEl.textContent = block.emoji || '💡';
  textEl.textContent = block.text || '';
  enableContentEditable(textEl, block.id, 'text', node);

  (block.children || []).forEach((child) => {
    childrenRoot.appendChild(renderBlock(child, block.id));
  });

  return node;
}

function createDividerBlock() {
  const template = document.getElementById('divider-block-template');
  return template.content.firstElementChild.cloneNode(true);
}

function createPageBlock(block) {
  const template = document.getElementById('page-block-template');
  const node = template.content.firstElementChild.cloneNode(true);
  const titleEl = node.querySelector('.page-block-title');
  titleEl.textContent = block.title || block.document_id;
  titleEl.dataset.docId = block.document_id;
  node.addEventListener('click', () => {
    if (callbacks.navigateTo) callbacks.navigateTo(block.document_id);
  });
  return node;
}

// ── Image edit panel (URL / file upload) ─────────────────────────────────────

/**
 * URL 입력과 파일 업로드를 탭으로 전환할 수 있는 편집 패널을 반환합니다.
 * @param {{ currentUrl: string, onCommit: (url: string) => void, onCancel: () => void }} opts
 */
function buildImageEditPanel({ currentUrl, onCommit, onCancel }) {
  const panel = document.createElement('div');
  panel.className = 'image-edit-panel';

  // ── 탭 헤더 ──────────────────────────────────────────────────────────────
  const tabs = document.createElement('div');
  tabs.className = 'image-edit-tabs';

  const urlTab = document.createElement('button');
  urlTab.type = 'button';
  urlTab.className = 'image-edit-tab is-active';
  urlTab.textContent = 'URL';

  const fileTab = document.createElement('button');
  fileTab.type = 'button';
  fileTab.className = 'image-edit-tab';
  fileTab.textContent = '파일 업로드';

  tabs.append(urlTab, fileTab);

  // ── URL 패널 ─────────────────────────────────────────────────────────────
  const urlPane = document.createElement('div');
  urlPane.className = 'image-edit-pane';

  const urlInput = document.createElement('input');
  urlInput.type = 'text';
  urlInput.className = 'image-url-input';
  urlInput.value = currentUrl;
  urlInput.placeholder = 'https://...';

  const urlConfirm = document.createElement('button');
  urlConfirm.type = 'button';
  urlConfirm.className = 'image-edit-confirm';
  urlConfirm.textContent = '적용';

  urlPane.append(urlInput, urlConfirm);

  // ── 파일 업로드 패널 ──────────────────────────────────────────────────────
  const filePane = document.createElement('div');
  filePane.className = 'image-edit-pane is-hidden';

  const dropZone = document.createElement('div');
  dropZone.className = 'image-drop-zone';

  const dropLabel = document.createElement('span');
  dropLabel.className = 'image-drop-label';
  dropLabel.textContent = '이미지를 드래그하거나 클릭해서 선택';

  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = 'image/jpeg,image/png,image/gif,image/webp';
  fileInput.className = 'image-file-input';

  const spinner = document.createElement('span');
  spinner.className = 'image-upload-spinner is-hidden';
  spinner.textContent = '업로드 중...';

  dropZone.append(dropLabel, fileInput, spinner);
  filePane.append(dropZone);

  // ── 조립 ─────────────────────────────────────────────────────────────────
  panel.append(tabs, urlPane, filePane);

  // ── 탭 전환 ──────────────────────────────────────────────────────────────
  urlTab.addEventListener('click', () => {
    urlTab.classList.add('is-active');
    fileTab.classList.remove('is-active');
    urlPane.classList.remove('is-hidden');
    filePane.classList.add('is-hidden');
  });

  fileTab.addEventListener('click', () => {
    fileTab.classList.add('is-active');
    urlTab.classList.remove('is-active');
    filePane.classList.remove('is-hidden');
    urlPane.classList.add('is-hidden');
  });

  // ── URL 적용 ─────────────────────────────────────────────────────────────
  urlConfirm.addEventListener('click', () => onCommit(urlInput.value.trim()));

  urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); onCommit(urlInput.value.trim()); }
    if (e.key === 'Escape') onCancel();
  });

  // ── 파일 업로드 공통 처리 ────────────────────────────────────────────────
  async function handleFile(file) {
    if (!file) return;
    dropLabel.classList.add('is-hidden');
    spinner.classList.remove('is-hidden');
    spinner.textContent = '업로드 중...';
    try {
      const result = await apiUploadImage(file);
      onCommit(result.url);
    } catch (err) {
      console.error(err);
      // 실패 시 UI 복구해 재시도 가능하도록
      spinner.classList.add('is-hidden');
      dropLabel.classList.remove('is-hidden');
      dropLabel.textContent = '업로드 실패. 다시 시도하세요.';
    } finally {
      // 같은 파일 재선택 시에도 change 이벤트가 발생하도록 초기화
      fileInput.value = '';
    }
  }

  // fileInput이 position:absolute로 dropZone 전체를 덮으므로 별도 click 핸들러 불필요
  fileInput.addEventListener('change', () => handleFile(fileInput.files[0]));

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('is-drag-over');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('is-drag-over'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('is-drag-over');
    handleFile(e.dataTransfer.files[0]);
  });

  // 패널 외부 클릭 시 취소
  setTimeout(() => {
    document.addEventListener('click', function handler(e) {
      if (!panel.contains(e.target)) {
        document.removeEventListener('click', handler);
        if (panel.isConnected) onCancel();
      }
    });
  }, 0);

  return panel;
}

// ── Public render functions ───────────────────────────────────────────────────

export function renderBlock(block, parentBlockId = null) {
  let blockEl;
  switch (block.type) {
    case 'text':
      blockEl = createTextBlock(block);
      break;
    case 'image':
      blockEl = createImageBlock(block);
      break;
    case 'toggle':
      blockEl = createToggleBlock(block);
      break;
    case 'quote':
      blockEl = createQuoteBlock(block);
      break;
    case 'code':
      blockEl = createCodeBlock(block);
      break;
    case 'callout':
      blockEl = createCalloutBlock(block);
      break;
    case 'divider':
      blockEl = createDividerBlock();
      break;
    case 'page':
      blockEl = createPageBlock(block);
      break;
    default: {
      const unsupported = document.createElement('p');
      unsupported.className = 'notion-block unsupported-block';
      unsupported.textContent = `지원하지 않는 블록 타입: ${block.type}`;
      blockEl = unsupported;
    }
  }
  return wrapBlock(blockEl, block, parentBlockId, {
    addBlockAfter: callbacks.addBlockAfter,
    reloadDocument: callbacks.reloadDocument,
    reloadSidebar: callbacks.reloadSidebar,
  });
}

// ── Block focus helper ───────────────────────────────────────────────────────

export function focusBlock(wrapperEl) {
  const blockEl = wrapperEl.querySelector('.notion-block');
  if (!blockEl) return;
  const target = blockEl.classList.contains('notion-text')
    ? blockEl
    : (blockEl.querySelector('.notion-caption, .toggle-title, .quote-text, .code-content, .callout-text') ?? blockEl);
  target.click();
}

// ── Document page renderer ───────────────────────────────────────────────────

export function renderDocument(documentPayload) {
  const pageTitle = document.getElementById('page-title');
  const pageSubtitle = document.getElementById('page-subtitle');
  const root = document.getElementById('block-root');

  pageTitle.textContent = documentPayload.title;
  pageSubtitle.textContent = documentPayload.subtitle || '';
  root.innerHTML = '';

  documentPayload.blocks.forEach((block) => {
    root.appendChild(renderBlock(block));
  });
}
