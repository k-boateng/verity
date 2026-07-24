"""PDF ingestion adapter.

PDF is a layout format, not a semantic one, so this is honest best-effort. We
recover the title, a clean byline, a section structure with paragraphs, figures,
and the reference list with [N]-style citations linked back to it — enough for
the reader, Ask, the anchored chat, and checkpoints to all work.

Tables and display equations don't survive text extraction (glyph soup, mangled
grids), so instead of guessing we crop those regions straight from the page as
crisp images. Prose stays selectable text; the hard-to-reconstruct bits render
as pictures of the real thing. Inline math in prose is left as best-effort text.

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
_EMAIL = re.compile(r"\S+@\S+")
_MIN_IMAGE_PT = 48  # ignore icons/rules/logos smaller than this


@dataclass
class Element:
    kind: str  # "text" | "image" | "table"
    page: int
    y: float
    x0: float
    text: str = ""
    size: float = 0.0
    bold: bool = False
    img_src: str = ""
    img_w: float = 0.0  # intended display width in CSS px (region's point width)
    table_rows: list = field(default_factory=list)

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass
class Section:
    anchor: str
    label: str
    tag: str
    heading: str
    content: list[dict] = field(default_factory=list)  # {kind, ...}
    is_refs: bool = False

    def texts(self) -> list[str]:
        return [c["text"] for c in self.content if c["kind"] == "text"]


class PdfError(Exception):
    pass


def page_count(pdf_bytes: bytes) -> int:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc.page_count


def extract(
    pdf_bytes: bytes, asset_url_prefix: str = "", assets: dict | None = None
) -> ProcessedHtml:
    """Parse a PDF. Figures and rasterized crops are collected into `assets`
    (a dict of filename -> (bytes, content_type)) rather than written to disk,
    so the caller can persist them wherever it likes. Pass assets=None (tests)
    to skip binary extraction."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        elements = _collect_elements(doc, assets, asset_url_prefix)
        meta_title = (doc.metadata or {}).get("title", "") or ""

    text_elements = [e for e in elements if e.kind == "text"]
    if not text_elements:
        raise PdfError("no extractable text — this may be a scanned PDF")

    body_size = _body_size(text_elements)
    title, title_size = _extract_title(text_elements, body_size, meta_title)
    byline, sections = _segment(elements, body_size, title, title_size)
    references = _parse_references(sections)
    article_html, targets, occurrences = _render(title, byline, sections, references)

    image_srcs = [e.img_src for e in elements if e.kind == "image"]
    return ProcessedHtml(
        title=title,
        authors=byline,
        article_html=article_html,
        targets=targets,
        occurrences=occurrences,
        image_srcs=image_srcs,
        math_by_section={},
    )


# --- collection -----------------------------------------------------------

def _collect_elements(
    doc: fitz.Document, assets: dict | None, asset_url_prefix: str
) -> list[Element]:
    """Flatten the document to text, image, and table elements in reading order.
    A cheap two-column heuristic (left-half before right-half, per page) handles
    the common two-column paper layout."""
    elements: list[Element] = []
    for pno in range(doc.page_count):
        page = doc.load_page(pno)
        width = page.rect.width

        tables = _extract_tables(page, pno, assets, asset_url_prefix)
        table_boxes = [box for _, box in tables]
        page_elements: list[Element] = [t for t, _ in tables]

        images = _extract_images(doc, page, pno, assets, asset_url_prefix)
        page_elements.extend(images)

        for b in page.get_text("dict").get("blocks", []):
            if b.get("type") != 0:
                continue
            if _inside_any_table(b["bbox"], table_boxes):
                continue
            text, size, bold = _block_text(b)
            if not text:
                continue
            # Display equations are glyph-soup as text — crop them from the page
            # as a crisp image instead, so they render correctly.
            if assets is not None and _is_display_equation(text, b["bbox"], width):
                src = _rasterize_region(
                    page, b["bbox"], assets, asset_url_prefix, f"eq-p{pno}-{round(b['bbox'][1])}"
                )
                if src:
                    page_elements.append(
                        Element(
                            kind="image",
                            page=pno,
                            y=b["bbox"][1],
                            x0=b["bbox"][0],
                            img_src=src,
                            img_w=b["bbox"][2] - b["bbox"][0],
                        )
                    )
                    continue
            page_elements.append(
                Element(
                    kind="text",
                    page=pno,
                    y=b["bbox"][1],
                    x0=b["bbox"][0],
                    text=text,
                    size=size,
                    bold=bold,
                )
            )

        def order_key(e: Element) -> tuple:
            column = 0 if e.x0 < width * 0.5 else 1
            return (column, round(e.y))

        page_elements.sort(key=order_key)
        elements.extend(page_elements)
    return elements


