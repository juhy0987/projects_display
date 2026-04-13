// ── File Block ─────────────────────────────────────────────────────────────────
//
// 상태 흐름:
//
//   [생성 직후 / file_id 없음]      [file_id 있음]
//         ↓                              ↓
//   empty (드롭존 표시)           uploaded (파일 카드 표시)
//         ↓ 파일 선택 / 드래그            ↓ ✕ 버튼
//   uploading (스피너)            empty (파일 제거 후)
//         ↓ 완료
//   uploaded (파일 카드)

import { apiUploadFile, apiDeleteFile, apiPatchBlock } from "../api.js";

export const type = "file";

/**
 * 파일 블록 DOM을 생성합니다.
 *
 * 파일이 없을 때: 드래그&드롭 / 클릭으로 업로드 유도.
 * 파일이 있을 때: 파일명·크기·MIME 타입을 카드로 표시하고 다운로드·제거 버튼 노출.
 *
 * @param {object} block           - 서버에서 받은 블록 데이터 (FileBlock 스키마)
 * @param {{ callbacks: object }} opts
 * @returns {HTMLElement}
 */
export function create(block, { callbacks } = {}) {
  const template = document.getElementById("file-block-template");
  const node = template.content.firstElementChild.cloneNode(true);

  const emptyState   = node.querySelector(".file-empty-state");
  const dropZone     = node.querySelector(".file-drop-zone");
  const fileInput    = node.querySelector(".file-input");
  const dropLabel    = node.querySelector(".file-drop-label");
  const spinnerWrap  = node.querySelector(".file-upload-spinner");
  const errorEl      = node.querySelector(".file-upload-error");
  const uploadedState = node.querySelector(".file-uploaded-state");
  const fileIcon     = node.querySelector(".file-icon");
  const fileName     = node.querySelector(".file-name");
  const fileMeta     = node.querySelector(".file-meta");
  const downloadBtn  = node.querySelector(".file-download-btn");
  const removeBtn    = node.querySelector(".file-remove-btn");

  // ── 상태 전환 ────────────────────────────────────────────────────────────

  function showEmpty() {
    emptyState.hidden    = false;
    spinnerWrap.hidden   = true;
    uploadedState.hidden = true;
    errorEl.hidden       = true;
    dropLabel.textContent = "파일을 드래그하거나 클릭해서 업로드";
  }

  function showUploading() {
    emptyState.hidden    = true;
    spinnerWrap.hidden   = false;
    uploadedState.hidden = true;
    errorEl.hidden       = true;
  }

  function showUploaded() {
    fileIcon.textContent  = _mimeIcon(block.mime_type);
    fileName.textContent  = block.original_filename || "파일";
    fileMeta.textContent  = _formatMeta(block.mime_type, block.size_bytes);
    downloadBtn.href      = block.download_url || `/api/files/${block.file_id}`;
    downloadBtn.download  = block.original_filename || "";

    emptyState.hidden    = true;
    spinnerWrap.hidden   = true;
    uploadedState.hidden = false;
    errorEl.hidden       = true;
  }

  function showError(msg) {
    errorEl.textContent  = msg;
    errorEl.hidden       = false;
    spinnerWrap.hidden   = true;
    emptyState.hidden    = false;
  }

  // ── 초기 렌더링 ───────────────────────────────────────────────────────────

  if (block.file_id) {
    showUploaded();
  } else {
    showEmpty();
  }

  // ── 업로드 처리 ───────────────────────────────────────────────────────────

  async function handleFile(file) {
    if (!file) return;
    showUploading();

    // patch 성공 후에만 block 상태를 갱신하여 실패 시 orphan 파일을 방지한다.
    // Ref: 낙관적 업데이트 대신 확정(confirm-then-apply) 패턴 사용
    //   https://developer.mozilla.org/en-US/docs/Glossary/Optimistic_UI
    let uploadedFile = null;
    try {
      uploadedFile = await apiUploadFile(file);
      // 블록 content_json에 file_id 저장이 성공한 뒤에만
      // block 객체에 업로드된 파일 메타데이터를 반영한다.
      await apiPatchBlock(block.id, { file_id: uploadedFile.id });

      block.file_id           = uploadedFile.id;
      block.original_filename = uploadedFile.original_filename;
      block.size_bytes        = uploadedFile.size_bytes;
      block.mime_type         = uploadedFile.mime_type;
      block.download_url      = uploadedFile.download_url;

      showUploaded();
    } catch (err) {
      // patch 실패 시 이미 업로드된 파일을 정리하여 orphan 방지
      if (uploadedFile?.id) {
        await apiDeleteFile(uploadedFile.id).catch((deleteErr) => {
          console.error("업로드된 파일 정리 실패:", deleteErr);
        });
      }
      console.error("파일 업로드 실패:", err);
      showError(err.message || "업로드 실패. 다시 시도하세요.");
    } finally {
      fileInput.value = "";
    }
  }

  fileInput.addEventListener("change", () => handleFile(fileInput.files[0]));

  // 드롭존 클릭 → 파일 선택 대화상자
  dropZone.addEventListener("click", () => fileInput.click());
  // Enter / Space 키보드 접근성
  dropZone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

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

  // ── 파일 제거 ─────────────────────────────────────────────────────────────

  removeBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const oldFileId = block.file_id;

    // patch 성공 후에만 로컬 상태를 갱신하여 서버/클라이언트 불일치를 방지한다.
    try {
      await apiPatchBlock(block.id, { file_id: "" });

      block.file_id           = "";
      block.original_filename = "";
      block.size_bytes        = 0;
      block.mime_type         = "";
      block.download_url      = "";
      showEmpty();

      // 서버의 블록 참조 제거가 확인된 뒤에만 실제 파일 삭제를 시도
      if (oldFileId) await apiDeleteFile(oldFileId).catch(console.error);
    } catch (err) {
      console.error("파일 제거 실패:", err);
      showError("파일 제거에 실패했습니다. 다시 시도하세요.");
    }
  });

  return node;
}

// ── 내부 유틸 ─────────────────────────────────────────────────────────────────

/**
 * MIME 타입에 대응하는 이모지 아이콘을 반환합니다.
 * @param {string} mime
 * @returns {string}
 */
function _mimeIcon(mime = "") {
  if (mime.startsWith("image/"))                                return "🖼";
  if (mime.startsWith("video/"))                                return "🎬";
  if (mime.startsWith("audio/"))                                return "🎵";
  if (mime === "application/pdf")                               return "📄";
  if (mime.includes("zip") || mime.includes("archive"))         return "📦";
  if (mime.includes("word") || mime.includes("document"))       return "📝";
  if (mime.includes("sheet") || mime.includes("excel"))         return "📊";
  if (mime.includes("presentation") || mime.includes("powerpoint")) return "📊";
  if (mime.startsWith("text/"))                                 return "📃";
  return "📎";
}

/**
 * MIME 타입과 크기를 사람이 읽기 쉬운 문자열로 조합합니다.
 * @param {string} mime
 * @param {number} sizeBytes
 * @returns {string}
 */
function _formatMeta(mime = "", sizeBytes = 0) {
  let sizeStr;
  if (sizeBytes >= 1024 * 1024) {
    sizeStr = `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
  } else if (sizeBytes >= 1024) {
    sizeStr = `${(sizeBytes / 1024).toFixed(1)} KB`;
  } else {
    sizeStr = `${sizeBytes} B`;
  }
  const ext = mime ? mime.split("/").pop().toUpperCase() : "";
  return ext ? `${ext} · ${sizeStr}` : sizeStr;
}
