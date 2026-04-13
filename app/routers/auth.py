"""관리자 인증 라우터.

엔드포인트:
  POST /api/auth/login   — 자격 증명 검증 후 세션 쿠키 발급
  POST /api/auth/logout  — 세션 쿠키 해제
  GET  /api/auth/status   — 현재 인증 상태 조회

세션 쿠키 설정은 OWASP Session Management Cheat Sheet를 따른다.
Ref: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel

from app.auth.config import (
  COOKIE_HTTPONLY,
  COOKIE_SAMESITE,
  COOKIE_SECURE,
  SESSION_COOKIE_NAME,
  SESSION_MAX_AGE,
)
from app.auth.service import authenticate, logout, validate_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
  username: str
  password: str


class LoginResponse(BaseModel):
  message: str
  username: str


class StatusResponse(BaseModel):
  authenticated: bool
  username: str | None = None


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, response: Response) -> LoginResponse:
  """관리자 로그인 — 세션 쿠키를 발급한다."""
  token = authenticate(body.username, body.password)
  if token is None:
    raise HTTPException(
      status_code=401,
      detail="아이디 또는 비밀번호가 올바르지 않습니다.",
    )
  response.set_cookie(
    key=SESSION_COOKIE_NAME,
    value=token,
    max_age=SESSION_MAX_AGE,
    httponly=COOKIE_HTTPONLY,
    samesite=COOKIE_SAMESITE,
    secure=COOKIE_SECURE,
    path="/",
  )
  return LoginResponse(message="로그인 성공", username=body.username)


@router.post("/logout")
def do_logout(
  response: Response,
  session_token: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> dict[str, str]:
  """관리자 로그아웃 — 세션 쿠키를 삭제한다."""
  if session_token:
    logout(session_token)
  response.delete_cookie(
    key=SESSION_COOKIE_NAME,
    path="/",
    httponly=COOKIE_HTTPONLY,
    samesite=COOKIE_SAMESITE,
    secure=COOKIE_SECURE,
  )
  return {"message": "로그아웃 완료"}


@router.get("/status", response_model=StatusResponse)
def auth_status(
  session_token: str | None = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> StatusResponse:
  """현재 인증 상태를 반환한다."""
  if session_token is None:
    return StatusResponse(authenticated=False)
  username = validate_session(session_token)
  if username is None:
    return StatusResponse(authenticated=False)
  return StatusResponse(authenticated=True, username=username)