def _rasterize_region(
    page: fitz.Page, bbox, assets: dict | None, asset_url_prefix: str, name: str
) -> str:
    """Render a region of the page to a crisp PNG (2x) — used for tables and
    display equations that don't survive text extraction. The bytes go into the
    assets dict; the URL is returned."""
    if assets is None:
        return ""
    try:
        rect = fitz.Rect(bbox) + (-3, -3, 3, 3)
        pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(2, 2))
        filename = f"{name}.png"
        assets[filename] = (pix.tobytes("png"), "image/png")
        return f"{asset_url_prefix}/{filename}"
    except Exception:
        return ""


_MATH_CHARS = set("=+−-×÷∑∫∏√≤≥≈≠∞∂∇^_{}|/⋅·→←↦∈∉⊂⊆∪∩⊗⊕≅∝∀∃±∓" + "αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ")


def _is_display_equation(text: str, bbox, page_width: float) -> bool:
    """A short, isolated, math-heavy block — a display equation. Conservative on
    purpose: better to leave a line as text than to rasterize real prose."""
    compact = text.replace(" ", "")
    if len(compact) < 3 or len(text) > 240 or len(text.split()) > 28:
        return False
    letters = sum(c.isalpha() and c.isascii() for c in compact)
    total = len(compact)
    math = sum(c in _MATH_CHARS for c in text)
    has_eqnum = bool(re.search(r"\(\d+\)\s*$", text))
    alpha_ratio = letters / total
    math_ratio = math / total
    return alpha_ratio < 0.55 and (math_ratio > 0.18 or (has_eqnum and math_ratio > 0.08))


def _looks_like_real_table(rows: list) -> bool:
    """A real data table has many short cells (numbers, short labels). A text
    column mis-detected as a table has a few long, sentence-like cells — reject
    those so we don't hide prose behind an image."""
    cells = [str(c).strip() for r in rows for c in r if c and str(c).strip()]
    if len(cells) < 4:
        return False
    avg_len = sum(len(c) for c in cells) / len(cells)
    short = sum(1 for c in cells if len(c) <= 25)
    return avg_len < 45 and short / len(cells) > 0.55


def _extract_tables(
    page: fitz.Page, pno: int, assets: dict | None, asset_url_prefix: str
) -> list[tuple[Element, tuple]]:
    out: list[tuple[Element, tuple]] = []
    try:
        finder = page.find_tables()
    except Exception:
        return out
    for i, tbl in enumerate(getattr(finder, "tables", [])):
        try:
            rows = tbl.extract()
            box = tuple(tbl.bbox)
        except Exception:
            continue
        if not rows or len(rows) < 2 or all(len(r) < 2 for r in rows):
            continue
        if not _looks_like_real_table(rows):
            continue  # a text column mis-detected as a table — leave it as prose
        # A cropped image of the real table beats a mangled HTML reconstruction.
        src = _rasterize_region(page, box, assets, asset_url_prefix, f"tbl-p{pno}-{i}")
        if src:
            element = Element(
                kind="image", page=pno, y=box[1], x0=box[0], img_src=src, img_w=box[2] - box[0]
            )
        else:
            element = Element(kind="table", page=pno, y=box[1], x0=box[0], table_rows=rows)
        out.append((element, box))
    return out


def _inside_any_table(bbox: tuple, table_boxes: list[tuple]) -> bool:
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    for tb in table_boxes:
        if tb[0] <= cx <= tb[2] and tb[1] <= cy <= tb[3]:
            return True
    return False


def _extract_images(
    doc: fitz.Document,
    page: fitz.Page,
    pno: int,
    assets: dict | None,
    asset_url_prefix: str,
) -> list[Element]:
    if assets is None:
        return []
    out: list[Element] = []
    seen: set[int] = set()
    for info in page.get_images(full=True):
        xref = info[0]
        if xref in seen:
            continue
        seen.add(xref)
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            rects = []
        rect = rects[0] if rects else None
        if rect is not None and (rect.width < _MIN_IMAGE_PT or rect.height < _MIN_IMAGE_PT):
            continue
        try:
            extracted = doc.extract_image(xref)
        except Exception:
            continue
        ext = extracted.get("ext", "png")
        data = extracted.get("image")
        if not data:
            continue
        filename = f"p{pno}-x{xref}.{ext}"
        assets[filename] = (data, f"image/{ext}")
        y = rect.y0 if rect is not None else pno * 10000
        x0 = rect.x0 if rect is not None else 0.0
        out.append(
            Element(
                kind="image", page=pno, y=y, x0=x0, img_src=f"{asset_url_prefix}/{filename}"
            )
        )
    return out


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


