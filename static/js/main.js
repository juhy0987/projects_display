// ── App entry point ───────────────────────────────────────────────────────────

import {
  fetchDocuments,
  fetchDocument,
  apiCreateDocument,
  apiDeleteDocument,
  apiUpdateTitle,
  apiCreateBlock,
  apiMoveBlock,
  apiUpdateDbRowProperties,
} from "./api.js";
import { fetchAuthStatus, getAuthState, onAuthChange } from "./auth.js";
import { initLoginUI } from "./loginModal.js";
import { openPagePickerModal } from "./pagePickerModal.js";
import { callbacks, renderBlock, renderDocument, focusBlock } from "./blockRenderers.js";
import { addDocumentItem, closeAllMenus, setActiveItem, enterInlineEdit } from "./documentList.js";
import { initSidebar } from "./sidebar.js";
import { openNotionImportModal } from "./notionImportModal.js";

async function initGallery() {
  // 인증 상태 확인 및 로그인 UI 초기화
  await fetchAuthStatus();
  initLoginUI();

  // Viewer 모드: 미인증 시 body에 viewer-mode 클래스를 부여하여
  // CSS로 쓰기 관련 UI를 일괄 숨긴다.
  function applyViewerMode(state) {
    document.body.classList.toggle("viewer-mode", !state.authenticated);
  }
  applyViewerMode(getAuthState());
  onAuthChange(applyViewerMode);

  const root = document.getElementById('block-root');
  const list = document.getElementById('document-list');
  const newDocBtn = document.getElementById('new-document-btn');

  let activeDocId = null;

  // ── Header title inline editing ───────────────────────────────────────────
  const pageTitle = document.getElementById('page-title');
  let titleEscaped = false;
  let titleOriginal = '';

  pageTitle.addEventListener('click', () => {
    if (pageTitle.contentEditable === 'true' || !activeDocId) return;
    if (!getAuthState().authenticated) return;
    titleOriginal = pageTitle.textContent;
    titleEscaped = false;
    pageTitle.contentEditable = 'true';
    pageTitle.classList.add('is-editing');
    pageTitle.focus();
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(pageTitle);
    range.collapse(false);
    if (sel) { sel.removeAllRanges(); sel.addRange(range); }
  });

  pageTitle.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); pageTitle.blur(); }
    if (e.key === 'Escape') {
      titleEscaped = true;
      pageTitle.textContent = titleOriginal;
      pageTitle.contentEditable = 'false';
      pageTitle.classList.remove('is-editing');
    }
  });

  pageTitle.addEventListener('blur', () => {
    if (pageTitle.contentEditable !== 'true') return;
    pageTitle.contentEditable = 'false';
    pageTitle.classList.remove('is-editing');
    if (titleEscaped) { titleEscaped = false; return; }

    const newTitle = pageTitle.textContent.trim() || '새 문서';
    pageTitle.textContent = newTitle;

    if (newTitle !== titleOriginal && activeDocId) {
      const docId = activeDocId;
      apiUpdateTitle(docId, newTitle)
        .then(() => {
          if (callbacks.onTitleChanged) callbacks.onTitleChanged(docId, newTitle);
        })
        .catch((err) => {
          console.error(err);
          pageTitle.textContent = titleOriginal;
        });
    }
  });

  /** Update the sidebar button text for a given document id. */
  function updateSidebarTitle(docId, newTitle) {
    const item = list.querySelector(`li[data-id="${docId}"]`);
    if (!item) return;
    const btn = item.querySelector(':scope > .document-row > .document-item');
    if (!btn) return;
    const titleSpan = btn.querySelector('.document-item-title');
    if (titleSpan) titleSpan.textContent = newTitle;
    else btn.textContent = newTitle;
  }

  // ── Sidebar helpers ───────────────────────────────────────────────────────
  /**
   * Full sidebar re-render: re-fetches document tree and rebuilds the list.
   * Preserves active highlight for the currently open document.
   */
  async function reloadSidebar() {
    const docs = await fetchDocuments();
    list.innerHTML = '';
    docs.forEach((doc) => addDocumentItem(list, doc, handlers, 0));
    if (activeDocId) {
      const activeItem = list.querySelector(`li[data-id="${activeDocId}"]`);
      if (activeItem) setActiveItem(list, activeItem);
    }
  }

  /**
   * Add a newly created child document to the sidebar under its parent item
   * without a full reload. The parent's toggle is expanded automatically.
   */
  function addChildToSidebar(childDoc) {
    const sidebarParentId = childDoc.parent_sidebar_id ?? childDoc.parent_id;
    const parentItem = list.querySelector(`li[data-id="${sidebarParentId}"]`);
    if (!parentItem) return;

    const parentDepth = parseInt(parentItem.dataset.depth ?? '0', 10);
    const childrenList = parentItem.querySelector(':scope > .document-children');
    const toggleBtn = parentItem.querySelector(':scope > .document-row > .document-toggle-btn');

    if (!childrenList || !toggleBtn) return;

    toggleBtn.classList.add('has-children', 'is-expanded');
    toggleBtn.setAttribute('aria-expanded', 'true');
    // Restore focusability — button was aria-hidden / tabIndex=-1 when childless
    toggleBtn.removeAttribute('aria-hidden');
    toggleBtn.tabIndex = 0;
    childrenList.hidden = false;

    addDocumentItem(childrenList, childDoc, handlers, parentDepth + 1);
  }

  // ── Wire up renderer callbacks ────────────────────────────────────────────
  callbacks.navigateTo = (documentId) => {
    const targetItem = list.querySelector(`li[data-id="${documentId}"]`);
    if (targetItem) {
      closeAllMenus(list);
      setActiveItem(list, targetItem);
    }
    loadDocument(documentId);
  };

  callbacks.reloadDocument = () => {
    if (activeDocId) loadDocument(activeDocId, { pushHistory: false, resetScroll: false });
  };

  callbacks.reloadSidebar = reloadSidebar;

  callbacks.onPageBlockAdded = (childDoc) => {
    addChildToSidebar(childDoc);
  };

  callbacks.onTitleChanged = (documentId, newTitle) => {
    updateSidebarTitle(documentId, newTitle);
    // If the changed document is currently open, update the header
    if (documentId === activeDocId) {
      pageTitle.textContent = newTitle;
    }
    // Update any visible page blocks that reference this document
    document.querySelectorAll(`.page-block-title[data-doc-id="${documentId}"]`).forEach((el) => {
      el.textContent = newTitle;
    });
    // Update db row title cells that reference this document
    document.querySelectorAll(`.db-row[data-doc-id="${documentId}"] .db-row-title`).forEach((el) => {
      el.textContent = newTitle;
    });
  };

  callbacks.onDbTitleChanged = (dbBlockId, newTitle) => {
    updateSidebarTitle(`db:${dbBlockId}`, newTitle);
  };

  // ── Document loader ───────────────────────────────────────────────────────
  async function loadDocument(documentId, { focusBlockId = null, pushHistory = true, resetScroll = true } = {}) {
    activeDocId = documentId;

    /**
     * Resolve page block creation parameters using the picker modal.
     * Returns { targetDocumentId } where null means "create new page".
     * Returns null when the user dismisses the modal without selecting.
     * @param {HTMLElement} anchorEl
     */
    async function pickPageTarget(anchorEl) {
      const choice = await openPagePickerModal(anchorEl, activeDocId);
      if (!choice) return null;
      return { targetDocumentId: choice.action === 'reference' ? choice.documentId : null };
    }

    callbacks.addBlockAfter = async (type, afterBlockId, parentBlockId = null) => {
      let targetDocumentId = null;
      if (type === 'page') {
        const afterWrapper = document.querySelector(`[data-block-id="${afterBlockId}"]`);
        const anchorEl = afterWrapper ?? root;
        const pick = await pickPageTarget(anchorEl);
        if (pick === null) return;
        targetDocumentId = pick.targetDocumentId;
      }

      const newBlock = await apiCreateBlock(activeDocId, type, parentBlockId, targetDocumentId);
      const afterWrapper = document.querySelector(`[data-block-id="${afterBlockId}"]`);
      if (afterWrapper) {
        const newWrapper = renderBlock(newBlock, parentBlockId, { isNew: true });
        afterWrapper.after(newWrapper);
        const nextWrapper = newWrapper.nextElementSibling;
        if (nextWrapper?.dataset?.blockId) {
          await apiMoveBlock(newBlock.id, nextWrapper.dataset.blockId);
        }
        // For container blocks with an auto-created child, focus that child
        const firstChildWrapper = newWrapper.querySelector('[data-block-children] > .block-wrapper');
        focusBlock(firstChildWrapper ?? newWrapper);
      }
      if (newBlock.child_document && callbacks.onPageBlockAdded) {
        callbacks.onPageBlockAdded(newBlock.child_document);
      }
    };

    // db_row 추가: database 블록 id를 parent_block_id로 전달
    callbacks.addDbRow = async (dbBlockId) => {
      const newBlock = await apiCreateBlock(activeDocId, 'db_row', dbBlockId);
      if (newBlock.child_document && callbacks.onPageBlockAdded) {
        callbacks.onPageBlockAdded(newBlock.child_document);
      }
      if (callbacks.reloadDocument) callbacks.reloadDocument();
    };

    const addBlock = async (type, parentBlockId = null) => {
      let targetDocumentId = null;
      if (type === 'page') {
        const containerEl = parentBlockId
          ? document.querySelector(`[data-block-id="${parentBlockId}"] [data-block-children]`)
          : root;
        const anchorEl = containerEl?.lastElementChild ?? root;
        const pick = await pickPageTarget(anchorEl);
        if (pick === null) return;
        targetDocumentId = pick.targetDocumentId;
      }

      const newBlock = await apiCreateBlock(activeDocId, type, parentBlockId, targetDocumentId);
      const containerEl = parentBlockId
        ? document.querySelector(`[data-block-id="${parentBlockId}"] [data-block-children]`)
        : root;
      if (containerEl) {
        const newWrapper = renderBlock(newBlock, parentBlockId, { isNew: true });
        containerEl.appendChild(newWrapper);
        // For container blocks with an auto-created child, focus that child
        const firstChildWrapper = newWrapper.querySelector('[data-block-children] > .block-wrapper');
        focusBlock(firstChildWrapper ?? newWrapper);
      }
      if (newBlock.child_document && callbacks.onPageBlockAdded) {
        callbacks.onPageBlockAdded(newBlock.child_document);
      }
    };
    callbacks.addBlock = addBlock;

    try {
      const payload = await fetchDocument(documentId);

      const rootBlocks = payload.blocks;
      const lastBlock = rootBlocks[rootBlocks.length - 1];
      if (!lastBlock || lastBlock.type !== 'text') {
        const newBlock = await apiCreateBlock(activeDocId, 'text');
        await loadDocument(documentId, { focusBlockId: focusBlockId ?? newBlock.id, pushHistory, resetScroll });
        return;
      }

      renderDocument(payload);
      // 페이지 전환 시 본문 최상단에서 시작 (#33) — 네비게이션 경로에서만 리셋
      if (resetScroll) window.scrollTo(0, 0);
      if (pushHistory) {
        const state = { docId: documentId };
        history.state?.docId === undefined
          ? history.replaceState(state, '')
          : history.pushState(state, '');
      }
      renderDbProperties(payload.db_context);
      if (focusBlockId) {
        const targetWrapper = root.querySelector(`[data-block-id="${focusBlockId}"]`);
        const targetBlock = targetWrapper?.querySelector('.notion-block');
        if (targetBlock) {
          const focusTarget = targetBlock.classList.contains('notion-text')
            ? targetBlock
            : (targetBlock.querySelector('.notion-caption, .toggle-title, .quote-text, .callout-text, .code-content') ?? targetBlock);
          focusTarget.click();
        }
      }
    } catch (err) {
      const p = document.createElement('p');
      p.className = 'error-state';
      p.textContent = `문서를 불러오지 못했습니다: ${err.message}`;
      root.replaceChildren(p);
    }
  }

  // ── DB row 속성 패널 ──────────────────────────────────────────────────────
  /**
   * db_context가 있을 때 타이틀 아래에 속성 패널을 렌더링한다.
   * @param {object|null} ctx - DbContext | null
   */
  function renderDbProperties(ctx) {
    const panel = document.getElementById('page-properties');
    panel.innerHTML = '';

    if (!ctx || !ctx.columns || ctx.columns.length === 0) {
      panel.hidden = true;
      return;
    }

    panel.hidden = false;

    ctx.columns.forEach((col) => {
      const row = document.createElement('div');
      row.className = 'db-prop-row';

      const label = document.createElement('span');
      label.className = 'db-prop-label';
      label.textContent = col.name;
      row.appendChild(label);

      const valueWrap = document.createElement('div');
      valueWrap.className = 'db-prop-value';

      if (col.type === 'checkbox') {
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'db-prop-checkbox';
        cb.checked = ctx.properties[col.id] === true || ctx.properties[col.id] === 'true';
        cb.addEventListener('change', async () => {
          ctx.properties[col.id] = cb.checked;
          await _saveDbProperties(ctx);
          _syncDbCellInParent(ctx.block_id, col.id, cb.checked);
        });
        valueWrap.appendChild(cb);
      } else {
        const input = document.createElement('input');
        input.type = col.type === 'number' ? 'number' : 'text';
        input.className = 'db-prop-input';
        input.value = ctx.properties[col.id] ?? '';
        input.placeholder = col.type === 'number' ? '0' : '값 입력...';

        let original = input.value;
        input.addEventListener('focus', () => { original = input.value; });
        input.addEventListener('blur', async () => {
          if (input.value === original) return;
          ctx.properties[col.id] = input.value;
          await _saveDbProperties(ctx);
          // database 블록이 열려 있는 경우 셀도 갱신
          _syncDbCellInParent(ctx.block_id, col.id, input.value);
        });
        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
          if (e.key === 'Escape') { input.value = original; input.blur(); }
        });
        valueWrap.appendChild(input);
      }

      row.appendChild(valueWrap);
      panel.appendChild(row);
    });
  }

  async function _saveDbProperties(ctx) {
    try {
      await apiUpdateDbRowProperties(ctx.block_id, ctx.properties);
    } catch (err) {
      console.error('속성 저장 실패:', err);
    }
  }

  function _syncDbCellInParent(rowBlockId, colId, newValue) {
    const cell = document.querySelector(
      `.db-row[data-row-block-id="${rowBlockId}"] [data-col-id="${colId}"]`
    );
    if (!cell) return;
    const textInput = cell.querySelector('.db-cell-input');
    if (textInput) { textInput.value = newValue; return; }
    const checkbox = cell.querySelector('.db-cell-checkbox');
    if (checkbox) checkbox.checked = newValue === true || newValue === 'true';
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

  // ── Shared document action handlers ──────────────────────────────────────
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
    onRename(docId, newTitle) {
      if (callbacks.onTitleChanged) callbacks.onTitleChanged(docId, newTitle);
    },
  };

  // ── Sidebar ───────────────────────────────────────────────────────────────
  initSidebar(
    document.getElementById('sidebar-tab'),
    document.getElementById('sidebar-panel'),
  );

  // ── 브라우저 뒤로/앞으로: 히스토리 상태에서 문서 복원 (#33) ───────────────
  window.addEventListener('popstate', (e) => {
    const docId = e.state?.docId;
    if (!docId) return;
    const targetItem = list.querySelector(`li[data-id="${docId}"]`);
    if (targetItem) {
      closeAllMenus(list);
      setActiveItem(list, targetItem);
    }
    loadDocument(docId, { pushHistory: false, resetScroll: true });
  });

  document.addEventListener('click', () => {
    closeAllMenus(list);
    document.querySelectorAll('.block-more-menu').forEach((m) => (m.hidden = true));
  });

  // ── Load initial document tree ────────────────────────────────────────────
  try {
    const documents = await fetchDocuments();

    if (documents.length === 0) {
      showEmptyState();
    } else {
      documents.forEach((doc) => addDocumentItem(list, doc, handlers, 0));
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

  // ── Notion Import button ─────────────────────────────────────────────────
  const importBtn = document.getElementById('notion-import-btn');
  if (importBtn) {
    importBtn.addEventListener('click', () => {
      openNotionImportModal(async (docId) => {
        await reloadSidebar();
        loadDocument(docId);
      });
    });
  }

  // ── + 새 문서 button ──────────────────────────────────────────────────────
  newDocBtn.addEventListener('click', async () => {
    try {
      const newDoc = await apiCreateDocument();
      const item = addDocumentItem(list, newDoc, handlers, 0);
      closeAllMenus(list);
      setActiveItem(list, item);
      document.getElementById('page-title').textContent = newDoc.title;
      document.getElementById('page-subtitle').textContent = '';
      root.innerHTML = '';
      activeDocId = newDoc.id;
      enterInlineEdit(item, newDoc.id, newDoc.title, list, (docId) => loadDocument(docId), (docId, newTitle) => {
        if (callbacks.onTitleChanged) callbacks.onTitleChanged(docId, newTitle);
      });
    } catch (err) {
      console.error('문서 생성 실패:', err);
    }
  });
}

window.addEventListener('DOMContentLoaded', initGallery);
