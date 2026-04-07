from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.models.blocks import BlockDocument
from app.repositories.sqlite_blocks import SQLiteBlockRepository

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "data" / "blocks.sqlite3"

app = FastAPI(title="Project Manager")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
repository = SQLiteBlockRepository(DB_FILE)
repository.initialize()


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Render the notion-like block page."""

    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/documents")
def list_documents() -> list[dict[str, str]]:
    """Return all available block documents."""

    return repository.list_documents()


@app.get("/api/documents/{document_id}", response_model=BlockDocument)
def get_document(document_id: str) -> BlockDocument:
    """Return one block document by id."""

    document = repository.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return document