def _body_size(elements: list[Element]) -> float:
    weighted: dict[float, int] = {}
    for e in elements:
        weighted[e.size] = weighted.get(e.size, 0) + len(e.text)
    return max(weighted, key=weighted.get) if weighted else 10.0


# --- structure ------------------------------------------------------------

def _extract_title(
    elements: list[Element], body_size: float, meta_title: str
) -> tuple[str, float]:
    first_page = [
        e for e in elements if e.page == 0 and not re.match(r"ar\s?xiv[:\s]", e.text, re.IGNORECASE)
    ]
    if not first_page:
        return (meta_title.strip() or "Untitled document", body_size + 4)
    top = max(first_page, key=lambda e: e.size)
    if top.size <= body_size + 0.5:
        return (meta_title.strip() or top.text[:200], top.size)
    parts = [e.text for e in first_page if abs(e.size - top.size) < 0.3 and e.y <= top.y + 120]
    title = " ".join(parts).strip() or top.text
    return (title[:300], top.size)


def _looks_like_heading(element: Element, body_size: float, title: str) -> bool:
    text = element.text
    if not text or text == title or element.words > _HEADING_WORDS_MAX:
        return False
    if _REF_HEADINGS.match(text):
        return True
    numbered = bool(_NUMBERED.match(text))
    if not numbered:
        if text[-1] in ".,;:":
            return False
        first_alpha = next((c for c in text if c.isalpha()), "")
        if first_alpha and not first_alpha.isupper():
            return False
    bigger = element.size >= body_size + 1.0
    allcaps = text.isupper() and 2 <= len(text) <= 60
    if bigger and element.words <= 14:
        return True
    if element.bold and (numbered or allcaps):
        return True
    if numbered and element.size >= body_size and element.words <= 12:
        return True
    return False


def _segment(
    elements: list[Element], body_size: float, title: str, title_size: float
) -> tuple[str, list[Section]]:
    sections: list[Section] = []
    front_matter: list[str] = []
    counter = 0
    current: Section | None = None

    for e in elements:
        if e.kind == "text":
            if e.text == title or (e.page == 0 and abs(e.size - title_size) < 0.3):
                continue  # title (or a title fragment) — never body
            if _looks_like_heading(e, body_size, title):
                counter += 1
                is_refs = bool(_REF_HEADINGS.match(e.text))
                m = _NUMBERED.match(e.text)
                if m:
                    tag = m.group(1)
                    heading = e.text[m.end() - 1 :].strip() or e.text
                    label = f"§{tag}"
                else:
                    tag = ""
                    heading = e.text
                    label = e.text if len(e.text) <= 40 else e.text[:40] + "…"
                current = Section(anchor=f"S{counter}", label=label, tag=tag, heading=heading, is_refs=is_refs)
                sections.append(current)
                continue

        if current is None:
            # Page-0 material before the first heading is the byline block.
            # Pull the author names out of it and drop affiliations/emails/
            # notices, so the byline is a clean list, not the stacked grid.
            if e.kind == "text" and e.page == 0:
                if not _is_notice(e.text):
                    front_matter.extend(_author_names(e.text))
                continue
            current = Section(anchor="S0", label="", tag="", heading="")
            sections.append(current)

        if e.kind == "text":
            current.content.append({"kind": "text", "text": e.text})
        elif e.kind == "image":
            current.content.append({"kind": "image", "src": e.img_src, "w": e.img_w})
        elif e.kind == "table":
            current.content.append({"kind": "table", "rows": e.table_rows})

    byline = _clean_byline(front_matter)
    sections = [s for s in sections if s.content or s.heading]
    return byline, sections


_NOTICE_WORDS = (
    "permission",
    "copyright",
    "all rights",
    "license",
    "reproduce",
    "preprint",
    "under review",
    "to appear",
    "©",
)


_AFFILIATION_WORDS = (
    "university",
    "universit",
    "institute",
    "college",
    "laborator",
    "department",
    "research",
    "google",
    "microsoft",
    "deepmind",
    "openai",
    "brain",
    "labs",
    " inc",
    " corp",
    "technolog",
    "academy",
)


def _is_notice(text: str) -> bool:
    """Front-matter prose that isn't a byline — legal notices, submission
    banners. Author/affiliation lines are short and not full sentences."""
    low = text.lower()
    if any(word in low for word in _NOTICE_WORDS):
        return True
    return len(text.split()) > 12 and text.rstrip().endswith(".")


