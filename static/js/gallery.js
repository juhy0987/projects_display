// ── API helpers ──────────────────────────────────────────────────────────────

async function fetchDocuments() {
  const res = await fetch('/api/documents');
  if (!res.ok) throw new Error('Failed to fetch documents');
  return res.json();
}

async function fetchDocument(documentId) {
  const res = await fetch(`/api/documents/${documentId}`);
  if (!res.ok) throw new Error('Failed to fetch document');
  return res.json();
}

async function apiCreateDocument() {
  const res = await fetch('/api/documents', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to create document');
  return res.json();
}

async function apiUpdateTitle(documentId, title) {
  const res = await fetch(`/api/documents/${documentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error('Failed to update title');
}

async function apiDeleteDocument(documentId) {
  const res = await fetch(`/api/documents/${documentId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete document');
}

async function apiPatchBlock(blockId, fields) {
  const res = await fetch(`/api/blocks/${blockId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  });
  if (!res.ok) throw new Error('Failed to update block');
}

async function apiCreateBlock(documentId, type, parentBlockId = null) {
  const res = await fetch(`/api/documents/${documentId}/blocks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, parent_block_id: parentBlockId }),
  });
  if (!res.ok) throw new Error('Failed to create block');
  return res.json();
}

async function apiDeleteBlock(blockId) {
  const res = await fetch(`/api/blocks/${blockId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete block');
}

async function apiMoveBlock(blockId, beforeBlockId) {
  const res = await fetch(`/api/blocks/${blockId}/position`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ before_block_id: beforeBlockId }),
  });
  if (!res.ok) throw new Error('Failed to move block');
}

// ── Inline editing helpers ────────────────────────────────────────────────────

/**
 * Make an element contenteditable on click.
 * Saves via PATCH on blur/Enter; restores on Escape.
 * @param {HTMLElement} el        - The element to make editable
 * @param {string}      blockId   - Block ID for the API call
 * @param {string}      field     - JSON field name to patch (e.g. "text", "title")
 * @param {HTMLElement} notionBlock - The .notion-block ancestor for is-editing class
 */
function enableContentEditable(el, blockId, field, notionBlock) {
  let originalText = '';
  let escaped = false;

  el.addEventListener('click', () => {
    if (el.contentEditable === 'true') return;
    originalText = el.textContent;
    escaped = false;
    el.contentEditable = 'true';
    notionBlock.classList.add('is-editing');
    el.focus();

    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    if (sel) {
      sel.removeAllRanges();
      sel.addRange(range);
    }
  });

  el.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      el.blur();
    } else if (e.key === 'Escape') {
      escaped = true;
      el.textContent = originalText;
      el.contentEditable = 'false';
      notionBlock.classList.remove('is-editing');
    }
  });

  el.addEventListener('blur', () => {
    if (el.contentEditable !== 'true') return;
    el.contentEditable = 'false';
    notionBlock.classList.remove('is-editing');
    if (escaped) { escaped = false; return; }
    const newText = el.textContent.trim();
    if (newText !== originalText) {
      apiPatchBlock(blockId, { [field]: newText }).catch(console.error);
    }
  });
}

// ── Module-level callbacks (set during initGallery) ──────────────────────────
// Allows block renderers to trigger navigation and block creation without
// knowing about the active document or load function.
let navigateTo = null;
let addBlock = null; // (type, parentBlockId?) => Promise<void>
let reloadDocument = null; // () => void — reload the active document

// ── Drag state ────────────────────────────────────────────────────────────────
let currentDragBlockId = null;
let currentDragParentBlockId = null;
let currentDropTarget = null;

// ── Block palette (slash command / + button) ─────────────────────────────────

const BLOCK_PALETTE_ITEMS = [
  { type: 'text', label: '텍스트', icon: 'T' },
  { type: 'image', label: '이미지', icon: '▣' },
  { type: 'container', label: '컨테이너', icon: '⊞' },
  { type: 'divider', label: '구분선', icon: '—' },
];

/**
 * Show the block type selection palette below anchorEl.
 * Calls addBlock(type) on selection.
 * @param {HTMLElement} anchorEl - Element to position the palette after
 * @param {string|null} parentBlockId - Optional parent block id
 */
function openBlockPalette(anchorEl, parentBlockId = null) {
  document.querySelectorAll('.block-palette').forEach((p) => p.remove());

  const palette = document.createElement('div');
  palette.className = 'block-palette';

  let removeOutsideListener = () => {};

  function close() {
    palette.remove();
    removeOutsideListener();
  }

  BLOCK_PALETTE_ITEMS.forEach(({ type, label, icon }) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'block-palette-item';
    btn.innerHTML = `<span class="block-palette-icon">${icon}</span>${label}`;
    // mousedown: prevent blur on the text block so the editing state is preserved
    // until we explicitly commit it; click: actually perform the selection
    btn.addEventListener('mousedown', (e) => e.preventDefault());
    btn.addEventListener('click', async () => {
      close();
      if (addBlock) await addBlock(type, parentBlockId);
    });
    palette.appendChild(btn);
  });

  anchorEl.after(palette);

  // Deferred to avoid catching the event that triggered openBlockPalette
  setTimeout(() => {
    function onOutside(e) {
      if (!palette.contains(e.target)) close();
    }
    document.addEventListener('click', onOutside, true);
    removeOutsideListener = () => document.removeEventListener('click', onOutside, true);
  }, 0);
}

/** + button rendered at the bottom of block-root. */
function createBlockAdder() {
  const adder = document.createElement('div');
  adder.className = 'block-adder';

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'block-adder-btn';
  btn.setAttribute('aria-label', '블록 추가');
  btn.textContent = '+';
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    openBlockPalette(adder);
  });

  adder.appendChild(btn);
  return adder;
}

// ── Block delete confirmation overlay ─────────────────────────────────────────

function showBlockDeleteConfirm(wrapperEl, blockId) {
  document.querySelectorAll('.block-delete-confirm').forEach((c) => c.remove());

  const dialog = document.createElement('div');
  dialog.className = 'block-delete-confirm';

  const text = document.createElement('span');
  text.className = 'block-delete-confirm-text';
  text.textContent = '정말 삭제할까요?';

  const btns = document.createElement('div');
  btns.className = 'block-delete-confirm-btns';

  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'block-delete-cancel-btn';
  cancelBtn.textContent = '취소';

  const okBtn = document.createElement('button');
  okBtn.type = 'button';
  okBtn.className = 'block-delete-ok-btn';
  okBtn.textContent = '삭제';

  btns.appendChild(cancelBtn);
  btns.appendChild(okBtn);
  dialog.appendChild(text);
  dialog.appendChild(btns);
  wrapperEl.appendChild(dialog);

  let removeOutsideListener = () => {};

  function close() {
    removeOutsideListener();
    dialog.remove();
  }

  cancelBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    close();
  });

  okBtn.addEventListener('click', async (e) => {
    e.stopPropagation();
    close();
    try {
      await apiDeleteBlock(blockId);
      if (reloadDocument) reloadDocument();
    } catch (err) {
      console.error('블록 삭제 실패:', err);
    }
  });

  setTimeout(() => {
    function onOutside(e) {
      if (!dialog.contains(e.target)) close();
    }
    document.addEventListener('click', onOutside, true);
    removeOutsideListener = () => document.removeEventListener('click', onOutside, true);
  }, 0);
}

// ── Block wrapper (drag handle + more menu) ───────────────────────────────────

/**
 * Wrap a block element with a drag handle and more-menu.
 * @param {HTMLElement} blockEl      - The rendered block element
 * @param {object}      block        - Block data (id, type, …)
 * @param {string|null} parentBlockId - Parent block id (null for top-level)
 */
function wrapBlock(blockEl, block, parentBlockId = null) {
  const wrapper = document.createElement('div');
  wrapper.className = 'block-wrapper';
  wrapper.dataset.blockId = block.id;
  wrapper.dataset.parentBlockId = parentBlockId ?? '';

  // ── Actions bar ──────────────────────────────────────────────────────────
  const actions = document.createElement('div');
  actions.className = 'block-actions';

  // Drag handle
  const dragHandle = document.createElement('button');
  dragHandle.type = 'button';
  dragHandle.className = 'block-drag-handle';
  dragHandle.setAttribute('aria-label', '드래그하여 이동');
  dragHandle.textContent = '⠿';

  // More button + menu
  const moreWrap = document.createElement('div');
  moreWrap.className = 'block-more-wrap';

  const moreBtn = document.createElement('button');
  moreBtn.type = 'button';
  moreBtn.className = 'block-more-btn';
  moreBtn.setAttribute('aria-label', '더보기');
  moreBtn.textContent = '⋯';

  const moreMenu = document.createElement('div');
  moreMenu.className = 'block-more-menu';
  moreMenu.hidden = true;

  const deleteBtn = document.createElement('button');
  deleteBtn.type = 'button';
  deleteBtn.className = 'block-delete-btn';
  deleteBtn.textContent = '삭제';

  moreMenu.appendChild(deleteBtn);
  moreWrap.appendChild(moreBtn);
  moreWrap.appendChild(moreMenu);
  actions.appendChild(dragHandle);
  actions.appendChild(moreWrap);
  wrapper.appendChild(actions);
  wrapper.appendChild(blockEl);

  // ── More menu toggle ──────────────────────────────────────────────────────
  moreBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const wasHidden = moreMenu.hidden;
    document.querySelectorAll('.block-more-menu').forEach((m) => (m.hidden = true));
    moreMenu.hidden = !wasHidden;
  });

  // ── Delete with confirmation ──────────────────────────────────────────────
  deleteBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    moreMenu.hidden = true;
    showBlockDeleteConfirm(wrapper, block.id);
  });

  // ── Drag and Drop ─────────────────────────────────────────────────────────
  // Only become draggable when the drag handle is pressed.
  // Reset on mouseup (document-level) to cover the case where the user
  // presses the handle but releases without starting a drag.
  dragHandle.addEventListener('mousedown', () => {
    wrapper.draggable = true;
    function onMouseUp() {
      if (!currentDragBlockId) wrapper.draggable = false;
      document.removeEventListener('mouseup', onMouseUp);
    }
    document.addEventListener('mouseup', onMouseUp);
  });

  wrapper.addEventListener('dragstart', (e) => {
    if (!wrapper.draggable) {
      e.preventDefault();
      return;
    }
    currentDragBlockId = block.id;
    currentDragParentBlockId = parentBlockId ?? '';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', block.id); // required for Firefox
    wrapper.classList.add('is-dragging');
  });

  wrapper.addEventListener('dragend', () => {
    wrapper.draggable = false;
    wrapper.classList.remove('is-dragging');
    currentDragBlockId = null;
    currentDragParentBlockId = null;
    if (currentDropTarget) {
      currentDropTarget.classList.remove('drop-above', 'drop-below');
      currentDropTarget = null;
    }
  });

  wrapper.addEventListener('dragover', (e) => {
    if (!currentDragBlockId) return;
    // Only allow drops from same-parent siblings
    if (currentDragParentBlockId !== (parentBlockId ?? '')) return;
    if (currentDragBlockId === block.id) return;

    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';

    if (currentDropTarget && currentDropTarget !== wrapper) {
      currentDropTarget.classList.remove('drop-above', 'drop-below');
    }
    currentDropTarget = wrapper;

    const rect = wrapper.getBoundingClientRect();
    const midY = rect.top + rect.height / 2;
    const isAbove = e.clientY < midY;
    wrapper.classList.toggle('drop-above', isAbove);
    wrapper.classList.toggle('drop-below', !isAbove);
  });

  wrapper.addEventListener('dragleave', (e) => {
    if (!wrapper.contains(e.relatedTarget)) {
      wrapper.classList.remove('drop-above', 'drop-below');
    }
  });

  wrapper.addEventListener('drop', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    wrapper.classList.remove('drop-above', 'drop-below');
    currentDropTarget = null;

    if (!currentDragBlockId || currentDragBlockId === block.id) return;
    if (currentDragParentBlockId !== (parentBlockId ?? '')) return;

    const rect = wrapper.getBoundingClientRect();
    const midY = rect.top + rect.height / 2;

    let beforeBlockId;
    if (e.clientY < midY) {
      beforeBlockId = block.id;
    } else {
      // Skip the dragged block itself if it happens to be the immediate next sibling
      let next = wrapper.nextElementSibling;
      while (next && next.dataset.blockId === currentDragBlockId) {
        next = next.nextElementSibling;
      }
      beforeBlockId = (next && next.classList.contains('block-wrapper'))
        ? next.dataset.blockId
        : null;
    }

    try {
      await apiMoveBlock(currentDragBlockId, beforeBlockId);
      if (reloadDocument) reloadDocument();
    } catch (err) {
      console.error('블록 이동 실패:', err);
    }
  });

  return wrapper;
}

// ── Block renderers ──────────────────────────────────────────────────────────

function createTextBlock(block) {
  const template = document.getElementById('text-block-template');
  const node = template.content.firstElementChild.cloneNode(true);
  node.textContent = block.text;

  // Apply heading level if present
  if (block.level) node.dataset.level = String(block.level);

  let originalText = node.textContent;
  let currentLevel = block.level ?? null;

  enableContentEditable(node, block.id, 'text', node);

  node.addEventListener('keydown', (e) => {
    // Slash command: open block palette when '/' is typed in an empty block
    if (e.key === '/' && node.contentEditable === 'true' && !node.textContent.trim()) {
      e.preventDefault();
      node.blur();
      openBlockPalette(node);
      return;
    }

    if (node.contentEditable !== 'true') return;
    if (e.key !== 'Enter' && e.key !== ' ') return;

    // Markdown heading promotion: only when content is exactly #, ##, or ###
    const raw = node.textContent;
    const exactPrefix = raw.match(/^(#{1,3})$/);
    if (!exactPrefix) {
      if (e.key === 'Enter') { e.preventDefault(); node.blur(); }
      return;
    }

    e.preventDefault();
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
  });

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
    if (navigateTo) navigateTo(block.document_id);
  });
  return node;
}

function renderBlock(block, parentBlockId = null) {
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
  return wrapBlock(blockEl, block, parentBlockId);
}

// ── Document page renderer ───────────────────────────────────────────────────

function renderDocument(documentPayload) {
  const pageTitle = document.getElementById('page-title');
  const pageSubtitle = document.getElementById('page-subtitle');
  const root = document.getElementById('block-root');

  pageTitle.textContent = documentPayload.title;
  pageSubtitle.textContent = documentPayload.subtitle || '';
  root.innerHTML = '';

  documentPayload.blocks.forEach((block) => {
    root.appendChild(renderBlock(block));
  });

  root.appendChild(createBlockAdder());
}

// ── Document list helpers ────────────────────────────────────────────────────

function closeAllMenus(list) {
  list.querySelectorAll('.document-menu').forEach((m) => (m.hidden = true));
}

function setActiveItem(list, targetItem) {
  list.querySelectorAll('.document-item').forEach((btn) => btn.classList.remove('is-active'));
  const btn = targetItem.querySelector('.document-item');
  if (btn) btn.classList.add('is-active');
}

/**
 * Replace the document-item button inside listItem with an <input> for inline
 * title editing. Commits on Enter or blur; cancels (keeps original) on Escape.
 */
function enterInlineEdit(listItem, docId, initialTitle, list, onSelect) {
  const existingBtn = listItem.querySelector('.document-item');
  const menuBtn = listItem.querySelector('.document-menu-btn');

  const input = document.createElement('input');
  input.type = 'text';
  input.setAttribute('size', '1'); // prevent browser default intrinsic width
  input.className = 'document-title-input';
  input.value = initialTitle;
  existingBtn.replaceWith(input);

  if (menuBtn) menuBtn.hidden = true;

  input.focus();
  input.select();

  let exited = false;

  function restoreButton(title) {
    if (exited) return;
    exited = true;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'document-item is-active';
    btn.textContent = title;
    btn.addEventListener('click', () => {
      closeAllMenus(list);
      setActiveItem(list, listItem);
      onSelect(docId);
    });
    input.replaceWith(btn);
    if (menuBtn) menuBtn.hidden = false;
  }

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const newTitle = input.value.trim() || '새 문서';
      apiUpdateTitle(docId, newTitle).catch(console.error);
      restoreButton(newTitle);
    } else if (e.key === 'Escape') {
      restoreButton(initialTitle); // cancel: no API call, restore original title
    }
  });

  input.addEventListener('blur', () => {
    const newTitle = input.value.trim() || '새 문서';
    if (!exited) apiUpdateTitle(docId, newTitle).catch(console.error);
    restoreButton(newTitle);
  });
}

/**
 * Build and append a single document list item.
 * Returns the <li> element.
 */
function addDocumentItem(list, docInfo, { onSelect, onDelete }) {
  const item = document.createElement('li');
  item.dataset.id = docInfo.id;

  const row = document.createElement('div');
  row.className = 'document-row';

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'document-item';
  btn.textContent = docInfo.title;
  btn.addEventListener('click', () => {
    closeAllMenus(list);
    setActiveItem(list, item);
    onSelect(docInfo.id);
  });

  const menuBtn = document.createElement('button');
  menuBtn.type = 'button';
  menuBtn.className = 'document-menu-btn';
  menuBtn.setAttribute('aria-label', '더보기');
  menuBtn.textContent = '⋯';

  const menu = document.createElement('div');
  menu.className = 'document-menu';
  menu.hidden = true;

  const deleteBtn = document.createElement('button');
  deleteBtn.type = 'button';
  deleteBtn.className = 'document-menu-delete';
  deleteBtn.textContent = '삭제';
  deleteBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    menu.hidden = true;
    onDelete(docInfo.id, item);
  });

  menuBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const wasHidden = menu.hidden;
    closeAllMenus(list);
    menu.hidden = !wasHidden;
  });

  menu.appendChild(deleteBtn);
  row.appendChild(btn);
  row.appendChild(menuBtn);
  row.appendChild(menu);
  item.appendChild(row);
  list.appendChild(item);

  return item;
}

// ── Main init ────────────────────────────────────────────────────────────────

async function initGallery() {
  const root = document.getElementById('block-root');
  const list = document.getElementById('document-list');
  const newDocBtn = document.getElementById('new-document-btn');

  let activeDocId = null;

  navigateTo = (documentId) => {
    const targetItem = list.querySelector(`li[data-id="${documentId}"]`);
    if (targetItem) {
      closeAllMenus(list);
      setActiveItem(list, targetItem);
    }
    loadDocument(documentId);
  };

  reloadDocument = () => {
    if (activeDocId) loadDocument(activeDocId);
  };

  async function loadDocument(documentId, { focusNewBlock = false } = {}) {
    activeDocId = documentId;
    addBlock = async (type, parentBlockId = null) => {
      await apiCreateBlock(activeDocId, type, parentBlockId);
      await loadDocument(activeDocId, { focusNewBlock: true });
    };
    try {
      const payload = await fetchDocument(documentId);
      renderDocument(payload);
      if (focusNewBlock) {
        const topWrappers = root.querySelectorAll(':scope > .block-wrapper');
        if (topWrappers.length > 0) {
          const lastWrapper = topWrappers[topWrappers.length - 1];
          const lastBlock = lastWrapper.querySelector('.notion-block');
          if (lastBlock) {
            const focusTarget = lastBlock.classList.contains('notion-text')
              ? lastBlock
              : (lastBlock.querySelector('.notion-caption, .container-title') ?? lastBlock);
            focusTarget.click();
          }
        }
      }
    } catch (err) {
      const p = document.createElement('p');
      p.className = 'error-state';
      p.textContent = `문서를 불러오지 못했습니다: ${err.message}`;
      root.replaceChildren(p);
    }
  }

  function showEmptyState() {
    activeDocId = null;
    document.getElementById('page-title').textContent = '';
    document.getElementById('page-subtitle').textContent = '';
    const p = document.createElement('p');
    p.className = 'empty-state';
    p.textContent = '문서가 없습니다.';
    root.replaceChildren(p);
  }

  const handlers = {
    onSelect(docId) {
      loadDocument(docId);
    },
    async onDelete(docId, item) {
      const wasActive = docId === activeDocId;
      try {
        await apiDeleteDocument(docId);
        item.remove();

        if (wasActive) {
          const firstItem = list.querySelector('li');
          if (firstItem) {
            setActiveItem(list, firstItem);
            loadDocument(firstItem.dataset.id);
          } else {
            showEmptyState();
          }
        }
      } catch (err) {
        console.error('문서 삭제 실패:', err);
      }
    },
  };

  // Close document menus and block more-menus when clicking outside
  document.addEventListener('click', () => {
    closeAllMenus(list);
    document.querySelectorAll('.block-more-menu').forEach((m) => (m.hidden = true));
  });

  // Load initial document list
  try {
    const documents = await fetchDocuments();

    if (documents.length === 0) {
      showEmptyState();
    } else {
      documents.forEach((doc) => addDocumentItem(list, doc, handlers));
      const firstItem = list.querySelector('li');
      setActiveItem(list, firstItem);
      await loadDocument(documents[0].id);
    }
  } catch (err) {
    const p = document.createElement('p');
    p.className = 'error-state';
    p.textContent = `문서를 불러오지 못했습니다: ${err.message}`;
    root.replaceChildren(p);
  }

  // + 새 문서 button
  newDocBtn.addEventListener('click', async () => {
    try {
      const newDoc = await apiCreateDocument();
      const item = addDocumentItem(list, newDoc, handlers);
      closeAllMenus(list);
      setActiveItem(list, item);
      // Show blank page immediately
      document.getElementById('page-title').textContent = newDoc.title;
      document.getElementById('page-subtitle').textContent = '';
      root.innerHTML = '';
      activeDocId = newDoc.id;
      // Enter inline title edit mode
      enterInlineEdit(item, newDoc.id, newDoc.title, list, (docId) => loadDocument(docId));
    } catch (err) {
      console.error('문서 생성 실패:', err);
    }
  });
}

window.addEventListener('DOMContentLoaded', initGallery);
