from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
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


class DocumentTitleUpdate(BaseModel):
    title: str


@app.post("/api/documents", status_code=201)
def create_document() -> dict[str, str]:
    """Create a new empty document and return its info."""

    return repository.create_document()


@app.patch("/api/documents/{document_id}")
def update_document_title(document_id: str, body: DocumentTitleUpdate) -> dict[str, str]:
    """Update the title of an existing document."""

    if not repository.update_document_title(document_id, body.title):
        raise HTTPException(status_code=404, detail="Document not found")

    return {"id": document_id, "title": body.title}


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(document_id: str) -> None:
    """Delete a document and all its blocks."""

    if not repository.delete_document(document_id):
        raise HTTPException(status_code=404, detail="Document not found")
