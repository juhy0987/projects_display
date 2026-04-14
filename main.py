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
app.add_middleware(
  CORSMiddleware,
  allow_origins=_allow_origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

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
