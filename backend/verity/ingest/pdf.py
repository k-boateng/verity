"""PDF ingestion adapter.

PDF is a layout format, not a semantic one, so this is honest best-effort: we
recover the title, a section structure, paragraphs, and the reference list with
[N]-style citations linked back to it. That's enough for the reader, Ask, the
anchored chat, and checkpoints to all work. Math and fine cross-references are
deliberately out of scope here — without a LaTeX source they're glyph soup, and
the trust layer would rather show nothing than a guess.

The output is the same ProcessedHtml shape the arXiv/LaTeXML pass produces, so
everything downstream (graph build, storage, the whole reader) is identical.
"""

import html as html_lib
import re
from dataclasses import dataclass, field

import fitz

from .html import ProcessedHtml, RefOccurrence, Target

_BOLD_FLAG = 1 << 4
_HEADING_WORDS_MAX = 16
_REF_HEADINGS = re.compile(r"^\s*(references|bibliography|works cited)\s*$", re.IGNORECASE)
_NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")
_CITE_RUN = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]")


@dataclass
class Block:
    text: str
    size: float
    bold: bool
    page: int
    y: float
    x0: float

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass
class Section:
    anchor: str
    label: str  # "§1", "§2.1", or the heading text
    tag: str  # what renders in the ltx_tag span
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    is_refs: bool = False


class PdfError(Exception):
    pass


def page_count(pdf_bytes: bytes) -> int:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc.page_count


def extract(pdf_bytes: bytes) -> ProcessedHtml:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        blocks = _collect_blocks(doc)
        meta_title = (doc.metadata or {}).get("title", "") or ""
    if not blocks:
        raise PdfError("no extractable text — this may be a scanned PDF")

    body_size = _body_size(blocks)
    title = _extract_title(blocks, body_size, meta_title)
    sections = _segment(blocks, body_size, title)
    references = _parse_references(sections)
    article_html, targets, occurrences = _render(title, sections, references)

    return ProcessedHtml(
        title=title,
        authors="",
        article_html=article_html,
        targets=targets,
        occurrences=occurrences,
        image_srcs=[],
        math_by_section={},
    )


# --- text collection ------------------------------------------------------

def _collect_blocks(doc: fitz.Document) -> list[Block]:
    """Flatten the document to text blocks in reading order. A cheap two-column
    heuristic (left-half blocks before right-half, per page) handles the common
    two-column paper layout; single-column falls out as a special case."""
    blocks: list[Block] = []
    for pno in range(doc.page_count):
        page = doc.load_page(pno)
        width = page.rect.width
        raw = [b for b in page.get_text("dict").get("blocks", []) if b.get("type") == 0]

        def order_key(b: dict) -> tuple:
            x0, y0 = b["bbox"][0], b["bbox"][1]
            column = 0 if x0 < width * 0.5 else 1
            return (column, round(y0))

        for b in sorted(raw, key=order_key):
            text, size, bold = _block_text(b)
            if text:
                blocks.append(
                    Block(text=text, size=size, bold=bold, page=pno, y=b["bbox"][1], x0=b["bbox"][0])
                )
    return blocks


def _block_text(block: dict) -> tuple[str, float, bool]:
    max_size = 0.0
    bold_chars = 0
    total_chars = 0
    joined = ""
    for line in block.get("lines", []):
        direction = line.get("dir", (1.0, 0.0))
        if abs(direction[1]) > 0.05:  # rotated/vertical text — margin stamps, not content
            continue
        line_text = "".join(span.get("text", "") for span in line.get("spans", []))
        for span in line.get("spans", []):
            n = len(span.get("text", ""))
            total_chars += n
            max_size = max(max_size, span.get("size", 0.0))
            if int(span.get("flags", 0)) & _BOLD_FLAG:
                bold_chars += n
        stripped = line_text.rstrip()
        if joined.endswith("-") and stripped:  # de-hyphenate line breaks
            joined = joined[:-1] + stripped.lstrip()
        elif joined:
            joined += " " + stripped.strip()
        else:
            joined = stripped.strip()
    text = re.sub(r"\s+", " ", joined).strip()
    bold = total_chars > 0 and bold_chars / total_chars > 0.6
    return text, round(max_size, 1), bold


