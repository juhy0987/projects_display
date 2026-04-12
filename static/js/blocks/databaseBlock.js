// ── Database Block ─────────────────────────────────────────────────────────────
//
// 테이블 형태로 렌더링되는 데이터베이스 블록.
// 각 행(db_row)은 클릭 시 독립 페이지로 열린다.

import {
  apiAddDbColumn,
  apiUpdateDbColumn,
  apiRemoveDbColumn,
  apiCreateBlock,
  apiUpdateDbRowProperties,
  apiPatchBlock,
} from "../api.js";

export const type = "database";

/**
 * @param {object} block  - DatabaseBlock 데이터
 * @param {object} opts
 * @param {object} opts.callbacks
 * @returns {HTMLElement}
 */
// 사용 가능한 배경 색상 목록
const DB_COLORS = [
  { id: "default", label: "기본 (흰색)",  bg: "#ffffff" },
  { id: "gray",    label: "회색",          bg: "#f1f1ef" },
  { id: "brown",   label: "갈색",          bg: "#f4eeee" },
  { id: "orange",  label: "주황",          bg: "#fbecdd" },
  { id: "yellow",  label: "노랑",          bg: "#fbf3db" },
  { id: "green",   label: "초록",          bg: "#edf3ec" },
  { id: "blue",    label: "파랑",          bg: "#e7f0f8" },
  { id: "purple",  label: "보라",          bg: "#f4f0f7" },
  { id: "pink",    label: "분홍",          bg: "#f9eff3" },
  { id: "red",     label: "빨강",          bg: "#fbe4e4" },
];

/**
 * color id를 받아 .notion-database 요소에 배경색 인라인 스타일을 적용한다.
 * @param {HTMLElement} el
 * @param {string} colorId
 */
function applyColor(el, colorId) {
  const found = DB_COLORS.find((c) => c.id === colorId) ?? DB_COLORS[0];
  el.style.backgroundColor = found.bg;
}

