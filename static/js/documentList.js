// ── Document list helpers ────────────────────────────────────────────────────

import { apiUpdateTitle } from "./api.js";

export function closeAllMenus(list) {
  list.querySelectorAll('.document-menu').forEach((m) => (m.hidden = true));
}

export function setActiveItem(list, targetItem) {
  list.querySelectorAll('.document-item').forEach((btn) => btn.classList.remove('is-active'));
  const btn = targetItem.querySelector('.document-item');
  if (btn) btn.classList.add('is-active');
}

/**
 * Replace the document-item button inside listItem with an <input> for inline
 * title editing. Commits on Enter or blur; cancels (keeps original) on Escape.
 */
export function enterInlineEdit(listItem, docId, initialTitle, list, onSelect) {
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
export function addDocumentItem(list, docInfo, { onSelect, onDelete }) {
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