def _extract_name(part: str) -> str:
    """The leading run of name-like tokens in a fragment — capitalized words and
    initials, stopping at an affiliation word, an email, or lowercase prose. So
    'Ashish Vaswani Google Brain ava@…' yields 'Ashish Vaswani'."""
    name: list[str] = []
    for tok in part.split():
        clean = tok.strip(".,;∗*†‡§¶0123456789¹²³⁴⁵⁶⁷⁸⁹⁰")
        low = clean.lower()
        if "@" in tok or any(word.strip() in low for word in _AFFILIATION_WORDS):
            break
        if tok[:1].isupper() or tok[:1] in "ŁØÅÖÜÉ":
            name.append(clean)
            if len(name) >= 4:
                break
        else:
            break
    if 1 <= len(name) <= 4 and any(len(t) > 1 for t in name):
        return " ".join(name)
    return ""


def _author_names(text: str) -> list[str]:
    if _EMAIL.sub("", text).strip() == "" or len(text.split()) > 40:
        return []
    names: list[str] = []
    for part in re.split(r"[,;]|\band\b|&", text):
        name = _extract_name(part.strip())
        if name:
            names.append(name)
    return names


def _clean_byline(names: list[str]) -> str:
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    text = ", ".join(seen)
    if len(text) > 220:
        text = text[:220].rsplit(",", 1)[0] + "…"
    return text


# --- references & citations ----------------------------------------------

def _parse_references(sections: list[Section]) -> dict[str, str]:
    refs: dict[str, str] = {}
    ref_section = next((s for s in sections if s.is_refs), None)
    if ref_section is None:
        return refs
    paragraphs = ref_section.texts()
    blob = " ".join(paragraphs).strip()

    if "[" in blob and _CITE_RUN.search(blob):
        parts = re.split(r"\[(\d+)\]", blob)
        for i in range(1, len(parts) - 1, 2):
            num = parts[i]
            text = parts[i + 1].strip(" .")
            if text:
                refs[num] = text[:600]
    else:
        numbered = re.findall(r"(?:^|\s)(\d{1,3})\.\s+(.+?)(?=\s\d{1,3}\.\s|$)", blob)
        if len(numbered) >= 2:
            for num, text in numbered:
                refs[num] = text.strip()[:600]
        else:
            for i, para in enumerate(paragraphs, start=1):
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
    title: str, byline: str, sections: list[Section], references: dict[str, str]
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
    if byline:
        parts.append(f'<div class="verity-byline">{html_lib.escape(byline)}</div>')

    for section in sections:
        if section.is_refs:
            continue
        parts.append(f'<section class="ltx_section" id="{section.anchor}">')
        if section.heading:
            tag_html = (
                f'<span class="ltx_tag">{html_lib.escape(section.tag)}</span> '
                if section.tag
                else ""
            )
            parts.append(
                f'<h2 class="ltx_title ltx_title_section">{tag_html}{html_lib.escape(section.heading)}</h2>'
            )
        for item in section.content:
            if item["kind"] == "text":
                body = _link_citations(item["text"], references, section.anchor, occurrences)
                parts.append(f'<div class="ltx_para"><p class="ltx_p">{body}</p></div>')
            elif item["kind"] == "image":
                src = html_lib.escape(item["src"])
                # rasterized crops render at 2x; set display width to the real
                # region width so equations/tables aren't doubled in size
                w = item.get("w") or 0
                style = f' style="width:{round(w)}px"' if w else ""
                cls = "ltx_figure pdf-crop" if "/tbl-" in src or "/eq-" in src else "ltx_figure"
                parts.append(
                    f'<figure class="{cls}"><img src="{src}"{style} loading="lazy" alt=""/></figure>'
                )
            elif item["kind"] == "table":
                parts.append(_render_table(item["rows"]))
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


def _render_table(rows: list) -> str:
    out = ['<div class="ltx_table pdf-table"><table class="ltx_tabular">']
    for r, row in enumerate(rows):
        out.append("<tr>")
        cells = row if isinstance(row, (list, tuple)) else [row]
        tag = "th" if r == 0 else "td"
        for cell in cells:
            text = "" if cell is None else re.sub(r"\s+", " ", str(cell)).strip()
            out.append(f"<{tag}>{html_lib.escape(text)}</{tag}>")
        out.append("</tr>")
    out.append("</table></div>")
    return "".join(out)


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
        inner = match.group(0)
        for n in nums:
            if n in references:
                occurrences.append(
                    RefOccurrence(section_anchor=section_anchor, target_anchor=f"bib.bib{n}", kind="cites")
                )
        first = next((n for n in nums if n in references), None)
        return f'<a data-verity="bib.bib{first}" data-verity-kind="citation" tabindex="0">{inner}</a>'

    return _CITE_RUN.sub(repl, escaped)
