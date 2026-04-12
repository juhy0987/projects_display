// ── Block renderers ──────────────────────────────────────────────────────────

import { initFormattingToolbar } from "./formattingToolbar.js";
import { wrapBlock } from "./blockWrapper.js";

import { blockRegistry } from "./blocks/registry.js";
import * as textBlock from "./blocks/textBlock.js";
import * as imageBlock from "./blocks/imageBlock.js";
import * as toggleBlock from "./blocks/toggleBlock.js";
import * as codeBlock from "./blocks/codeBlock.js";
import * as quoteBlock from "./blocks/quoteBlock.js";
import * as calloutBlock from "./blocks/calloutBlock.js";
import * as dividerBlock from "./blocks/dividerBlock.js";
import * as pageBlock from "./blocks/pageBlock.js";

// 블록 모듈 등록
[textBlock, imageBlock, toggleBlock, codeBlock, quoteBlock, calloutBlock, dividerBlock, pageBlock]
  .forEach((mod) => blockRegistry.register(mod));

// Initialise singleton toolbar once
initFormattingToolbar();

/**
 * Callbacks set by main.js before rendering begins.
 * Block renderers use these to trigger navigation and block creation without
 * knowing about the active document or load function.
 */
export const callbacks = {
  navigateTo: null,         // (documentId) => void
  addBlock: null,           // (type, parentBlockId?) => Promise<void>
  addBlockAfter: null,      // (type, afterBlockId, parentBlockId?) => Promise<void>
  reloadDocument: null,     // () => void
  onPageBlockAdded: null,   // (childDoc) => void — update sidebar after page block creation
  reloadSidebar: null,      // () => Promise<void> — full sidebar refresh
  onTitleChanged: null,     // (documentId, newTitle) => void — propagate title change to page blocks
};

// ── Public render functions ───────────────────────────────────────────────────

export function renderBlock(block, parentBlockId = null) {
  const blockEl = blockRegistry.create(block, {
    callbacks,
    renderBlock,
    focusBlock,
  });
  return wrapBlock(blockEl, block, parentBlockId, {
    addBlockAfter: callbacks.addBlockAfter,
    reloadDocument: callbacks.reloadDocument,
    reloadSidebar: callbacks.reloadSidebar,
  });
}

// ── Block focus helper ───────────────────────────────────────────────────────

export function focusBlock(wrapperEl) {
  const blockEl = wrapperEl.querySelector(".notion-block");
  if (!blockEl) return;
  const target = blockEl.classList.contains("notion-text")
    ? blockEl
    : (blockEl.querySelector(".notion-caption, .toggle-title, .quote-text, .code-content, .callout-text") ?? blockEl);
  target.click();
}

// ── Document page renderer ───────────────────────────────────────────────────

export function renderDocument(documentPayload) {
  const pageTitle = document.getElementById("page-title");
  const pageSubtitle = document.getElementById("page-subtitle");
  const root = document.getElementById("block-root");

  pageTitle.textContent = documentPayload.title;
  pageSubtitle.textContent = documentPayload.subtitle || "";
  root.innerHTML = "";

  documentPayload.blocks.forEach((block) => {
    root.appendChild(renderBlock(block));
  });
}
