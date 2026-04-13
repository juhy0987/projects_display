// ── Notion Import Modal ──────────────────────────────────────────────────────
//
// Notion export HTML/ZIP 파일을 업로드하여 프로젝트 페이지로 변환하는
// 모달 UI를 제공합니다.
//
// 플로우:
//   1. 사용자가 Import 버튼 클릭 → 모달 열림
//   2. 파일 선택 (.html / .zip)
//   3. 업로드 및 변환 진행 (프로그레스 표시)
//   4. 완료 → 변환 리포트 표시, 생성된 문서로 이동

import { apiImportNotion } from "./api.js";

/** @type {HTMLDialogElement|null} */
let dialog = null;

/**
 * 모달 DOM을 한 번만 생성하고 재사용합니다.
 * @returns {HTMLDialogElement}
 */
function ensureDialog() {
  if (dialog) return dialog;

  dialog = document.createElement("dialog");
  dialog.className = "notion-import-dialog";
  dialog.innerHTML = `
    <div class="notion-import-content">
      <h3 class="notion-import-title">Notion Import</h3>
      <p class="notion-import-desc">
        Notion에서 export한 HTML, Markdown 또는 ZIP 파일을 선택하세요.
      </p>

      <div class="notion-import-dropzone" id="notion-import-dropzone">
        <span class="notion-import-dropzone-icon">&#128196;</span>
        <span class="notion-import-dropzone-text">.html, .md 또는 .zip 파일을 드래그하거나 클릭하세요</span>
        <input type="file" id="notion-import-file" accept=".html,.htm,.md,.zip" hidden />
      </div>

      <div class="notion-import-selected" id="notion-import-selected" hidden>
        <span class="notion-import-filename" id="notion-import-filename"></span>
        <button type="button" class="notion-import-clear" id="notion-import-clear">&times;</button>
      </div>

      <div class="notion-import-progress" id="notion-import-progress" hidden>
        <div class="notion-import-progress-bar">
          <div class="notion-import-progress-fill" id="notion-import-progress-fill"></div>
        </div>
        <span class="notion-import-progress-text" id="notion-import-progress-text">변환 중...</span>
      </div>

      <div class="notion-import-report" id="notion-import-report" hidden></div>

      <div class="notion-import-actions">
        <button type="button" class="notion-import-cancel" id="notion-import-cancel">취소</button>
        <button type="button" class="notion-import-submit" id="notion-import-submit" disabled>Import</button>
      </div>
    </div>
  `;

  document.body.appendChild(dialog);

  // 이벤트 바인딩
  const dropzone = dialog.querySelector("#notion-import-dropzone");
  const fileInput = dialog.querySelector("#notion-import-file");
  const selectedEl = dialog.querySelector("#notion-import-selected");
  const filenameEl = dialog.querySelector("#notion-import-filename");
  const clearBtn = dialog.querySelector("#notion-import-clear");
  const cancelBtn = dialog.querySelector("#notion-import-cancel");
  const submitBtn = dialog.querySelector("#notion-import-submit");

  // 클릭으로 파일 선택
  dropzone.addEventListener("click", () => fileInput.click());

  // 드래그 앤 드롭
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("is-dragover");
  });
  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("is-dragover");
  });
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("is-dragover");
    const files = e.dataTransfer.files;
    if (files.length > 0) selectFile(files[0]);
  });

  // 파일 선택 이벤트
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) selectFile(fileInput.files[0]);
  });

  // 선택 해제
  clearBtn.addEventListener("click", () => {
    resetFileSelection();
  });

  // 취소
  cancelBtn.addEventListener("click", () => {
    dialog.close();
    resetState();
  });

  // backdrop 클릭으로 닫기
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) {
      dialog.close();
      resetState();
    }
  });

  // ESC 닫기
  dialog.addEventListener("cancel", () => {
    resetState();
  });

  return dialog;
}

/** @type {File|null} */
let selectedFile = null;

/** @type {((docId: string) => void)|null} */
let onComplete = null;

function selectFile(file) {
  const name = file.name.toLowerCase();
  if (!name.endsWith(".html") && !name.endsWith(".htm") && !name.endsWith(".md") && !name.endsWith(".zip")) {
    alert("지원하지 않는 파일 형식입니다. .html, .md 또는 .zip 파일을 선택해주세요.");
    return;
  }

  selectedFile = file;

  const dropzone = dialog.querySelector("#notion-import-dropzone");
  const selectedEl = dialog.querySelector("#notion-import-selected");
  const filenameEl = dialog.querySelector("#notion-import-filename");
  const submitBtn = dialog.querySelector("#notion-import-submit");

  dropzone.hidden = true;
  selectedEl.hidden = false;
  filenameEl.textContent = file.name;
  submitBtn.disabled = false;
}

