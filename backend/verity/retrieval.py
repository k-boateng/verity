"""Retrieve-before-generate: before asking the model anything, see whether
the paper answers the reader's selection itself. A retrieved answer is a
verbatim quote from the paper (high trust, no model, no cost); only when this
finds nothing does resolution fall through to generation.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from .ingest.html import normalize_math
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


def symbol_excerpts(html_path: str, label: str, limit: int = 4) -> list[str]:
    """Prose paragraphs where a symbol actually appears, pulled from the stored
    rendering. This is the grounding context handed to the model so a symbol
    definition is based on how the paper uses it, not invented."""
    path = Path(html_path) if html_path else None
    if path is None or not path.exists():
        return []
    target = normalize_math(label)
    if not target:
        return []

    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    seen: set[str] = set()
    excerpts: list[str] = []
    for math in soup.find_all("math"):
        alt = math.get("alttext", "")
        if not alt or target not in normalize_math(alt):
            continue
        para = math.find_parent(class_="ltx_p") or math.find_parent("p")
        if para is None:
            continue
        text = re.sub(r"\s+", " ", para.get_text(" ", strip=True)).strip()
        key = text[:80]
        if not text or key in seen:
            continue
        seen.add(key)
        excerpts.append(text[:400])
        if len(excerpts) >= limit:
            break
    return excerpts


def section_text(html_path: str, anchor: str, limit: int = 6000) -> str:
    """The prose of one section, pulled from the stored rendering. This is the
    grounding source for a checkpoint — key points are drawn from here, never
    invented."""
    path = Path(html_path) if html_path else None
    if path is None or not path.exists():
        return ""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    el = soup.find(id=anchor)
    if el is None:
        return ""
    text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
    return text[:limit]
