import shutil
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
from .models import Chat, Document, Edge, Node, utcnow


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


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int) -> dict:
    session = db.get_session()
    try:
        doc = _get_doc(session, doc_id)
        arxiv_id = doc.arxiv_id
        session.delete(doc)  # cascades to nodes, edges, chats
        session.commit()
    finally:
        session.close()
    doc_dir = config.DOCUMENTS_DIR / arxiv_id.replace("/", "_")
    if doc_dir.exists():
        shutil.rmtree(doc_dir, ignore_errors=True)
    return {"deleted": doc_id}


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

def _friendly_error(exc: Exception) -> str:
    """Turn a raw provider error into something a reader should see. Free-tier
    rate limits are common, so they get their own clear message."""
    s = str(exc).lower()
    if any(k in s for k in ("429", "resource_exhausted", "retryinfo", "quota", "rate limit")):
        return "The free-tier model is rate-limited right now — wait a minute and try again."
    return "Something went wrong reaching the model. Try again in a moment."


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
        return {"mode": "error", "content": _friendly_error(exc), "label": "", "anchor": ""}

    abstained = llm_tasks.is_abstention(answer)
    return {
        "mode": "abstained" if abstained else "generated",
        "content": llm_tasks.ABSTAIN_MESSAGE if abstained else answer,
        "label": "",
        "anchor": "",
        "model": get_provider().name,
    }


# --- Symbol definitions ---------------------------------------------------

@app.post("/api/documents/{doc_id}/nodes/{node_id}/define")
def define_symbol(doc_id: int, node_id: int) -> dict:
    """Resolve a symbol's meaning on demand, grounded in the excerpts where it
    appears, and cache the result on the node. Retrieve-before-generate: the
    excerpts come from the paper; only the summarizing is generated."""
    session = db.get_session()
    try:
        node = session.get(Node, node_id)
        if node is None or node.document_id != doc_id or node.kind != "symbol":
            raise HTTPException(status_code=404, detail="symbol not found")

        data = dict(node.data or {})
        # already resolved — return the cache
        if data.get("definition_status") in ("grounded", "inferred", "undefined"):
            return {"id": node.id, "excerpt": node.excerpt, "data": data}

        provider = get_provider()
        if not provider.is_configured():
            return {"id": node.id, "excerpt": "", "data": {**data, "definition_status": "unresolved"}}

        doc = session.get(Document, doc_id)
        excerpts = retrieval.symbol_excerpts(doc.html_path if doc else "", node.label)

        if not excerpts:
            data["definition_status"] = "undefined"
            node.data = data
            session.commit()
            return {"id": node.id, "excerpt": "", "data": data}

        try:
            answer = llm_tasks.define_symbol(
                provider, symbol=node.label, excerpts="\n\n".join(excerpts), title=doc.title if doc else ""
            )
        except Exception as exc:
            return {"id": node.id, "excerpt": "", "data": {**data, "error": _friendly_error(exc)}}

        if not answer or answer.strip().lower().startswith("not explicitly defined"):
            data["definition_status"] = "undefined"
            node.excerpt = ""
        else:
            data["definition_status"] = "grounded"
            node.excerpt = answer.strip()
        node.data = data
        session.commit()
        return {"id": node.id, "excerpt": node.excerpt, "data": data}
    finally:
        session.close()


# --- Equation resolution --------------------------------------------------

class ExplainEquationRequest(BaseModel):
    latex: str
    context: str = ""
    symbols: list[str] = []


@app.post("/api/documents/{doc_id}/explain-equation")
def explain_equation(doc_id: int, req: ExplainEquationRequest) -> dict:
    if not req.latex.strip():
        raise HTTPException(status_code=422, detail="no equation")
    provider = get_provider()
    if not provider.is_configured():
        return {"mode": "unconfigured", "content": ""}

    session = db.get_session()
    try:
        title = _get_doc(session, doc_id).title
    finally:
        session.close()

    try:
        answer = llm_tasks.explain_equation(
            provider,
            latex=req.latex,
            context=req.context,
            symbols=req.symbols,
            title=title,
        )
    except Exception as exc:
        return {"mode": "error", "content": _friendly_error(exc)}

    abstained = llm_tasks.is_abstention(answer)
    return {
        "mode": "abstained" if abstained else "generated",
        "content": llm_tasks.ABSTAIN_MESSAGE if abstained else answer,
    }


# --- Anchored chat (persisted server-side) --------------------------------

_CHAT_SYSTEM = (
    "You are Verity, embedded in a scientific paper, having a short focused "
    "conversation anchored to a specific passage. Answer the reader's questions "
    "clearly and helpfully, drawing on BOTH the anchored context and your general "
    "knowledge of the field. Ground any claim about what THIS paper specifically "
    "does, defines, or reports in the provided context; but for concepts, "
    "background, and 'why' questions, use standard knowledge of the field — do "
    "NOT refuse just because the anchored passage doesn't restate the answer. The "
    "passage is context, not a limit on what you may explain. Be concise. Write in "
    "plain prose — no markdown bold, headers, or bullet lists — but write any math "
    "in LaTeX: inline as $...$ and display equations as $$...$$."
)


