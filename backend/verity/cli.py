import argparse
import json
import sys
from collections import Counter

from . import db
from .ingest import IngestError, ingest
from .models import Edge, Node


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verity", description="Verity ingestion CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    p_ingest = sub.add_parser("ingest", help="Ingest an arXiv paper by id or URL")
    p_ingest.add_argument("arxiv_id")
    p_ingest.add_argument("--json", dest="json_out", help="Write the graph to a JSON file")
    args = parser.parse_args(argv)

    db.init_db()
    session = db.get_session()
    try:
        doc = ingest(session, args.arxiv_id)
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    nodes = session.query(Node).filter_by(document_id=doc.id).all()
    edges = session.query(Edge).filter_by(document_id=doc.id).all()
    kinds = Counter(n.kind for n in nodes)

    print(f"{doc.arxiv_id}: {doc.title}")
    print(f"status: {doc.status}")
    print("nodes: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    print(f"edges: {len(edges)}")

    if args.json_out:
        payload = {
            "document": {"arxiv_id": doc.arxiv_id, "title": doc.title, "authors": doc.authors},
            "nodes": [
                {
                    "id": n.id,
                    "kind": n.kind,
                    "label": n.label,
                    "html_anchor": n.html_anchor,
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
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"graph written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