function resetFileSelection() {
  selectedFile = null;
  const dropzone = dialog.querySelector("#notion-import-dropzone");
  const selectedEl = dialog.querySelector("#notion-import-selected");
  const fileInput = dialog.querySelector("#notion-import-file");
  const submitBtn = dialog.querySelector("#notion-import-submit");

  dropzone.hidden = false;
  selectedEl.hidden = true;
  fileInput.value = "";
  submitBtn.disabled = true;
}

function resetState() {
  resetFileSelection();
  const progress = dialog.querySelector("#notion-import-progress");
  const report = dialog.querySelector("#notion-import-report");
  const submitBtn = dialog.querySelector("#notion-import-submit");
  const cancelBtn = dialog.querySelector("#notion-import-cancel");

  progress.hidden = true;
  report.hidden = true;
  submitBtn.disabled = true;
  submitBtn.textContent = "Import";
  cancelBtn.textContent = "취소";
}

/**
 * Notion Import 모달을 열고, import 완료 시 콜백을 실행합니다.
 * @param {(docId: string) => void} onImportComplete - 생성된 문서 ID로 이동하는 콜백
 */
export function openNotionImportModal(onImportComplete) {
  const dlg = ensureDialog();
  resetState();
  onComplete = onImportComplete;

  const submitBtn = dlg.querySelector("#notion-import-submit");

  // 기존 리스너 제거 후 재등록
  const newSubmit = submitBtn.cloneNode(true);
  submitBtn.replaceWith(newSubmit);
  newSubmit.addEventListener("click", handleSubmit);

  dlg.showModal();
}

async function handleSubmit() {
  if (!selectedFile || !dialog) return;

  const progress = dialog.querySelector("#notion-import-progress");
  const progressFill = dialog.querySelector("#notion-import-progress-fill");
  const progressText = dialog.querySelector("#notion-import-progress-text");
  const report = dialog.querySelector("#notion-import-report");
  const submitBtn = dialog.querySelector("#notion-import-submit");
  const cancelBtn = dialog.querySelector("#notion-import-cancel");

  // 진행 상태 표시
  progress.hidden = false;
  submitBtn.disabled = true;
  progressFill.style.width = "30%";
  progressText.textContent = "파일 업로드 중...";

  try {
    progressFill.style.width = "60%";
    progressText.textContent = "변환 중...";

    const result = await apiImportNotion(selectedFile);

    progressFill.style.width = "100%";
    progressText.textContent = "완료!";

    // 변환 리포트 표시
    const r = result.report;
    report.hidden = false;
    report.innerHTML = `
      <div class="notion-import-report-header">변환 완료</div>
      <div class="notion-import-report-body">
        <div class="notion-import-report-row">
          <span>생성된 문서</span>
          <strong>${result.title}</strong>
        </div>
        <div class="notion-import-report-row">
          <span>총 페이지</span>
          <strong>${result.total_pages}개</strong>
        </div>
        <div class="notion-import-report-row">
          <span>변환 요소</span>
          <strong>${r.converted} / ${r.total_elements}</strong>
        </div>
        ${r.fallback > 0 ? `
        <div class="notion-import-report-row notion-import-report-warn">
          <span>Fallback 처리</span>
          <strong>${r.fallback}건</strong>
        </div>` : ""}
        ${r.skipped > 0 ? `
        <div class="notion-import-report-row notion-import-report-skip">
          <span>건너뜀</span>
          <strong>${r.skipped}건</strong>
        </div>` : ""}
        ${r.warnings.length > 0 ? `
        <details class="notion-import-report-warnings">
          <summary>경고 (${r.warnings.length}건)</summary>
          <ul>${r.warnings.map((w) => `<li>${w}</li>`).join("")}</ul>
        </details>` : ""}
      </div>
    `;

    // 버튼 상태 변경
    submitBtn.textContent = "문서 열기";
    submitBtn.disabled = false;
    cancelBtn.textContent = "닫기";

    // 버튼 동작 변경: 문서로 이동
    const newSubmit = submitBtn.cloneNode(true);
    submitBtn.replaceWith(newSubmit);
    newSubmit.addEventListener("click", () => {
      dialog.close();
      resetState();
      if (onComplete) onComplete(result.document_id);
    });

  } catch (err) {
    progressFill.style.width = "100%";
    progressFill.classList.add("is-error");
    progressText.textContent = `오류: ${err.message}`;
    submitBtn.disabled = false;
    submitBtn.textContent = "다시 시도";

    // 에러 후 다시 시도 가능하도록 초기화
    setTimeout(() => {
      progressFill.classList.remove("is-error");
    }, 3000);
  }
}