def _build_chat_prompt(title: str, chat: Chat, messages: list[dict]) -> str:
    seed = (
        f'Paper: "{title}"\nSection: {chat.section_label or "unknown"}\n\n'
        f"Anchored paragraph:\n\"\"\"\n{(chat.paragraph or '').strip()}\n\"\"\"\n\n"
    )
    if chat.selection.strip():
        seed += f'The reader first highlighted: "{chat.selection.strip()}"\n\n'
    deps = chat.dependencies or []
    if deps:
        seed += "Nearby resolved references:\n" + "\n".join(f"- {d}" for d in deps[:12]) + "\n\n"
    transcript = seed + "Conversation so far:\n"
    for m in messages:
        who = "Reader" if m.get("role") == "user" else "Verity"
        transcript += f"{who}: {m.get('content', '').strip()}\n"
    return transcript + "Verity:"


def _chat_summary(chat: Chat) -> dict:
    msgs = chat.messages or []
    return {
        "id": chat.id,
        "selection": chat.selection,
        "section_label": chat.section_label,
        "section_anchor": chat.section_anchor,
        "question_count": sum(1 for m in msgs if m.get("role") == "user"),
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
    }


def _chat_full(chat: Chat) -> dict:
    return {
        "id": chat.id,
        "document_id": chat.document_id,
        "selection": chat.selection,
        "section_label": chat.section_label,
        "section_anchor": chat.section_anchor,
        "paragraph": chat.paragraph,
        "dependencies": chat.dependencies or [],
        "messages": chat.messages or [],
    }


class ChatCreateRequest(BaseModel):
    selection: str
    section_label: str = ""
    section_anchor: str = ""
    paragraph: str = ""
    dependencies: list[str] = []


@app.get("/api/documents/{doc_id}/chats")
def list_chats(doc_id: int) -> list[dict]:
    session = db.get_session()
    try:
        _get_doc(session, doc_id)
        chats = (
            session.query(Chat)
            .filter_by(document_id=doc_id)
            .order_by(Chat.updated_at.desc())
            .all()
        )
        return [_chat_summary(c) for c in chats]
    finally:
        session.close()


@app.post("/api/documents/{doc_id}/chats")
def create_or_open_chat(doc_id: int, req: ChatCreateRequest) -> dict:
    """Open the existing conversation for this passage if there is one,
    otherwise start a fresh thread. Keyed by (document, selection, section)."""
    session = db.get_session()
    try:
        _get_doc(session, doc_id)
        existing = (
            session.query(Chat)
            .filter_by(
                document_id=doc_id,
                selection=req.selection,
                section_anchor=req.section_anchor,
            )
            .one_or_none()
        )
        if existing is not None:
            return _chat_full(existing)
        chat = Chat(
            document_id=doc_id,
            selection=req.selection,
            section_label=req.section_label,
            section_anchor=req.section_anchor,
            paragraph=req.paragraph,
            dependencies=req.dependencies,
            messages=[],
        )
        session.add(chat)
        session.commit()
        return _chat_full(chat)
    finally:
        session.close()


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: int) -> dict:
    session = db.get_session()
    try:
        chat = session.get(Chat, chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="chat not found")
        return _chat_full(chat)
    finally:
        session.close()


class ChatMessageRequest(BaseModel):
    content: str


@app.post("/api/chats/{chat_id}/message")
def send_chat_message(chat_id: int, req: ChatMessageRequest):
    """Append the reader's message, then stream the reply. The server persists
    both sides, so the thread is durable and reopenable."""
    provider = get_provider()
    if not provider.is_configured():
        raise HTTPException(status_code=409, detail="no model configured")

    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="empty message")

    session = db.get_session()
    try:
        chat = session.get(Chat, chat_id)
        if chat is None:
            raise HTTPException(status_code=404, detail="chat not found")
        doc = session.get(Document, chat.document_id)
        title = doc.title if doc else ""
        messages = list(chat.messages or [])
        messages.append({"role": "user", "content": content})
        chat.messages = messages
        chat.updated_at = utcnow()
        session.commit()
        transcript = _build_chat_prompt(title, chat, messages)
    finally:
        session.close()

    # The generator runs after this function returns, so it can't use the
    # request-scoped session; it opens its own to persist the reply.
    def token_stream():
        acc = ""
        try:
            for piece in provider.stream(_CHAT_SYSTEM, transcript, max_tokens=900):
                acc += piece
                yield piece
        except Exception as exc:
            fallback = "\n\n" + _friendly_error(exc)
            acc += fallback
            yield fallback
        finally:
            s = db.get_session()
            try:
                c = s.get(Chat, chat_id)
                if c is not None:
                    msgs = list(c.messages or [])
                    msgs.append({"role": "assistant", "content": acc})
                    c.messages = msgs
                    c.updated_at = utcnow()
                    s.commit()
            finally:
                s.close()

    return StreamingResponse(token_stream(), media_type="text/plain; charset=utf-8")
