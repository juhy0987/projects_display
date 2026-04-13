"""인증 서비스 — 자격 증명 검증과 세션 발급/해제를 담당한다.

비밀번호 비교에 ``secrets.compare_digest``를 사용해 타이밍 공격을 방지한다.
Ref: https://docs.python.org/3/library/secrets.html#secrets.compare_digest
"""
from __future__ import annotations

import secrets

from app.auth.config import ADMIN_PASSWORD, ADMIN_USERNAME
from app.auth.session import session_store


def authenticate(username: str, password: str) -> str | None:
  """자격 증명을 검증하고 세션 토큰을 반환한다.

  인증 실패 시 None을 반환한다. 사용자명과 비밀번호 모두
  ``compare_digest``로 비교해 어떤 필드가 틀렸는지 추론할 수 없게 한다.
  """
  username_ok = secrets.compare_digest(username, ADMIN_USERNAME)
  password_ok = secrets.compare_digest(password, ADMIN_PASSWORD)
  if not (username_ok and password_ok):
    return None
  return session_store.create(username)


def validate_session(token: str) -> str | None:
  """세션 토큰을 검증하고 username을 반환한다. 무효하면 None."""
  return session_store.validate(token)


def logout(token: str) -> bool:
  """세션을 해제한다."""
  return session_store.revoke(token)
