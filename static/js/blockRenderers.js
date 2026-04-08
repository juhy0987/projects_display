// ── Block renderers ──────────────────────────────────────────────────────────

import { apiPatchBlock } from "./api.js";
import { enableContentEditable } from "./editor.js";
import { openBlockPalette } from "./blockPalette.js";
import { wrapBlock } from "./blockWrapper.js";

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
  node.textContent = block.text;

  // Apply heading level if present
  if (block.level) node.dataset.level = String(block.level);

  let originalText = node.textContent;
  let currentLevel = block.level ?? null;

  enableContentEditable(node, block.id, 'text', node, {
    onEnter: () => {
      const parentBlockId =
        node.closest('.block-wrapper')?.dataset.parentBlockId || null;
      if (callbacks.addBlockAfter) {
        callbacks.addBlockAfter('text', block.id, parentBlockId).catch(console.error);
      }
    },
  });

  // Registered in capture phase to preempt enableContentEditable's bubble-phase Enter handler,
  // preventing spurious block creation when heading promotion intercepts the keystroke.
  node.addEventListener('keydown', (e) => {
    // Slash command: open block palette when '/' is typed in an empty block
    if (e.key === '/' && node.contentEditable === 'true' && !node.textContent.trim()) {
      e.preventDefault();
      node.blur();
      openBlockPalette(node, null, null, callbacks.addBlock);
      return;
    }

    if (node.contentEditable !== 'true') return;
    if (e.key !== ' ' && !(e.key === 'Enter' && !e.shiftKey)) return;

    // Markdown heading promotion: only when content is exactly #, ##, or ###
    const raw = node.textContent;
    const exactPrefix = raw.match(/^(#{1,3})$/);
    if (!exactPrefix) {
      // Enter without heading prefix is handled by enableContentEditable's onEnter
      return;
    }

    e.preventDefault();
    e.stopImmediatePropagation();
    const newLevel = exactPrefix[1].length;
    node.textContent = '';
    node.dataset.level = String(newLevel);

    const patch = {};
    if (newLevel !== currentLevel) patch.level = newLevel;
    if ('' !== originalText) patch.text = '';
    if (Object.keys(patch).length) {
      currentLevel = newLevel;
      originalText = '';
      apiPatchBlock(block.id, patch).catch(console.error);
    }
  }, { capture: true });

  // On blur: also handle pasted "# Title" form (prefix + mandatory whitespace)
  node.addEventListener('blur', () => {
    if (node.contentEditable !== 'false') return; // enableContentEditable already committed
    const raw = node.textContent;
    const match = raw.match(/^(#{1,3})\s+(\S.*)?$/);
    if (!match) return;

    const newLevel = match[1].length;
    const newText = (match[2] ?? '').trimEnd();
    node.textContent = newText;
    node.dataset.level = String(newLevel);

    const patch = {};
    if (newLevel !== currentLevel) patch.level = newLevel;
    if (newText !== originalText) patch.text = newText;
    if (Object.keys(patch).length) {
      currentLevel = newLevel;
      originalText = newText;
      apiPatchBlock(block.id, patch).catch(console.error);
    }
  }, true); // capture: runs after enableContentEditable's blur

  return node;
}

function createImageBlock(block) {
  const template = document.getElementById('image-block-template');
  const node = template.content.firstElementChild.cloneNode(true);
  const image = node.querySelector('.notion-image');
  const caption = node.querySelector('.notion-caption');

  let currentUrl = block.url;
  image.src = currentUrl;
  image.alt = block.caption || '';
  caption.textContent = block.caption || '';

  if (!block.caption) {
    caption.classList.add('is-empty');
  }

  // 이미지 클릭 시 URL 인라인 편집
  image.addEventListener('click', () => {
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'image-url-input';
    input.value = currentUrl;
    input.placeholder = 'https://...';
    node.classList.add('is-editing');
    image.replaceWith(input);
    input.focus();
    input.select();

    let saved = false;

    function saveUrl() {
      if (saved) return;
      saved = true;
      const newUrl = input.value.trim();
      if (newUrl && newUrl !== currentUrl) {
        currentUrl = newUrl;
        image.src = newUrl;
        apiPatchBlock(block.id, { url: newUrl }).catch(console.error);
      }
      input.replaceWith(image);
      node.classList.remove('is-editing');
    }

    input.addEventListener('blur', saveUrl);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
      if (e.key === 'Escape') {
        saved = true;
        input.replaceWith(image);
        node.classList.remove('is-editing');
      }
    });
  });

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
