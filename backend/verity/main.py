from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from . import config, db
from .ingest import IngestError, ingest
from .models import Document, Edge, Node

app = FastAPI(title="Verity API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    db.init_db()


class IngestRequest(BaseModel):
    arxiv_id: str


def _doc_summary(doc: Document) -> dict:
    return {
        "id": doc.id,
        "arxiv_id": doc.arxiv_id,
        "title": doc.title,
        "authors": doc.authors,
        "status": doc.status,
        "error": doc.error,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@app.post("/api/documents")
def create_document(req: IngestRequest) -> dict:
    session = db.get_session()
    try:
        doc = ingest(session, req.arxiv_id)
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        session.close()
    return _doc_summary(doc)


@app.get("/api/documents")
def list_documents() -> list[dict]:
    session = db.get_session()
    try:
        docs = session.query(Document).order_by(Document.created_at.desc()).all()
        return [_doc_summary(d) for d in docs]
    finally:
        session.close()


def _get_doc(session, doc_id: int) -> Document:
    doc = session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return doc


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: int) -> dict:
    session = db.get_session()
    try:
        return _doc_summary(_get_doc(session, doc_id))
    finally:
        session.close()


@app.get("/api/documents/{doc_id}/html", response_class=HTMLResponse)
def get_document_html(doc_id: int) -> str:
    session = db.get_session()
    try:
        doc = _get_doc(session, doc_id)
    finally:
        session.close()
    path = Path(doc.html_path) if doc.html_path else None
    if path is None or not path.exists():
        raise HTTPException(status_code=409, detail=f"document not ready (status: {doc.status})")
    return path.read_text(encoding="utf-8")


@app.get("/api/documents/{doc_id}/nodes")
def get_document_nodes(doc_id: int) -> dict:
    session = db.get_session()
    try:
        doc = _get_doc(session, doc_id)
        nodes = session.query(Node).filter_by(document_id=doc.id).all()
        edges = session.query(Edge).filter_by(document_id=doc.id).all()
        return {
            "nodes": [
                {
                    "id": n.id,
                    "kind": n.kind,
                    "label": n.label,
                    "html_anchor": n.html_anchor,
                    "definition_anchor": n.definition_anchor,
                    "excerpt": n.excerpt,
                    "data": n.data,
                }
                for n in nodes
            ],
            "edges": [
                {"source": e.source_node_id, "target": e.target_node_id, "kind": e.kind}
                for e in edges
            ],
        }
    finally:
        session.close()


@app.get("/api/assets/{safe_id}/{asset_path:path}")
def get_asset(safe_id: str, asset_path: str) -> FileResponse:
    base = (config.DOCUMENTS_DIR / safe_id / "assets").resolve()
    target = (base / asset_path).resolve()
    if not str(target).startswith(str(base)) or not target.exists():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(target)
