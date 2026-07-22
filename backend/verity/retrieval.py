"""Retrieve-before-generate: before asking the model anything, see whether
the paper answers the reader's selection itself. A retrieved answer is a
verbatim quote from the paper (high trust, no model, no cost); only when this
finds nothing does resolution fall through to generation.
"""

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .models import Document, Node


@dataclass
class Retrieved:
    content: str
    label: str
    anchor: str
    section_label: str


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower().strip(".,;:()[]")


def retrieve_selection(session: Session, doc: Document, selection: str) -> Retrieved | None:
    """Match a selected span against objects the paper already defines: a
    named theorem/lemma, a section title, or a symbol with a grounded
    definition. Exact-ish matching only — a loose match here would be a
    confident wrong answer, which is worse than falling through to a flagged
    generation."""
    target = _norm(selection)
    if len(target) < 2:
        return None

    nodes = session.query(Node).filter_by(document_id=doc.id).all()

    # Prefer the most specific match: a grounded definition beats a bare title.
    best: Retrieved | None = None
    for node in nodes:
        label = _norm(node.label)
        if not label:
            continue
        if node.kind in ("theorem", "section") and label and label == target and node.excerpt:
            return Retrieved(
                content=node.excerpt,
                label=node.label,
                anchor=node.html_anchor,
                section_label=node.data.get("section_label", "") if node.data else "",
            )
        if node.kind == "symbol" and label == target:
            status = (node.data or {}).get("definition_status")
            if node.excerpt and status in ("grounded", "inferred"):
                best = Retrieved(
                    content=node.excerpt,
                    label=node.label,
                    anchor=node.definition_anchor,
                    section_label=(node.data or {}).get("section_label", ""),
                )
    return best
