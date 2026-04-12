// ── Block palette (slash command / + button) ─────────────────────────────────

import { apiDeleteBlock } from "./api.js";

export const BLOCK_PALETTE_ITEMS = [
  { type: 'text', label: '텍스트', icon: 'T' },
  { type: 'image', label: '이미지', icon: '▣' },
  { type: 'toggle', label: '토글', icon: '▶' },
  { type: 'quote', label: '인용', icon: '"' },
  { type: 'code', label: '코드', icon: '⟨⟩' },
  { type: 'callout', label: '콜아웃', icon: '💡' },
  { type: 'divider', label: '구분선', icon: '—' },
  { type: 'page', label: '페이지', icon: '⊔' },
];

/**
 * Show the block type selection palette below anchorEl.
 * @param {HTMLElement} anchorEl - Element to position the palette after
 * @param {string|null} parentBlockId - Optional parent block id
 * @param {function|null} onSelect - Optional override: called with (type) instead of addBlock
 * @param {function|null} addBlock - Fallback when onSelect is null: addBlock(type, parentBlockId)
 */
export function openBlockPalette(anchorEl, parentBlockId = null, onSelect = null, addBlock = null) {
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
      if (onSelect) await onSelect(type);
      else if (addBlock) await addBlock(type, parentBlockId);
    });
    palette.appendChild(btn);
  });

  anchorEl.after(palette);

  // Deferred to avoid catching the event that triggered openBlockPalette.
  // Guard with isConnected: if close() was called before the timeout fires
  // (e.g. an item was clicked immediately), skip registration to prevent a dangling listener.
  setTimeout(() => {
    if (!palette.isConnected) return;
    function onOutside(e) {
      if (!palette.contains(e.target)) close();
    }
    document.addEventListener('click', onOutside, true);
    removeOutsideListener = () => document.removeEventListener('click', onOutside, true);
  }, 0);
}

// ── Block delete confirmation overlay ─────────────────────────────────────────

/**
 * @param {HTMLElement} wrapperEl
 * @param {string} blockId
 * @param {function} reloadDocument
 */
export function showBlockDeleteConfirm(wrapperEl, blockId, reloadDocument) {
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
      if (reloadDocument) await reloadDocument();
    } catch (err) {
      console.error('블록 삭제 실패:', err);
    }
  });

  // Guard with isConnected: if close() was called before the timeout fires
  // (e.g. confirm/cancel was clicked immediately), skip registration to prevent a dangling listener.
  setTimeout(() => {
    if (!dialog.isConnected) return;
    function onOutside(e) {
      if (!dialog.contains(e.target)) close();
    }
    document.addEventListener('click', onOutside, true);
    removeOutsideListener = () => document.removeEventListener('click', onOutside, true);
  }, 0);
}