def _body_size(blocks: list[Block]) -> float:
    weighted: dict[float, int] = {}
    for b in blocks:
        weighted[b.size] = weighted.get(b.size, 0) + len(b.text)
    return max(weighted, key=weighted.get) if weighted else 10.0


# --- structure ------------------------------------------------------------

def _extract_title(blocks: list[Block], body_size: float, meta_title: str) -> str:
    first_page = [
        b for b in blocks if b.page == 0 and not re.match(r"ar\s?xiv[:\s]", b.text, re.IGNORECASE)
    ]
    if not first_page:
        return meta_title.strip() or "Untitled document"
    top = max(first_page, key=lambda b: b.size)
    if top.size <= body_size + 0.5:
        return meta_title.strip() or top.text[:200]
    # merge adjacent same-size lines near the top (multi-line titles)
    parts = [b.text for b in first_page if abs(b.size - top.size) < 0.3 and b.y <= top.y + 120]
    title = " ".join(parts).strip() or top.text
    return title[:300]


def _looks_like_heading(block: Block, body_size: float, title: str) -> bool:
    text = block.text
    if not text or text == title or block.words > _HEADING_WORDS_MAX:
        return False
    if _REF_HEADINGS.match(text):
        return True
    numbered = bool(_NUMBERED.match(text))
    # Non-numbered candidates must read like a heading: start capitalized and
    # not end like a sentence. This drops title-page fragments ("…scholarly
    # works.") that happen to be short and bold.
    if not numbered:
        if text[-1] in ".,;:":
            return False
        first_alpha = next((c for c in text if c.isalpha()), "")
        if first_alpha and not first_alpha.isupper():
            return False
    bigger = block.size >= body_size + 1.0
    allcaps = text.isupper() and 2 <= len(text) <= 60
    if bigger and block.words <= 14:
        return True
    if block.bold and (numbered or allcaps):
        return True
    if numbered and block.size >= body_size and block.words <= 12:
        return True
    return False


def _segment(blocks: list[Block], body_size: float, title: str) -> list[Section]:
    sections: list[Section] = []
    counter = 0
    current: Section | None = None
    for b in blocks:
        if b.text == title:
            continue
        if _looks_like_heading(b, body_size, title):
            counter += 1
            is_refs = bool(_REF_HEADINGS.match(b.text))
            m = _NUMBERED.match(b.text)
            if m:
                tag = m.group(1)
                heading = b.text[m.end() - 1 :].strip() or b.text
                label = f"§{tag}"
            else:
                # No real section number — show the heading itself, no counter.
                tag = ""
                heading = b.text
                label = b.text if len(b.text) <= 40 else b.text[:40] + "…"
            current = Section(
                anchor=f"S{counter}", label=label, tag=tag, heading=heading, is_refs=is_refs
            )
            sections.append(current)
        else:
            if current is None:  # preamble before the first heading (abstract etc.)
                current = Section(anchor="S0", label="", tag="", heading="")
                sections.append(current)
            current.paragraphs.append(b.text)
    return [s for s in sections if s.paragraphs or s.heading]


# --- references & citations ----------------------------------------------

