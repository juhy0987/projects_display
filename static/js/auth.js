// ── 인증 상태 관리 모듈 ──────────────────────────────────────────────────────
//
// 전역 인증 상태를 관리하고, 로그인/로그아웃 API를 호출하며,
// 인증 상태 변경 시 구독자(subscriber)에게 알린다.
// Ref: Observer 패턴 — https://refactoring.guru/design-patterns/observer

/** @type {{ authenticated: boolean, username: string | null }} */
let _authState = { authenticated: false, username: null };

/** @type {Set<(state: typeof _authState) => void>} */
const _subscribers = new Set();

/** 현재 인증 상태를 반환한다 (읽기 전용 복사본). */
export function getAuthState() {
  return { ..._authState };
}

/** 인증 상태가 변경될 때 호출될 콜백을 등록한다. */
export function onAuthChange(callback) {
  _subscribers.add(callback);
  return () => _subscribers.delete(callback);
}

function _notify() {
  const snapshot = { ..._authState };
  _subscribers.forEach((cb) => cb(snapshot));
}

/** 서버에서 현재 인증 상태를 조회한다 (앱 초기화 시 호출). */
export async function fetchAuthStatus() {
  try {
    const res = await fetch("/api/auth/status");
    if (!res.ok) return;
    const data = await res.json();
    _authState = {
      authenticated: data.authenticated,
      username: data.username ?? null,
    };
    _notify();
  } catch {
    // 네트워크 오류 시 미인증 상태 유지
  }
}

/** 로그인 요청을 보낸다. 성공 시 true, 실패 시 에러 메시지 문자열을 반환한다. */
export async function login(username, password) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    return err.detail ?? "로그인에 실패했습니다.";
  }
  const data = await res.json();
  _authState = { authenticated: true, username: data.username };
  _notify();
  return true;
}

/** 로그아웃 요청을 보낸다. */
export async function logout() {
  await fetch("/api/auth/logout", { method: "POST" });
  _authState = { authenticated: false, username: null };
  _notify();
}

/**
 * 인증이 필요한 API 응답(403)을 처리하는 헬퍼.
 * 기존 api.js의 fetch 래퍼에서 쓰기 실패 시 사용자에게 안내한다.
 */
export function isPermissionError(res) {
  return res.status === 403;
}
