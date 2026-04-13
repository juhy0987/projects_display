"""인메모리 세션 저장소.

``secrets.token_urlsafe``로 세션 토큰을 생성하고, 만료 시각과 함께
딕셔너리에 보관한다. 토큰 검증 시 만료된 세션은 자동으로 제거된다.

보안 고려사항:
  - 토큰은 충분한 엔트로피를 가진 난수로 생성하여 세션 식별자로 사용
  - 토큰 길이: 32바이트(URL-safe base64 → 43자) — OWASP 권장 128비트 이상
    Ref: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

from app.auth.config import SESSION_MAX_AGE


@dataclass
class _SessionEntry:
  username: str
  expires_at: float


@dataclass
class SessionStore:
  """프로세스 인메모리 세션 저장소."""

  _sessions: dict[str, _SessionEntry] = field(default_factory=dict)

  def create(self, username: str) -> str:
    """새 세션을 생성하고 토큰을 반환한다."""
    self.cleanup_expired()
    token = secrets.token_urlsafe(32)
    self._sessions[token] = _SessionEntry(
      username=username,
      expires_at=time.time() + SESSION_MAX_AGE,
    )
    return token

  def validate(self, token: str) -> str | None:
    """유효한 세션이면 username을 반환하고, 아니면 None."""
    entry = self._sessions.get(token)
    if entry is None:
      return None
    if time.time() > entry.expires_at:
      self._sessions.pop(token, None)
      return None
    return entry.username

  def revoke(self, token: str) -> bool:
    """세션을 무효화한다. 성공 시 True."""
    return self._sessions.pop(token, None) is not None

  def cleanup_expired(self) -> int:
    """만료된 세션을 일괄 제거하고 제거 건수를 반환한다."""
    now = time.time()
    expired = [k for k, v in self._sessions.items() if now > v.expires_at]
    for k in expired:
      del self._sessions[k]
    return len(expired)


# 싱글턴 — 프로세스 수명 동안 공유
session_store = SessionStore()