def _parse_references(sections: list[Section]) -> dict[str, str]:
    refs: dict[str, str] = {}
    ref_section = next((s for s in sections if s.is_refs), None)
    if ref_section is None:
        return refs
    blob = " ".join(ref_section.paragraphs).strip()

    if "[" in blob and _CITE_RUN.search(blob):
        # "[1] ... [2] ..." — split on bracketed numbers
        parts = re.split(r"\[(\d+)\]", blob)
        # parts = [pre, num, text, num, text, ...]
        for i in range(1, len(parts) - 1, 2):
            num = parts[i]
            text = parts[i + 1].strip(" .")
            if text:
                refs[num] = text[:600]
    else:
        # "1. ..." numbered, or one reference per paragraph
        numbered = re.findall(r"(?:^|\s)(\d{1,3})\.\s+(.+?)(?=\s\d{1,3}\.\s|$)", blob)
        if len(numbered) >= 2:
            for num, text in numbered:
                refs[num] = text.strip()[:600]
        else:
            for i, para in enumerate(ref_section.paragraphs, start=1):
                cleaned = re.sub(r"^\[?\d+\]?\.?\s*", "", para).strip()
                if cleaned:
                    refs[str(i)] = cleaned[:600]
    return refs


def _expand_cite_run(run: str) -> list[str]:
    nums: list[str] = []
    for part in re.split(r"\s*,\s*", run):
        rng = re.match(r"(\d+)\s*[–-]\s*(\d+)", part)
        if rng:
            lo, hi = int(rng.group(1)), int(rng.group(2))
            if hi - lo < 50:
                nums.extend(str(n) for n in range(lo, hi + 1))
        elif part.strip().isdigit():
            nums.append(part.strip())
    return nums


# --- rendering ------------------------------------------------------------

def _render(
    title: str, sections: list[Section], references: dict[str, str]
) -> tuple[str, list[Target], list[RefOccurrence]]:
    targets: list[Target] = []
    occurrences: list[RefOccurrence] = []

    for num, text in references.items():
        targets.append(
            Target(
                anchor=f"bib.bib{num}",
                kind="citation",
                label=f"[{num}]",
                excerpt_text=text,
                excerpt_html="",
                section_label="References",
            )
        )

    parts = ['<article class="ltx_document">']
    parts.append(f'<h1 class="ltx_title ltx_title_document">{html_lib.escape(title)}</h1>')

    for section in sections:
        if section.is_refs:
            continue
        parts.append(f'<section class="ltx_section" id="{section.anchor}">')
        if section.heading:
            tag_html = f'<span class="ltx_tag">{html_lib.escape(section.tag)}</span> ' if section.tag else ""
            parts.append(
                f'<h2 class="ltx_title ltx_title_section">{tag_html}{html_lib.escape(section.heading)}</h2>'
            )
        for para in section.paragraphs:
            body = _link_citations(para, references, section.anchor, occurrences)
            parts.append(f'<div class="ltx_para"><p class="ltx_p">{body}</p></div>')
        parts.append("</section>")

    if references:
        parts.append('<section class="ltx_bibliography" id="bib"><h2 class="ltx_title">References</h2>')
        parts.append('<ul class="ltx_biblist">')
        for num, text in references.items():
            parts.append(
                f'<li class="ltx_bibitem" id="bib.bib{num}">'
                f'<span class="ltx_tag">[{num}]</span> {html_lib.escape(text)}</li>'
            )
        parts.append("</ul></section>")

    parts.append("</article>")
    return "".join(parts), targets, occurrences


def _link_citations(
    text: str,
    references: dict[str, str],
    section_anchor: str,
    occurrences: list[RefOccurrence],
) -> str:
    escaped = html_lib.escape(text)

    def repl(match: re.Match) -> str:
        run = match.group(1)
        nums = _expand_cite_run(run)
        if not any(n in references for n in nums):
            return match.group(0)
        # Link each known number inside the bracket to its reference.
        inner = match.group(0)
        for n in nums:
            if n in references:
                occurrences.append(
                    RefOccurrence(section_anchor=section_anchor, target_anchor=f"bib.bib{n}", kind="cites")
                )
        first = next((n for n in nums if n in references), None)
        return (
            f'<a data-verity="bib.bib{first}" data-verity-kind="citation" tabindex="0">{inner}</a>'
        )

    return _CITE_RUN.sub(repl, escaped)
