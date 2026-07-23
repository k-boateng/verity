import hashlib

from sqlalchemy.orm import Session

from .. import config
from ..models import Document, Edge, Node
from . import arxiv, graph as graph_mod, html as html_mod, latex as latex_mod
from . import pdf as pdf_mod


class IngestError(Exception):
    pass


def ingest(session: Session, raw_id: str, force: bool = False) -> Document:
    try:
        arxiv_id = arxiv.normalize_arxiv_id(raw_id)
    except arxiv.FetchError as exc:
        raise IngestError(str(exc)) from exc

    doc = session.query(Document).filter_by(arxiv_id=arxiv_id).one_or_none()
    if doc is not None and doc.status == "ready" and not force:
        return doc
    if doc is None:
        doc = Document(arxiv_id=arxiv_id, status="fetched")
        session.add(doc)
        session.commit()

    try:
        _run(session, doc)
        doc.status = "ready"
        doc.error = ""
    except (arxiv.FetchError, IngestError) as exc:
        doc.status = "failed"
        doc.error = str(exc)
        session.commit()
        raise IngestError(str(exc)) from exc
    session.commit()
    return doc


def _run(session: Session, doc: Document) -> None:
    safe_id = doc.arxiv_id.replace("/", "_")
    doc_dir = config.document_dir(doc.arxiv_id)

    fetched = arxiv.fetch(doc.arxiv_id, doc_dir)

    latex_info = None
    if fetched.source_dir is not None:
        main_tex = arxiv.find_main_tex(fetched.source_dir)
        if main_tex is not None:
            tex = arxiv.inline_inputs(main_tex)
            # .bbl bibliographies live outside the main file; append them
            for bbl in fetched.source_dir.rglob("*.bbl"):
                try:
                    tex += "\n" + bbl.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass
            latex_info = latex_mod.parse(tex)

    byline = ", ".join(fetched.authors)
    processed = html_mod.process(fetched.html, safe_id, byline=byline)
    doc.title = fetched.title or processed.title or doc.arxiv_id
    doc.authors = processed.authors
    doc.status = "parsed"
    session.commit()

    for src in processed.image_srcs:
        arxiv.fetch_asset(fetched.html_base_url, src, doc_dir / "assets" / src)

    processed_path = doc_dir / "paper.html"
    processed_path.write_text(processed.article_html, encoding="utf-8")
    doc.html_path = str(processed_path)

    graph = graph_mod.build(processed, latex_info)
    _store_graph(session, doc, graph)


def _store_graph(session: Session, doc: Document, graph) -> None:
    session.query(Edge).filter_by(document_id=doc.id).delete()
    session.query(Node).filter_by(document_id=doc.id).delete()
    session.flush()

    node_by_anchor: dict[str, Node] = {}
    for n in graph.nodes:
        node = Node(document_id=doc.id, **n)
        session.add(node)
        if n["html_anchor"]:
            node_by_anchor[n["html_anchor"]] = node
    session.flush()

    for e in graph.edges:
        source = node_by_anchor.get(e["source_anchor"])
        target = node_by_anchor.get(e["target_anchor"])
        if target is None:
            continue
        session.add(
            Edge(
                document_id=doc.id,
                source_node_id=source.id if source else target.id,
                target_node_id=target.id,
                kind=e["kind"],
            )
        )
    session.flush()


def ingest_pdf(session: Session, filename: str, pdf_bytes: bytes) -> Document:
    """Ingest an uploaded PDF into the same schema as an arXiv paper. Keyed by
    content hash, so re-uploading the same file reuses the existing document."""
    if len(pdf_bytes) > config.PDF_MAX_BYTES:
        mb = config.PDF_MAX_BYTES // (1024 * 1024)
        raise IngestError(f"PDF is too large (limit {mb} MB)")

    try:
        pages = pdf_mod.page_count(pdf_bytes)
    except Exception as exc:
        raise IngestError(f"couldn't open the PDF: {exc}") from exc
    if pages > config.PDF_MAX_PAGES:
        raise IngestError(
            f"PDF has {pages} pages; the limit is {config.PDF_MAX_PAGES}. "
            "Verity is tuned for papers — very long documents aren't supported yet."
        )

    key = "pdf-" + hashlib.sha1(pdf_bytes).hexdigest()[:16]
    doc = session.query(Document).filter_by(arxiv_id=key).one_or_none()
    if doc is not None and doc.status == "ready":
        return doc
    if doc is None:
        doc = Document(arxiv_id=key, source="pdf", filename=filename, status="fetched")
        session.add(doc)
        session.commit()

    try:
        doc_dir = config.document_dir(key)
        (doc_dir / "source.pdf").write_bytes(pdf_bytes)

        processed = pdf_mod.extract(pdf_bytes)
        doc.title = processed.title or filename or key
        doc.authors = processed.authors

        html_path = doc_dir / "paper.html"
        html_path.write_text(processed.article_html, encoding="utf-8")
        doc.html_path = str(html_path)

        graph = graph_mod.build(processed, None)
        _store_graph(session, doc, graph)

        doc.status = "ready"
        doc.error = ""
    except (pdf_mod.PdfError, IngestError) as exc:
        doc.status = "failed"
        doc.error = str(exc)
        session.commit()
        raise IngestError(str(exc)) from exc
    session.commit()
    return doc
