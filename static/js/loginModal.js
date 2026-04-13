// ── 로그인 모달 ──────────────────────────────────────────────────────────────
//
// 우상단 로그인 버튼과 모달을 관리한다.
// 인증 상태에 따라 버튼 텍스트/동작이 전환된다.

import { getAuthState, onAuthChange, login, logout } from "./auth.js";

/** 로그인 버튼 및 모달을 초기화한다. */
export function initLoginUI() {
  _createLoginButton();
  _createLoginModal();

  // 인증 상태 변경 구독
  onAuthChange(_updateButtonState);
  _updateButtonState(getAuthState());
}

// ── 로그인 버튼 (우상단) ──────────────────────────────────────────────────────

let _loginBtn = null;

function _createLoginButton() {
  _loginBtn = document.createElement("button");
  _loginBtn.id = "auth-btn";
  _loginBtn.type = "button";
  _loginBtn.className = "auth-btn";

  _loginBtn.addEventListener("click", () => {
    const state = getAuthState();
    if (state.authenticated) {
      _handleLogout();
    } else {
      _openModal();
    }
  });

  // main-area 내부 상단에 고정 배치
  const mainArea = document.querySelector(".main-area");
  if (mainArea) {
    mainArea.appendChild(_loginBtn);
  }
}

function _updateButtonState(state) {
  if (!_loginBtn) return;
  if (state.authenticated) {
    _loginBtn.textContent = "로그아웃";
    _loginBtn.classList.add("is-authenticated");
    _loginBtn.title = `${state.username} (로그아웃)`;
  } else {
    _loginBtn.textContent = "로그인";
    _loginBtn.classList.remove("is-authenticated");
    _loginBtn.title = "관리자 로그인";
  }
}

async function _handleLogout() {
  await logout();
  // 페이지를 새로고침하여 read-only 상태로 전환
  window.location.reload();
}

// ── 로그인 모달 ──────────────────────────────────────────────────────────────

let _modal = null;
let _usernameInput = null;
let _passwordInput = null;
let _errorMsg = null;

function _createLoginModal() {
  _modal = document.createElement("div");
  _modal.className = "login-modal-overlay";

  const dialog = document.createElement("div");
  dialog.className = "login-modal";
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-label", "관리자 로그인");

  // 제목
  const title = document.createElement("h2");
  title.className = "login-modal-title";
  title.textContent = "관리자 로그인";
  dialog.appendChild(title);

  // 에러 메시지
  _errorMsg = document.createElement("p");
  _errorMsg.className = "login-modal-error";
  _errorMsg.hidden = true;
  dialog.appendChild(_errorMsg);

  // 폼
  const form = document.createElement("form");
  form.className = "login-modal-form";
  form.addEventListener("submit", _handleSubmit);

  _usernameInput = _createField(form, "text", "아이디", "username");
  _passwordInput = _createField(form, "password", "비밀번호", "password");

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.className = "login-modal-submit";
  submitBtn.textContent = "로그인";
  form.appendChild(submitBtn);

  dialog.appendChild(form);

  // 닫기 버튼
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "login-modal-close";
  closeBtn.setAttribute("aria-label", "닫기");
  closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", _closeModal);
  dialog.appendChild(closeBtn);

  _modal.appendChild(dialog);

  // 오버레이 클릭 시 닫기
  _modal.addEventListener("click", (e) => {
    if (e.target === _modal) _closeModal();
  });

  document.body.appendChild(_modal);
}

function _createField(form, type, label, name) {
  const group = document.createElement("div");
  group.className = "login-field";

  const lbl = document.createElement("label");
  lbl.className = "login-field-label";
  lbl.textContent = label;
  lbl.htmlFor = `login-${name}`;
  group.appendChild(lbl);

  const input = document.createElement("input");
  input.type = type;
  input.id = `login-${name}`;
  input.name = name;
  input.className = "login-field-input";
  input.required = true;
  input.autocomplete = type === "password" ? "current-password" : "username";
  group.appendChild(input);

  form.appendChild(group);
  return input;
}

function _openModal() {
  _modal.classList.add("is-open");
  _errorMsg.hidden = true;
  _usernameInput.value = "";
  _passwordInput.value = "";
  _usernameInput.focus();

  // Escape로 닫기
  document.addEventListener("keydown", _onKeydown);
}

function _closeModal() {
  _modal.classList.remove("is-open");
  document.removeEventListener("keydown", _onKeydown);
}

function _onKeydown(e) {
  if (e.key === "Escape") _closeModal();
}

async function _handleSubmit(e) {
  e.preventDefault();
  const username = _usernameInput.value.trim();
  const password = _passwordInput.value;

  if (!username || !password) {
    _showError("아이디와 비밀번호를 입력해 주세요.");
    return;
  }

  const result = await login(username, password);
  if (result === true) {
    _closeModal();
    // 페이지를 새로고침하여 write 모드로 전환
    window.location.reload();
  } else {
    _showError(result);
    _passwordInput.value = "";
    _passwordInput.focus();
  }
}

function _showError(msg) {
  _errorMsg.textContent = msg;
  _errorMsg.hidden = false;
}
