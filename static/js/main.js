// ── App entry point ───────────────────────────────────────────────────────────

import {
  fetchDocuments,
  fetchDocument,
  apiCreateDocument,
  apiDeleteDocument,
  apiUpdateTitle,
  apiCreateBlock,
  apiMoveBlock,
} from "./api.js";
import { callbacks, renderBlock, renderDocument, focusBlock } from "./blockRenderers.js";
import { addDocumentItem, closeAllMenus, setActiveItem, enterInlineEdit } from "./documentList.js";
import { initSidebar } from "./sidebar.js";

async function initGallery() {
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
    if (btn) btn.textContent = newTitle;
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
    const parentItem = list.querySelector(`li[data-id="${childDoc.parent_id}"]`);
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
    if (activeDocId) loadDocument(activeDocId);
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
  };

  // ── Document loader ───────────────────────────────────────────────────────
  async function loadDocument(documentId, { focusBlockId = null } = {}) {
    activeDocId = documentId;

    callbacks.addBlockAfter = async (type, afterBlockId, parentBlockId = null) => {
      const newBlock = await apiCreateBlock(activeDocId, type, parentBlockId);
      const afterWrapper = document.querySelector(`[data-block-id="${afterBlockId}"]`);
      if (afterWrapper) {
        const newWrapper = renderBlock(newBlock, parentBlockId);
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

    const addBlock = async (type, parentBlockId = null) => {
      const newBlock = await apiCreateBlock(activeDocId, type, parentBlockId);
      const containerEl = parentBlockId
        ? document.querySelector(`[data-block-id="${parentBlockId}"] [data-block-children]`)
        : root;
      if (containerEl) {
        const newWrapper = renderBlock(newBlock, parentBlockId);
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
        await loadDocument(documentId, { focusBlockId: focusBlockId ?? newBlock.id });
        return;
      }

      renderDocument(payload);
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
