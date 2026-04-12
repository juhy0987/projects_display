// ── Image Block ───────────────────────────────────────────────────────────────

import { apiPatchBlock, apiUploadImage } from "../api.js";

export const type = "image";

/**
 * @param {object} block
 * @returns {HTMLElement}
 */
export function create(block) {
  const template = document.getElementById("image-block-template");
  const node = template.content.firstElementChild.cloneNode(true);
  const image = node.querySelector(".notion-image");
  const caption = node.querySelector(".notion-caption");

  let currentUrl = block.url || "";
  image.src = currentUrl;
  image.alt = block.caption || "";
  caption.textContent = block.caption || "";

  if (!block.caption) caption.classList.add("is-empty");

  const placeholder = document.createElement("div");
  placeholder.className = "image-placeholder";
  placeholder.textContent = "이미지를 추가하려면 클릭하세요";
  if (!currentUrl) image.replaceWith(placeholder);

  function openEditPanel(anchorEl) {
    const panel = buildImageEditPanel({
      currentUrl,
      onCommit(newUrl) {
        if (newUrl && newUrl !== currentUrl) {
          currentUrl = newUrl;
          image.src = newUrl;
          apiPatchBlock(block.id, { url: newUrl }).catch(console.error);
        }
        panel.replaceWith(currentUrl ? image : placeholder);
        node.classList.remove("is-editing");
      },
      onCancel() {
        panel.replaceWith(currentUrl ? image : placeholder);
        node.classList.remove("is-editing");
      },
    });
    node.classList.add("is-editing");
    anchorEl.replaceWith(panel);
  }

  image.addEventListener("click", () => openEditPanel(image));
  placeholder.addEventListener("click", () => openEditPanel(placeholder));

  // ── Caption editing ──────────────────────────────────────────────────────
  let originalCaption = block.caption || "";
  let captionEscaped = false;
  caption.contentEditable = "true";

  caption.addEventListener("focus", () => {
    captionEscaped = false;
    node.classList.add("is-editing");
    caption.classList.remove("is-empty");
  });

  caption.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); caption.blur(); }
    if (e.key === "Escape") {
      captionEscaped = true;
      caption.textContent = originalCaption;
      if (!originalCaption) caption.classList.add("is-empty");
      caption.blur();
    }
  });

  caption.addEventListener("blur", () => {
    node.classList.remove("is-editing");
    if (captionEscaped) { captionEscaped = false; return; }
    const newCaption = caption.textContent.trim();
    caption.textContent = newCaption;
    if (!newCaption) caption.classList.add("is-empty");
    if (newCaption !== originalCaption) {
      originalCaption = newCaption;
      image.alt = newCaption;
      apiPatchBlock(block.id, { caption: newCaption }).catch(console.error);
    }
  });

  return node;
}

// ── Image edit panel (URL / file upload) ─────────────────────────────────────

/**
 * URL 입력과 파일 업로드를 탭으로 전환할 수 있는 편집 패널을 반환합니다.
 * @param {{ currentUrl: string, onCommit: (url: string) => void, onCancel: () => void }} opts
 * @returns {HTMLElement}
 */
function buildImageEditPanel({ currentUrl, onCommit, onCancel }) {
  const panel = document.createElement("div");
  panel.className = "image-edit-panel";

  // ── 탭 헤더 ──────────────────────────────────────────────────────────────
  const tabs = document.createElement("div");
  tabs.className = "image-edit-tabs";

  const urlTab = document.createElement("button");
  urlTab.type = "button";
  urlTab.className = "image-edit-tab is-active";
  urlTab.textContent = "URL";

  const fileTab = document.createElement("button");
  fileTab.type = "button";
  fileTab.className = "image-edit-tab";
  fileTab.textContent = "파일 업로드";

  tabs.append(urlTab, fileTab);

  // ── URL 패널 ─────────────────────────────────────────────────────────────
  const urlPane = document.createElement("div");
  urlPane.className = "image-edit-pane";

  const urlInput = document.createElement("input");
  urlInput.type = "text";
  urlInput.className = "image-url-input";
  urlInput.value = currentUrl;
  urlInput.placeholder = "https://...";

  const urlConfirm = document.createElement("button");
  urlConfirm.type = "button";
  urlConfirm.className = "image-edit-confirm";
  urlConfirm.textContent = "적용";

  urlPane.append(urlInput, urlConfirm);

  // ── 파일 업로드 패널 ──────────────────────────────────────────────────────
  const filePane = document.createElement("div");
  filePane.className = "image-edit-pane is-hidden";

  const dropZone = document.createElement("div");
  dropZone.className = "image-drop-zone";

  const dropLabel = document.createElement("span");
  dropLabel.className = "image-drop-label";
  dropLabel.textContent = "이미지를 드래그하거나 클릭해서 선택";

  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = "image/jpeg,image/png,image/gif,image/webp";
  fileInput.className = "image-file-input";

  const spinner = document.createElement("span");
  spinner.className = "image-upload-spinner is-hidden";
  spinner.textContent = "업로드 중...";

  dropZone.append(dropLabel, fileInput, spinner);
  filePane.append(dropZone);
  panel.append(tabs, urlPane, filePane);

  // ── 탭 전환 ──────────────────────────────────────────────────────────────
  urlTab.addEventListener("click", () => {
    urlTab.classList.add("is-active");
    fileTab.classList.remove("is-active");
    urlPane.classList.remove("is-hidden");
    filePane.classList.add("is-hidden");
  });

  fileTab.addEventListener("click", () => {
    fileTab.classList.add("is-active");
    urlTab.classList.remove("is-active");
    filePane.classList.remove("is-hidden");
    urlPane.classList.add("is-hidden");
  });

  // ── URL 적용 ─────────────────────────────────────────────────────────────
  urlConfirm.addEventListener("click", () => onCommit(urlInput.value.trim()));

  urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); onCommit(urlInput.value.trim()); }
    if (e.key === "Escape") onCancel();
  });

  // ── 파일 업로드 처리 ──────────────────────────────────────────────────────
  async function handleFile(file) {
    if (!file) return;
    dropLabel.classList.add("is-hidden");
    spinner.classList.remove("is-hidden");
    spinner.textContent = "업로드 중...";
    try {
      const result = await apiUploadImage(file);
      onCommit(result.url);
    } catch (err) {
      console.error(err);
      spinner.classList.add("is-hidden");
      dropLabel.classList.remove("is-hidden");
      dropLabel.textContent = "업로드 실패. 다시 시도하세요.";
    } finally {
      fileInput.value = "";
    }
  }

  fileInput.addEventListener("change", () => handleFile(fileInput.files[0]));

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("is-drag-over");
  });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("is-drag-over"));
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("is-drag-over");
    handleFile(e.dataTransfer.files[0]);
  });

  // 패널 외부 클릭 시 취소
  setTimeout(() => {
    document.addEventListener("click", function handler(e) {
      if (!panel.contains(e.target)) {
        document.removeEventListener("click", handler);
        if (panel.isConnected) onCancel();
      }
    });
  }, 0);

  return panel;
}