export function create(block, { callbacks = {} } = {}) {
  const wrap = document.createElement("div");
  wrap.className = "notion-block notion-database";
  wrap.dataset.dbBlockId = block.id;

  // 저장된 색상 적용 (없으면 기본 흰색)
  applyColor(wrap, block.color ?? "default");

  // ── 제목 + 색상 버튼 ────────────────────────────────────────────────────────
  const titleRow = document.createElement("div");
  titleRow.className = "db-title-row";

  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.className = "db-title-input";
  titleInput.value = block.title || "";
  titleInput.placeholder = "데이터베이스 이름...";
  let dbTitleOriginal = titleInput.value;
  titleInput.addEventListener("focus", () => { dbTitleOriginal = titleInput.value; });
  titleInput.addEventListener("blur", async () => {
    const newTitle = titleInput.value.trim();
    if (newTitle === dbTitleOriginal) return;
    try {
      await apiPatchBlock(block.id, { title: newTitle });
      dbTitleOriginal = newTitle;
      if (callbacks.onDbTitleChanged) callbacks.onDbTitleChanged(block.id, newTitle);
    } catch (err) {
      console.error("DB 제목 저장 실패:", err);
    }
  });
  titleInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") titleInput.blur();
  });

  // 색상 선택 버튼
  const colorBtn = document.createElement("button");
  colorBtn.type = "button";
  colorBtn.className = "db-color-btn";
  colorBtn.title = "배경 색상 변경";
  colorBtn.textContent = "🎨";
  colorBtn.addEventListener("click", () => {
    toggleColorPalette();
  });

  // 색상 팔레트 드롭다운
  const colorPalette = document.createElement("div");
  colorPalette.className = "db-color-palette";
  colorPalette.hidden = true;

  DB_COLORS.forEach((c) => {
    const swatch = document.createElement("button");
    swatch.type = "button";
    swatch.className = "db-color-swatch";
    swatch.title = c.label;
    swatch.style.backgroundColor = c.bg;
    if ((block.color ?? "default") === c.id) swatch.classList.add("is-active");

    swatch.addEventListener("mousedown", (e) => e.preventDefault());
    swatch.addEventListener("click", async () => {
      block.color = c.id;
      applyColor(wrap, c.id);
      colorPalette.querySelectorAll(".db-color-swatch").forEach((s) => s.classList.remove("is-active"));
      swatch.classList.add("is-active");
      closePalette();
      try {
        await apiPatchBlock(block.id, { color: c.id });
      } catch (err) {
        console.error("색상 저장 실패:", err);
      }
    });
    colorPalette.appendChild(swatch);
  });

  let removeOutsideListener = () => {};

  function closePalette() {
    colorPalette.hidden = true;
    removeOutsideListener();
    removeOutsideListener = () => {};
  }

  function openPalette() {
    colorPalette.hidden = false;
    // 다음 틱에 등록: 팔레트를 연 클릭 자체가 즉시 닫기를 트리거하지 않도록
    setTimeout(() => {
      if (!colorPalette.isConnected) return;
      function onOutside(e) {
        // colorBtn 클릭은 여기서 처리하지 않음 — 버튼 핸들러가 toggle을 담당
        if (colorBtn.contains(e.target)) return;
        if (!colorPalette.contains(e.target)) closePalette();
      }
      document.addEventListener("click", onOutside, true);
      removeOutsideListener = () => document.removeEventListener("click", onOutside, true);
    }, 0);
  }

  function toggleColorPalette() {
    if (colorPalette.hidden) openPalette();
    else closePalette();
  }

  titleRow.appendChild(titleInput);
  titleRow.appendChild(colorBtn);
  titleRow.appendChild(colorPalette);
  wrap.appendChild(titleRow);

  // ── 테이블 ──────────────────────────────────────────────────────────────────
  const tableWrap = document.createElement("div");
  tableWrap.className = "db-table-wrap";

  const table = document.createElement("table");
  table.className = "db-table";

  const thead = document.createElement("thead");
  const tbody = document.createElement("tbody");
  table.appendChild(thead);
  table.appendChild(tbody);
  tableWrap.appendChild(table);
  wrap.appendChild(tableWrap);

  // ── 새 행 추가 버튼 ──────────────────────────────────────────────────────────
  const addRowBtn = document.createElement("button");
  addRowBtn.type = "button";
  addRowBtn.className = "db-add-row-btn";
  addRowBtn.textContent = "+ 새 행";
  addRowBtn.addEventListener("click", async () => {
    if (!callbacks.addDbRow) return;
    await callbacks.addDbRow(block.id);
  });
  wrap.appendChild(addRowBtn);

  // ── 렌더 함수 ─────────────────────────────────────────────────────────────────
  function render(schema, rows) {
    renderHeader(schema);
    renderRows(schema, rows);
  }

  function renderHeader(schema) {
    thead.innerHTML = "";
    const tr = document.createElement("tr");

    // 열기 버튼 컬럼 (고정)
    const thOpen = document.createElement("th");
    thOpen.className = "db-th db-th-open";
    tr.appendChild(thOpen);

    // 이름(제목) 컬럼 (고정)
    const thTitle = document.createElement("th");
    thTitle.className = "db-th db-th-title";
    thTitle.textContent = "이름";
    tr.appendChild(thTitle);

    // 스키마 컬럼들
    schema.forEach((col) => {
      const th = document.createElement("th");
      th.className = "db-th";
      th.dataset.colId = col.id;

      const nameSpan = document.createElement("span");
      nameSpan.className = "db-col-name";
      nameSpan.textContent = col.name;
      nameSpan.title = "클릭하여 편집";
      nameSpan.addEventListener("click", () => startColumnRename(th, nameSpan, col));

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "db-col-remove-btn";
      removeBtn.textContent = "×";
      removeBtn.title = "컬럼 삭제";
      removeBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm(`"${col.name}" 컬럼을 삭제할까요? 모든 행의 해당 값도 삭제됩니다.`)) return;
        try {
          await apiRemoveDbColumn(block.id, col.id);
          if (callbacks.reloadDocument) callbacks.reloadDocument();
        } catch (err) {
          console.error("컬럼 삭제 실패:", err);
        }
      });

      th.appendChild(nameSpan);
      th.appendChild(removeBtn);
      tr.appendChild(th);
    });

    // + 컬럼 추가 버튼
    const thAdd = document.createElement("th");
    thAdd.className = "db-th db-th-add";
    const addColBtn = document.createElement("button");
    addColBtn.type = "button";
    addColBtn.className = "db-add-col-btn";
    addColBtn.textContent = "+";
    addColBtn.title = "컬럼 추가";
    addColBtn.addEventListener("click", () => startAddColumn(thAdd));
    thAdd.appendChild(addColBtn);
    tr.appendChild(thAdd);

    thead.appendChild(tr);
  }

  function renderRows(schema, rows) {
    tbody.innerHTML = "";
    rows.forEach((row) => {
      tbody.appendChild(createRowEl(schema, row));
    });
  }

  function createRowEl(schema, row) {
    const tr = document.createElement("tr");
    tr.className = "db-row";
    tr.dataset.rowBlockId = row.id;
    tr.dataset.docId = row.document_id;

    if (row.is_broken_ref) {
      tr.classList.add("is-broken-ref");
    }

    // 페이지로 열기 버튼
    const tdOpen = document.createElement("td");
    tdOpen.className = "db-td db-td-open";
    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = "db-row-open-btn";
    openBtn.title = "페이지로 열기";
    openBtn.textContent = "⤷";
    if (!row.is_broken_ref) {
      openBtn.addEventListener("click", () => {
        if (callbacks.navigateTo) callbacks.navigateTo(row.document_id);
      });
    }
    tdOpen.appendChild(openBtn);
    tr.appendChild(tdOpen);

    // 이름(제목) 셀
    const tdTitle = document.createElement("td");
    tdTitle.className = "db-td db-td-title";
    const titleEl = document.createElement("span");
    titleEl.className = "db-row-title";
    titleEl.textContent = row.is_broken_ref ? "삭제된 페이지" : (row.title || "제목 없음");
    if (!row.is_broken_ref) {
      titleEl.style.cursor = "pointer";
      titleEl.addEventListener("click", () => {
        if (callbacks.navigateTo) callbacks.navigateTo(row.document_id);
      });
    }
    tdTitle.appendChild(titleEl);
    tr.appendChild(tdTitle);

    // 속성 셀들
    schema.forEach((col) => {
      const td = document.createElement("td");
      td.className = "db-td";
      td.dataset.colId = col.id;

      if (!row.is_broken_ref) {
        const input = createCellInput(col, row.properties?.[col.id] ?? "", async (newVal) => {
          const props = { ...(row.properties || {}), [col.id]: newVal };
          try {
            await apiUpdateDbRowProperties(row.id, props);
            row.properties = props;
          } catch (err) {
            console.error("속성 저장 실패:", err);
          }
        });
        td.appendChild(input);
      }

      tr.appendChild(td);
    });

    return tr;
  }

  function createCellInput(col, value, onCommit) {
    if (col.type === "checkbox") {
      const input = document.createElement("input");
      input.type = "checkbox";
      input.className = "db-cell-checkbox";
      input.checked = value === true || value === "true";
      input.addEventListener("change", () => onCommit(input.checked));
      return input;
    }

    const input = document.createElement("input");
    input.type = col.type === "number" ? "number" : "text";
    input.className = "db-cell-input";
    input.value = value ?? "";

    let original = input.value;
    input.addEventListener("focus", () => { original = input.value; });
    input.addEventListener("blur", () => {
      if (input.value !== original) onCommit(input.value);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); input.blur(); }
      if (e.key === "Escape") { input.value = original; input.blur(); }
    });
    return input;
  }

  function startColumnRename(thEl, nameSpan, col) {
    if (thEl.querySelector(".db-col-rename-input")) return;
    const input = document.createElement("input");
    input.type = "text";
    input.className = "db-col-rename-input";
    input.value = col.name;
    nameSpan.replaceWith(input);
    input.focus();
    input.select();

    async function commit() {
      const newName = input.value.trim() || col.name;
      try {
        await apiUpdateDbColumn(block.id, col.id, { name: newName });
        col.name = newName;
        if (callbacks.reloadDocument) callbacks.reloadDocument();
      } catch (err) {
        console.error("컬럼 이름 변경 실패:", err);
        input.replaceWith(nameSpan);
      }
    }

    input.addEventListener("blur", commit);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); input.blur(); }
      if (e.key === "Escape") { input.replaceWith(nameSpan); }
    });
  }

  function startAddColumn(thAdd) {
    // 이미 추가 중이면 중복 방지
    if (thead.querySelector(".db-col-new-input")) return;

    const thNew = document.createElement("th");
    thNew.className = "db-th";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "db-col-rename-input db-col-new-input";
    input.placeholder = "컬럼 이름";
    thNew.appendChild(input);
    thAdd.before(thNew);
    input.focus();

    let committed = false;

    async function commit() {
      if (committed) return;
      committed = true;
      const name = input.value.trim();
      if (!name) {
        thNew.remove();
        return;
      }
      try {
        await apiAddDbColumn(block.id, name);
        if (callbacks.reloadDocument) callbacks.reloadDocument();
      } catch (err) {
        console.error("컬럼 추가 실패:", err);
        thNew.remove();
      }
    }

    function cancel() {
      if (committed) return;
      committed = true;
      thNew.remove();
    }

    input.addEventListener("blur", commit);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); input.blur(); }
      if (e.key === "Escape") { cancel(); }
    });
  }

  // 최초 렌더
  render(block.columns ?? [], block.rows ?? []);

  return wrap;
}
