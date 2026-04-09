// ── Block renderers ──────────────────────────────────────────────────────────

import { apiPatchBlock, apiUploadImage } from "./api.js";
import { enableContentEditable } from "./editor.js";
import { openBlockPalette } from "./blockPalette.js";
import { wrapBlock } from "./blockWrapper.js";
import {
  initFormattingToolbar,
  sanitizeHtml,
  setEditingNode,
  clearEditingNode,
} from "./formattingToolbar.js";

// Initialise singleton toolbar once
initFormattingToolbar();

/**
 * Callbacks set by main.js before rendering begins.
 * Block renderers use these to trigger navigation and block creation without
 * knowing about the active document or load function.
 */
export const callbacks = {
  navigateTo: null,       // (documentId) => void
  addBlock: null,         // (type, parentBlockId?) => Promise<void>
  addBlockAfter: null,    // (type, afterBlockId, parentBlockId?) => Promise<void>
  reloadDocument: null,   // () => void
};

// ── Individual block creators ─────────────────────────────────────────────────

function createTextBlock(block) {
  const template = document.getElementById('text-block-template');
  const node = template.content.firstElementChild.cloneNode(true);

  // Render formatted HTML when available, fall back to plain text
  if (block.formatted_text) {
    node.innerHTML = sanitizeHtml(block.formatted_text);
  } else {
    node.textContent = block.text;
  }

  if (block.level) node.dataset.level = String(block.level);

  let originalHtml = node.innerHTML;
  let originalText = node.textContent;
  let currentLevel = block.level ?? null;
  let escaped = false;

  // ── Click: activate editing (but let link clicks open the URL) ──────────
  node.addEventListener('click', (e) => {
    // When not editing, a click on a link should navigate, not start editing
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
    node.classList.add('is-editing');
    setEditingNode(node);
    node.focus();
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(node);
    range.collapse(false);
    if (sel) { sel.removeAllRanges(); sel.addRange(range); }
  });

  // ── Blur: save and deactivate ────────────────────────────────────────────
  node.addEventListener('blur', () => {
    if (node.contentEditable !== 'true') return;
    node.contentEditable = 'false';
    node.classList.remove('is-editing');
    clearEditingNode();

    if (escaped) { escaped = false; return; }

    // Handle pasted "# Title" heading promotion form
    const raw = node.textContent;
    const headingMatch = raw.match(/^(#{1,3})\s+(\S.*)?$/);
    if (headingMatch) {
      const newLevel = headingMatch[1].length;
      const newText = (headingMatch[2] ?? '').trimEnd();
      node.textContent = newText;
      node.dataset.level = String(newLevel);
      const patch = {};
      if (newLevel !== currentLevel) patch.level = newLevel;
      if (newText !== originalText) patch.text = newText;
      patch.formatted_text = '';
      currentLevel = newLevel;
      originalText = newText;
      originalHtml = node.innerHTML;
      apiPatchBlock(block.id, patch).catch(console.error);
      return;
    }

    // Normal save: patch both text and formatted_text when changed
    const newText = node.textContent.trim();
    const newHtml = sanitizeHtml(node.innerHTML);
    const patch = {};
    if (newText !== originalText) patch.text = newText;
    if (newHtml !== sanitizeHtml(originalHtml)) patch.formatted_text = newHtml;
    if (Object.keys(patch).length) {
      originalText = newText;
      originalHtml = node.innerHTML;
      apiPatchBlock(block.id, patch).catch(console.error);
    }
  });

  // ── Keydown: formatting shortcuts + heading promotion + slash command ────
  // Capture phase: intercepts Enter/Space for heading promotion before bubble handlers
  node.addEventListener('keydown', (e) => {
    // Slash command: open palette when '/' is typed in an empty block
    if (e.key === '/' && node.contentEditable === 'true' && !node.textContent.trim()) {
      e.preventDefault();
      node.blur();
      openBlockPalette(node, null, null, callbacks.addBlock);
      return;
    }

    if (node.contentEditable !== 'true') return;

    // Escape: cancel editing and restore original content
    if (e.key === 'Escape') {
      e.preventDefault();
      escaped = true;
      node.innerHTML = originalHtml;
      node.contentEditable = 'false';
      node.classList.remove('is-editing');
      clearEditingNode();
      return;
    }

    // Enter (no shift): either new block or heading promotion
    if (e.key === 'Enter' && !e.shiftKey) {
      const raw = node.textContent;
      const exactPrefix = raw.match(/^(#{1,3})$/);
      if (exactPrefix) {
        // Heading promotion
        e.preventDefault();
        e.stopImmediatePropagation();
        const newLevel = exactPrefix[1].length;
        node.textContent = '';
        node.dataset.level = String(newLevel);
        const patch = { level: newLevel, text: '', formatted_text: '' };
        currentLevel = newLevel;
        originalText = '';
        originalHtml = '';
        apiPatchBlock(block.id, patch).catch(console.error);
        return;
      }
      e.preventDefault();
      node.blur();
      const parentBlockId =
        node.closest('.block-wrapper')?.dataset.parentBlockId || null;
      if (callbacks.addBlockAfter) {
        callbacks.addBlockAfter('text', block.id, parentBlockId).catch(console.error);
      }
      return;
    }

    // Space: heading promotion when content is exactly #, ##, or ###
    if (e.key === ' ') {
      const raw = node.textContent;
      const exactPrefix = raw.match(/^(#{1,3})$/);
      if (!exactPrefix) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      const newLevel = exactPrefix[1].length;
      node.textContent = '';
      node.dataset.level = String(newLevel);
      const patch = { level: newLevel, text: '', formatted_text: '' };
      currentLevel = newLevel;
      originalText = '';
      originalHtml = '';
      apiPatchBlock(block.id, patch).catch(console.error);
    }

    // Formatting keyboard shortcuts (Ctrl/Cmd + B / I / U)
    if (e.ctrlKey || e.metaKey) {
      if (e.key === 'b') { e.preventDefault(); document.execCommand('bold', false); }
      else if (e.key === 'i') { e.preventDefault(); document.execCommand('italic', false); }
      else if (e.key === 'u') { e.preventDefault(); document.execCommand('underline', false); }
    }
  }, { capture: true });

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

function createContainerBlock(block) {
  const template = document.getElementById('container-block-template');
  const node = template.content.firstElementChild.cloneNode(true);
  const titleNode = node.querySelector('.container-title');
  const childrenRoot = node.querySelector('.container-children');

  if (block.title) {
    titleNode.textContent = block.title;
    enableContentEditable(titleNode, block.id, 'title', node);
  } else {
    titleNode.remove();
  }

  if (block.layout === 'grid') {
    childrenRoot.classList.add('is-grid');
  }

  block.children.forEach((child) => {
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
  node.querySelector('.page-block-title').textContent = block.title || block.document_id;
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
    case 'container':
      blockEl = createContainerBlock(block);
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
  });
}

// ── Block focus helper ───────────────────────────────────────────────────────

export function focusBlock(wrapperEl) {
  const blockEl = wrapperEl.querySelector('.notion-block');
  if (!blockEl) return;
  const target = blockEl.classList.contains('notion-text')
    ? blockEl
    : (blockEl.querySelector('.notion-caption, .container-title') ?? blockEl);
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
