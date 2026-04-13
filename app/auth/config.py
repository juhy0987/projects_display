"""관리자 인증 설정.

환경 변수를 통해 관리자 자격 증명과 세션 정책을 설정한다.
``ADMIN_PASSWORD``가 설정되지 않으면 프로세스 시작 시 임의 비밀번호를
생성하고 표준 출력에 경고를 표시한다.

Ref: https://fastapi.tiangolo.com/advanced/settings/
     https://docs.python.org/3/library/os.html#os.environ
     https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
"""
from __future__ import annotations

import os
import secrets
import sys

# 관리자 계정 자격 증명
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")

_password_from_env = os.getenv("ADMIN_PASSWORD")
if _password_from_env:
  ADMIN_PASSWORD: str = _password_from_env
else:
  ADMIN_PASSWORD = secrets.token_urlsafe(16)
  print(
    f"[WARNING] ADMIN_PASSWORD 환경변수가 설정되지 않았습니다. "
    f"임시 비밀번호가 생성되었습니다: {ADMIN_PASSWORD}",
    file=sys.stderr,
  )

# 세션 정책
SESSION_COOKIE_NAME: str = "session_token"
SESSION_MAX_AGE: int = int(os.getenv("SESSION_MAX_AGE", "3600"))  # 기본 1시간(초)

# 쿠키 보안 설정
# Ref: https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies#security
COOKIE_HTTPONLY: bool = True
COOKIE_SAMESITE: str = "lax"
# HTTPS 환경에서만 True로 설정 (개발 환경에서는 False)
COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"
