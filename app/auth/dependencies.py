"""인증 관련 FastAPI 의존성.

라우터에서 ``Depends(require_admin)``으로 쓰기 권한을 보호한다.
인증되지 않은 요청은 HTTP 403 Forbidden을 반환한다.

Ref: https://fastapi.tiangolo.com/tutorial/dependencies/
     https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
"""
from __future__ import annotations

from fastapi import Cookie, HTTPException

from app.auth.config import SESSION_COOKIE_NAME
from app.auth.service import validate_session


def require_admin(
  session_token: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> str:
  """관리자 인증 여부를 확인하는 의존성.

  인증된 사용자의 username을 반환한다.
  세션 쿠키가 없거나 유효하지 않으면 403을 발생시킨다.
  """
  if session_token is None:
    raise HTTPException(
      status_code=403,
      detail="로그인이 필요합니다.",
    )
  username = validate_session(session_token)
  if username is None:
    raise HTTPException(
      status_code=403,
      detail="세션이 만료되었습니다. 다시 로그인해 주세요.",
    )
  return username
