// ── Page picker modal ─────────────────────────────────────────────────────────
// Shown when the user selects the "페이지" block type.
// Resolves with { action: 'new' } or { action: 'reference', documentId } or null (dismissed).

import { fetchDocuments } from "./api.js";

/**
 * Flatten a nested document tree into a single array for display.
 * @param {Array} docs - Tree from fetchDocuments()
 * @param {number} depth
 * @returns {Array<{id, title, depth}>}
 */
function flattenDocs(docs, depth = 0) {
  const result = [];
  for (const doc of docs) {
    result.push({ id: doc.id, title: doc.title, depth });
    if (doc.children?.length) result.push(...flattenDocs(doc.children, depth + 1));
  }
  return result;
}

// Module-level reference to the active modal's close function.
// Ensures at most one modal is open at a time and that any previous Promise
// always resolves (preventing leaks when openPagePickerModal is called again
// before the previous modal is dismissed).
let _activeClose = null;

/**
 * Open the page picker modal anchored below anchorEl.
 * @param {HTMLElement} anchorEl
 * @param {string|null} excludeDocumentId - Current document to hide from the list
 * @returns {Promise<{action:'new'}|{action:'reference', documentId:string}|null>}
 */
export function openPagePickerModal(anchorEl, excludeDocumentId = null) {
  // Resolve and remove any previously open modal so its Promise never hangs.
  if (_activeClose) {
    _activeClose(null);
    _activeClose = null;
  }

  return new Promise((resolve) => {
    document.querySelectorAll('.page-picker-modal').forEach((m) => m.remove());

    const modal = document.createElement('div');
    modal.className = 'page-picker-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-label', '페이지 블록 추가');

    let removeOutsideListener = () => {};

    function close(result) {
      _activeClose = null;
      modal.remove();
      removeOutsideListener();
      resolve(result ?? null);
    }

    _activeClose = close;

    // ── 새 페이지 생성 button ─────────────────────────────────────────────────
    const newBtn = document.createElement('button');
    newBtn.type = 'button';
    newBtn.className = 'page-picker-option';
    newBtn.innerHTML = '<span class="page-picker-icon">＋</span>새 페이지 생성';
    newBtn.addEventListener('mousedown', (e) => e.preventDefault());
    newBtn.addEventListener('click', () => close({ action: 'new' }));
    modal.appendChild(newBtn);

    // ── 기존 페이지 참조 section ──────────────────────────────────────────────
    const divider = document.createElement('div');
    divider.className = 'page-picker-divider';
    modal.appendChild(divider);

    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.className = 'page-picker-search';
    searchInput.placeholder = '페이지 검색...';
    searchInput.setAttribute('aria-label', '페이지 검색');
    modal.appendChild(searchInput);

    const listEl = document.createElement('ul');
    listEl.className = 'page-picker-list';
    listEl.setAttribute('role', 'listbox');
    listEl.setAttribute('aria-label', '페이지 목록');
    modal.appendChild(listEl);

    let allDocs = [];

    function renderList(query) {
      const q = query.trim().toLowerCase();
      const filtered = q ? allDocs.filter((d) => d.title.toLowerCase().includes(q)) : allDocs;
      listEl.innerHTML = '';

      if (filtered.length === 0) {
        const empty = document.createElement('li');
        empty.className = 'page-picker-empty';
        empty.textContent = '검색 결과 없음';
        listEl.appendChild(empty);
        return;
      }

      for (const doc of filtered) {
        const item = document.createElement('li');
        item.className = 'page-picker-item';
        item.setAttribute('role', 'option');
        item.setAttribute('tabindex', '0');
        item.setAttribute('aria-label', doc.title || '제목 없음');

        const indent = document.createElement('span');
        indent.className = 'page-picker-indent';
        indent.style.paddingLeft = `${doc.depth * 12}px`;

        const icon = document.createElement('span');
        icon.className = 'page-picker-item-icon';
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = '⊔';

        const titleSpan = document.createElement('span');
        titleSpan.className = 'page-picker-item-title';
        titleSpan.textContent = doc.title || '제목 없음';

        item.appendChild(indent);
        item.appendChild(icon);
        item.appendChild(titleSpan);

        function select() {
          close({ action: 'reference', documentId: doc.id });
        }

        item.addEventListener('mousedown', (e) => e.preventDefault());
        item.addEventListener('click', select);
        item.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(); }
        });

        listEl.appendChild(item);
      }
    }

    // Fetch document list asynchronously while modal is visible
    fetchDocuments()
      .then((tree) => {
        allDocs = flattenDocs(tree).filter((d) => d.id !== excludeDocumentId);
        renderList(searchInput.value);
      })
      .catch(() => {
        const err = document.createElement('li');
        err.className = 'page-picker-empty';
        err.textContent = '문서 목록을 불러오지 못했습니다.';
        listEl.appendChild(err);
      });

    searchInput.addEventListener('input', () => renderList(searchInput.value));
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') close(null);
    });

    anchorEl.after(modal);
    searchInput.focus();

    setTimeout(() => {
      if (!modal.isConnected) return;
      function onOutside(e) {
        if (!modal.contains(e.target)) close(null);
      }
      document.addEventListener('click', onOutside, true);
      removeOutsideListener = () => document.removeEventListener('click', onOutside, true);
    }, 0);
  });
}
