// ── Block wrapper (drag handle + more menu) ───────────────────────────────────

import { apiChangeBlockType, apiMoveBlock } from "./api.js";
import { BLOCK_PALETTE_ITEMS, openBlockPalette, showBlockDeleteConfirm } from "./blockPalette.js";

// ── Drag state ────────────────────────────────────────────────────────────────
let currentDragBlockId = null;
let currentDragParentBlockId = null;
let currentDropTarget = null;

/**
 * Wrap a block element with a drag handle and more-menu.
 * @param {HTMLElement} blockEl       - The rendered block element
 * @param {object}      block         - Block data (id, type, …)
 * @param {string|null} parentBlockId - Parent block id (null for top-level)
 * @param {object}      callbacks     - { addBlockAfter, reloadDocument }
 */
export function wrapBlock(blockEl, block, parentBlockId = null, { addBlockAfter, reloadDocument } = {}) {
  const wrapper = document.createElement('div');
  wrapper.className = 'block-wrapper';
  wrapper.dataset.blockId = block.id;
  wrapper.dataset.parentBlockId = parentBlockId ?? '';

  // ── Actions bar ──────────────────────────────────────────────────────────
  const actions = document.createElement('div');
  actions.className = 'block-actions';

  // Drag handle — also opens action dropdown on click
  const dragWrap = document.createElement('div');
  dragWrap.className = 'block-more-wrap';

  const dragHandle = document.createElement('button');
  dragHandle.type = 'button';
  dragHandle.className = 'block-drag-handle';
  dragHandle.setAttribute('aria-label', '이동 / 블록 액션');
  dragHandle.textContent = '⠿';

  const moreMenu = document.createElement('div');
  moreMenu.className = 'block-more-menu';
  moreMenu.hidden = true;

  // Type change section (only for non-page blocks)
  const isPageBlock = block.type === 'page';
  if (!isPageBlock) {
    const sectionLabel = document.createElement('div');
    sectionLabel.className = 'block-menu-section-label';
    sectionLabel.textContent = '타입 변경';
    moreMenu.appendChild(sectionLabel);

    BLOCK_PALETTE_ITEMS.forEach(({ type, label, icon }) => {
      const changeBtn = document.createElement('button');
      changeBtn.type = 'button';
      changeBtn.className = 'block-change-type-btn';
      if (type === block.type) changeBtn.classList.add('is-current');
      changeBtn.innerHTML = `<span class="block-menu-icon">${icon}</span>${label}`;
      changeBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        moreMenu.hidden = true;
        if (type === block.type) return;
        try {
          await apiChangeBlockType(block.id, type);
          if (reloadDocument) reloadDocument();
        } catch (err) {
          console.error('블록 타입 변경 실패:', err);
        }
      });
      moreMenu.appendChild(changeBtn);
    });

    const menuDivider = document.createElement('div');
    menuDivider.className = 'block-menu-divider';
    moreMenu.appendChild(menuDivider);
  }

  // Delete action
  const deleteBtn = document.createElement('button');
  deleteBtn.type = 'button';
  deleteBtn.className = 'block-delete-btn';
  deleteBtn.textContent = '삭제';
  moreMenu.appendChild(deleteBtn);

  dragWrap.appendChild(dragHandle);
  dragWrap.appendChild(moreMenu);

  // Insert below button
  const insertBtn = document.createElement('button');
  insertBtn.type = 'button';
  insertBtn.className = 'block-insert-btn';
  insertBtn.setAttribute('aria-label', '아래에 블록 추가');
  insertBtn.textContent = '+';

  actions.appendChild(insertBtn);
  actions.appendChild(dragWrap);
  wrapper.appendChild(actions);
  wrapper.appendChild(blockEl);

  // ── Drag handle click → action dropdown ──────────────────────────────────
  let dragDidStart = false;

  dragHandle.addEventListener('click', (e) => {
    e.stopPropagation();
    if (dragDidStart) {
      dragDidStart = false;
      return;
    }
    const wasHidden = moreMenu.hidden;
    document.querySelectorAll('.block-more-menu').forEach((m) => (m.hidden = true));
    moreMenu.hidden = !wasHidden;
  });

  // ── Insert below ─────────────────────────────────────────────────────────
  insertBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    document.querySelectorAll('.block-more-menu').forEach((m) => (m.hidden = true));
    openBlockPalette(wrapper, parentBlockId, async (type) => {
      if (addBlockAfter) await addBlockAfter(type, block.id, parentBlockId);
    });
  });

  // ── Delete with confirmation ──────────────────────────────────────────────
  deleteBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    moreMenu.hidden = true;
    showBlockDeleteConfirm(wrapper, block.id, reloadDocument);
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
    dragDidStart = true;
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

  // ── Drop target (blockEl only — action buttons excluded) ────────────────
  blockEl.addEventListener('dragover', (e) => {
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

  blockEl.addEventListener('dragleave', (e) => {
    if (!blockEl.contains(e.relatedTarget)) {
      wrapper.classList.remove('drop-above', 'drop-below');
    }
  });

  blockEl.addEventListener('drop', async (e) => {
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
