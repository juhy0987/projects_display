// ── Document list helpers ────────────────────────────────────────────────────

import { apiUpdateTitle } from "./api.js";

export function closeAllMenus(list) {
  list.querySelectorAll('.document-menu').forEach((m) => (m.hidden = true));
}

export function setActiveItem(list, targetItem) {
  list.querySelectorAll('.document-item').forEach((btn) => btn.classList.remove('is-active'));
  const btn = targetItem.querySelector(':scope > .document-row > .document-item');
  if (btn) btn.classList.add('is-active');
}

/**
 * Replace the document-item button inside listItem with an <input> for inline
 * title editing. Commits on Enter or blur; cancels (keeps original) on Escape.
 */
export function enterInlineEdit(listItem, docId, initialTitle, list, onSelect, onTitleSaved = null) {
  const existingBtn = listItem.querySelector(':scope > .document-row > .document-item');
  const menuBtn = listItem.querySelector(':scope > .document-row > .document-menu-btn');

  const input = document.createElement('input');
  input.type = 'text';
  input.setAttribute('size', '1');
  input.className = 'document-title-input';
  input.value = initialTitle;
  existingBtn.replaceWith(input);

  if (menuBtn) menuBtn.hidden = true;

  input.focus();
  input.select();

  let exited = false;

  function restoreButton(title) {
    if (exited) return null;
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
    return btn;
  }

  function saveTitle(newTitle) {
    const btn = restoreButton(newTitle);
    if (newTitle === initialTitle) return;
    apiUpdateTitle(docId, newTitle)
      .then(() => { if (onTitleSaved) onTitleSaved(docId, newTitle); })
      .catch((err) => {
        console.error(err);
        if (btn) btn.textContent = initialTitle;
      });
  }

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      saveTitle(input.value.trim() || '새 문서');
    } else if (e.key === 'Escape') {
      restoreButton(initialTitle);
    }
  });

  input.addEventListener('blur', () => {
    if (exited) return;
    saveTitle(input.value.trim() || '새 문서');
  });
}

/**
 * Build and append a single document list item (and its children recursively).
 *
 * @param {HTMLElement} list        - Parent <ul> to append into
 * @param {object}      docInfo     - Document data including .children[]
 * @param {object}      handlers    - { onSelect, onDelete }
 * @param {number}      depth       - Nesting depth (0 = root)
 * @returns {HTMLLIElement}
 */
export function addDocumentItem(list, docInfo, handlers, depth = 0) {
  const { onSelect, onDelete, onRename } = handlers;

  const item = document.createElement('li');
  item.dataset.id = docInfo.id;
  item.dataset.depth = String(depth);

  const row = document.createElement('div');
  row.className = 'document-row';
  row.style.paddingLeft = depth > 0 ? `${depth * 14}px` : '0';

  // ── Toggle button (> chevron) ─────────────────────────────────────────────
  const toggleBtn = document.createElement('button');
  toggleBtn.type = 'button';
  toggleBtn.className = 'document-toggle-btn';
  toggleBtn.setAttribute('aria-label', '하위 페이지 펼치기/접기');
  toggleBtn.setAttribute('aria-expanded', 'false');

  const hasChildren = !!(docInfo.children && docInfo.children.length > 0);
  if (hasChildren) {
    toggleBtn.classList.add('has-children');
  } else {
    // No children: keep button in DOM for layout stability but remove from
    // tab order and hide from assistive technology.
    toggleBtn.tabIndex = -1;
    toggleBtn.setAttribute('aria-hidden', 'true');
  }

  // ── Document select button ────────────────────────────────────────────────
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'document-item';
  btn.textContent = docInfo.title;
  btn.addEventListener('click', () => {
    closeAllMenus(list);
    setActiveItem(list, item);
    onSelect(docInfo.id);
  });

  // ── More (⋯) menu button ──────────────────────────────────────────────────
  const menuBtn = document.createElement('button');
  menuBtn.type = 'button';
  menuBtn.className = 'document-menu-btn';
  menuBtn.setAttribute('aria-label', '더보기');
  menuBtn.textContent = '⋯';

  const menu = document.createElement('div');
  menu.className = 'document-menu';
  menu.hidden = true;

  const renameBtn = document.createElement('button');
  renameBtn.type = 'button';
  renameBtn.className = 'document-menu-rename';
  renameBtn.textContent = '이름 바꾸기';
  renameBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    menu.hidden = true;
    const currentTitle = btn.textContent;
    enterInlineEdit(item, docInfo.id, currentTitle, list, (docId) => onSelect(docId), (docId, newTitle) => {
      if (onRename) onRename(docId, newTitle);
    });
  });

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

  menu.appendChild(renameBtn);
  menu.appendChild(deleteBtn);
  row.appendChild(toggleBtn);
  row.appendChild(btn);
  row.appendChild(menuBtn);
  row.appendChild(menu);
  item.appendChild(row);

  // ── Children list ─────────────────────────────────────────────────────────
  const childrenList = document.createElement('ul');
  childrenList.className = 'document-children';
  childrenList.hidden = true;
  item.appendChild(childrenList);

  // Render existing children (collapsed by default)
  if (docInfo.children && docInfo.children.length > 0) {
    docInfo.children.forEach((child) =>
      addDocumentItem(childrenList, child, handlers, depth + 1)
    );
  }

  // ── Toggle expand/collapse ────────────────────────────────────────────────
  toggleBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const willExpand = !toggleBtn.classList.contains('is-expanded');
    toggleBtn.classList.toggle('is-expanded', willExpand);
    toggleBtn.setAttribute('aria-expanded', String(willExpand));
    childrenList.hidden = !willExpand;
  });

  list.appendChild(item);
  return item;
}
