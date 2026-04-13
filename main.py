from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.routers import auth, blocks, database, documents, files, notion_import, upload, url_embed

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Project Manager")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(blocks.router)
app.include_router(database.router)
app.include_router(upload.router)
app.include_router(files.router)
app.include_router(url_embed.router)
app.include_router(notion_import.router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
  """Render the notion-like block page."""
  return templates.TemplateResponse(request=request, name="index.html")
