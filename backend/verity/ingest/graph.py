"""Merge the HTML and LaTeX passes into graph rows.

The HTML pass is authoritative for anchors and excerpts (it's what the
reader displays). The LaTeX pass fills in what the HTML can't provide:
macro definitions and symbol candidates for the notation sheet, and
richer bibliography text when the HTML bibliography is missing.
"""

from dataclasses import dataclass, field

from .html import ProcessedHtml
from .latex import LatexInfo


@dataclass
class GraphData:
    nodes: list[dict] = field(default_factory=list)  # keyed later by html_anchor
    edges: list[dict] = field(default_factory=list)  # {source_anchor, target_anchor, kind}


def build(processed: ProcessedHtml, latex: LatexInfo | None) -> GraphData:
    graph = GraphData()
    seen_anchors: set[str] = set()

    for t in processed.targets:
        graph.nodes.append(
            {
                "kind": t.kind,
                "label": t.label,
                "html_anchor": t.anchor,
                "definition_anchor": t.anchor,
                "excerpt": t.excerpt_text,
                "data": {
                    "excerpt_html": t.excerpt_html,
                    "section_label": t.section_label,
                    "grounded": True,
                },
            }
        )
        seen_anchors.add(t.anchor)

    for occ in processed.occurrences:
        graph.edges.append(
            {
                "source_anchor": occ.section_anchor,
                "target_anchor": occ.target_anchor,
                "kind": occ.kind,
            }
        )

    if latex is not None:
        _add_symbols(graph, latex)

    return graph


def _add_symbols(graph: GraphData, latex: LatexInfo) -> None:
    """First-cut notation sheet: macro definitions are grounded (the macro
    body is a real definition from the source); repeated math tokens are
    listed but explicitly ungrounded until a definition span is verified —
    they render as the abstention state, never as a guess."""
    added: set[str] = set()

    for name, body in latex.macros.items():
        if len(name) > 24 or not body or len(body) > 120:
            continue
        if "#" in body:  # parameterized macros are commands, not notation
            continue
        token = f"\\{name}"
        graph.nodes.append(
            {
                "kind": "symbol",
                "label": token,
                "html_anchor": "",
                "definition_anchor": "",
                "excerpt": body,
                "data": {"source": "macro", "grounded": True, "section_label": "preamble"},
            }
        )
        added.add(token)

    for sym in latex.symbols:
        token = sym["token"]
        if token in added:
            continue
        graph.nodes.append(
            {
                "kind": "symbol",
                "label": token,
                "html_anchor": "",
                "definition_anchor": "",
                "excerpt": "",  # empty excerpt = "not stated in this paper" (abstention)
                "data": {"source": "math_scan", "grounded": False, "count": sym["count"]},
            }
        )
        added.add(token)
