"""Ingestion: turn an arXiv paper into a stored HTML rendering plus a
dependency graph of resolvable objects (sections, equations, citations,
symbols, ...).

The HTML rendering (LaTeXML, via arxiv.org/html or ar5iv) is the display
source and the anchor space; the LaTeX source supplies what the HTML
alone can't (macro definitions, theorem statements, symbol candidates).
"""

from .pipeline import IngestError, ingest

__all__ = ["ingest", "IngestError"]
