from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import auth, blocks, database, documents, files, notion_import, upload, url_embed

BASE_DIR = Path(__file__).resolve().parent

# FE/BE 분리 이후 be 는 API 전용 역할이며, 프론트 템플릿/자산은 fe/ 에서 관리한다.
# 단, 업로드 이미지(static/uploads)와 사용자 파일(static/files)은 서버 기록 자원이므로
# be 가 그대로 제공한다. (Ref: https://fastapi.tiangolo.com/tutorial/static-files/)
app = FastAPI(title="Project Manager")

# CORS 설정: FE 가 별도 오리진에서 서빙되므로 쿠키 기반 세션을 위해
# allow_credentials=True 와 명시적 오리진 화이트리스트가 필요하다.
# FE_ALLOWED_ORIGINS 환경변수로 쉼표 구분 오리진을 주입할 수 있다.
# (Ref: https://fastapi.tiangolo.com/tutorial/cors/)
_DEFAULT_ORIGINS = "http://localhost:5173,http://localhost:3000"
_allow_origins = [
  o.strip()
  for o in os.environ.get("FE_ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",")
  if o.strip()
]
# allow_credentials=True 와 와일드카드("*") 오리진은 CORS 스펙상 동시에 사용할 수
# 없으며, Starlette CORSMiddleware 는 RuntimeError 를 발생시킨다.
# 운영 실수(FE_ALLOWED_ORIGINS=*)를 방어하기 위해 와일드카드가 감지되면 기본값으로
# 폴백한다. (Ref: https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS#credentialed_requests_and_wildcards)
if "*" in _allow_origins:
  _allow_origins = [o.strip() for o in _DEFAULT_ORIGINS.split(",") if o.strip()]
app.add_middleware(
  CORSMiddleware,
  allow_origins=_allow_origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

# 신규 배포 환경에서 static/ 디렉터리가 아직 생성되지 않았을 수 있다.
# StaticFiles 는 디렉터리 부재 시 RuntimeError 를 발생시키므로 선제 생성한다.
# (Ref: https://www.starlette.io/staticfiles/)
_static_dir = BASE_DIR / "static"
_static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(blocks.router)
app.include_router(database.router)
app.include_router(upload.router)
app.include_router(files.router)
app.include_router(url_embed.router)
app.include_router(notion_import.router)


@app.get("/api/health")
def health() -> dict[str, str]:
  """헬스체크 엔드포인트.

  FE/BE 분리 후 `/` 루트 HTML 응답을 제거했기 때문에,
  배포 환경의 liveness/readiness probe 용도로 단순 200 응답을 제공한다.
  """
  return {"status": "ok"}
