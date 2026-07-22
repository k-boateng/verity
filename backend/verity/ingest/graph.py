"""Merge the HTML and LaTeX passes into graph rows.

The HTML pass is authoritative for anchors and excerpts (it's what the
reader displays). The LaTeX pass fills in what the HTML can't provide:
macro definitions and symbol candidates for the notation sheet, and
richer bibliography text when the HTML bibliography is missing.
"""

from dataclasses import dataclass, field

from .html import ProcessedHtml, normalize_math
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
        _add_symbols(graph, latex, processed.math_by_section)

    return graph


def _sections_containing(needle: str, math_by_section: dict[str, str]) -> list[str]:
    """Sections whose math mentions this token — the basis for showing only
    the notation that's currently on the reader's screen."""
    norm = normalize_math(needle)
    if not norm:
        return []
    return [anchor for anchor, blob in math_by_section.items() if norm in blob]


def _is_structured_symbol(body: str) -> bool:
    """A meaningful notation symbol has structure — a sub/superscript or a
    math-alphabet command. A bare letter (the expansion of a plumbing macro
    like \\kq -> q) is noise the reader never registers as notation."""
    return any(
        marker in body
        for marker in ("_", "^", "\\mathbb", "\\mathcal", "\\mathbf", "\\mathrm", "\\text", "\\vec", "\\hat")
    )


def _render_math(latex_src: str) -> str:
    """Render a LaTeX symbol fragment to MathML so the notation sheet shows the
    actual symbol (d_k) rather than its source form (\\dmodel). Best-effort;
    an unrenderable fragment falls back to a plain-text label downstream."""
    try:
        from latex2mathml.converter import convert

        return convert(latex_src)
    except Exception:
        return ""


def _add_symbols(
    graph: GraphData, latex: LatexInfo, math_by_section: dict[str, str] | None = None
) -> None:
    """Seed the notation sheet with the symbols the reader actually sees in the
    rendered math. Definitions are deliberately left empty here — the macro
    body is not a definition, it's the same symbol spelled another way. Real,
    grounded definitions are filled in later by the resolution layer; until
    then each entry carries only its rendered form and where it appears."""
    added: set[str] = set()

    def add(display_latex: str, key: str, source: str, extra: dict) -> None:
        graph.nodes.append(
            {
                "kind": "symbol",
                "label": display_latex,
                "html_anchor": "",
                "definition_anchor": "",
                "excerpt": "",  # no definition yet — never fabricate one
                "data": {
                    "source": source,
                    "label_mathml": _render_math(display_latex),
                    "definition_status": "unresolved",
                    "sections": _sections_containing(key, math_by_section or {}),
                    **extra,
                },
            }
        )
        added.add(key)

    # Macros: the reader sees the *expansion*, so that's the label; the macro
    # name (\dmodel) is internal plumbing and never shown.
    for name, body in latex.macros.items():
        if not body or len(name) > 24 or len(body) > 60:
            continue
        if "#" in body:  # parameterized macros are commands, not notation
            continue
        if not _is_structured_symbol(body):  # skip bare-letter plumbing (\kq -> q)
            continue
        if body in added:
            continue
        add(body, body, "macro", {"macro_name": f"\\{name}"})

    # Scanned math tokens: the token is already the rendered symbol.
    for sym in latex.symbols:
        token = sym["token"]
        if token in added:
            continue
        add(token, token, "math_scan", {"count": sym["count"]})
