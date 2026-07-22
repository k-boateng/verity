from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from . import config, db, retrieval
from .ingest import IngestError, ingest
from .llm import get_provider
from .llm import tasks as llm_tasks
from .models import Document, Edge, Node


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Verity API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# --- Resolution (Ask) -----------------------------------------------------

class ResolveRequest(BaseModel):
    selection: str
    paragraph: str = ""
    section: str = ""
    dependencies: list[str] = []


@app.get("/api/config")
def get_config() -> dict:
    """Lets the frontend know whether generation is available, so the Ask UI
    can offer an honest 'set up a model' state instead of failing."""
    return {"llm_configured": get_provider().is_configured()}


@app.post("/api/documents/{doc_id}/resolve")
def resolve_selection(doc_id: int, req: ResolveRequest) -> dict:
    selection = req.selection.strip()
    if not selection:
        raise HTTPException(status_code=422, detail="empty selection")

    session = db.get_session()
    try:
        doc = _get_doc(session, doc_id)

        # 1. Retrieve: does the paper define this itself?
        hit = retrieval.retrieve_selection(session, doc, selection)
        if hit is not None:
            return {
                "mode": "retrieved",
                "content": hit.content,
                "label": hit.label,
                "anchor": hit.anchor,
                "section_label": hit.section_label,
            }

        # 2. Generate: only if the paper can't answer, and only if configured.
        provider = get_provider()
        if not provider.is_configured():
            return {"mode": "unconfigured", "content": "", "label": "", "anchor": ""}

        title = doc.title
    finally:
        session.close()

    try:
        answer = llm_tasks.resolve_selection(
            provider,
            selection=selection,
            paragraph=req.paragraph,
            section=req.section,
            title=title,
            dependencies=req.dependencies,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"generation failed: {exc}")

    abstained = llm_tasks.is_abstention(answer)
    return {
        "mode": "abstained" if abstained else "generated",
        "content": llm_tasks.ABSTAIN_MESSAGE if abstained else answer,
        "label": "",
        "anchor": "",
        "model": get_provider().name,
    }


class ChatRequest(BaseModel):
    messages: list[dict]  # [{role: "user"|"assistant", content: str}]
    paragraph: str = ""
    selection: str = ""
    section: str = ""
    dependencies: list[str] = []


@app.post("/api/documents/{doc_id}/chat")
def chat(doc_id: int, req: ChatRequest):
    """Anchored chat — the escape hatch. Streams a reply seeded warm with the
    paragraph, the selection, and the resolved dependencies."""
    provider = get_provider()
    if not provider.is_configured():
        raise HTTPException(status_code=409, detail="no model configured")

    session = db.get_session()
    try:
        doc = _get_doc(session, doc_id)
        title = doc.title
    finally:
        session.close()

    system = (
        "You are Verity, embedded in a scientific paper, having a short focused "
        "conversation anchored to one paragraph. Answer concisely and ground your "
        "answers in the paragraph and the resolved references provided. If something "
        "isn't supported by that context, say so plainly rather than guessing."
    )
    seed = (
        f'Paper: "{title}"\nSection: {req.section or "unknown"}\n\n'
        f"Anchored paragraph:\n\"\"\"\n{req.paragraph.strip()}\n\"\"\"\n\n"
    )
    if req.selection.strip():
        seed += f'The reader first highlighted: "{req.selection.strip()}"\n\n'
    if req.dependencies:
        seed += "Nearby resolved references:\n" + "\n".join(f"- {d}" for d in req.dependencies[:12]) + "\n\n"

    transcript = seed + "Conversation so far:\n"
    for m in req.messages:
        who = "Reader" if m.get("role") == "user" else "Verity"
        transcript += f"{who}: {m.get('content', '').strip()}\n"
    transcript += "Verity:"

    def token_stream():
        try:
            for piece in provider.stream(system, transcript, max_tokens=700):
                yield piece
        except Exception as exc:  # surface, don't hang the stream
            yield f"\n\n[error: {exc}]"

    return StreamingResponse(token_stream(), media_type="text/plain; charset=utf-8")
