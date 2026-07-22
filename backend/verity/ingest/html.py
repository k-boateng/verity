"""HTML pass over the LaTeXML rendering (arxiv.org/html or ar5iv).

LaTeXML already resolves \\ref and \\cite into internal links
(<a href="#S3.E4">, <a href="#bib.bib4">). This pass:
  - extracts title/authors,
  - builds the anchor map: every internal link target becomes a resolvable
    node with a quotable excerpt,
  - records which section each reference occurs in (graph edges),
  - stamps hover targets with data-verity="<anchor>",
  - strips scripts/styles and rewrites image srcs to the backend asset route.
"""

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag


@dataclass
class Target:
    anchor: str
    kind: str
    label: str
    excerpt_text: str
    excerpt_html: str
    section_label: str


@dataclass
class RefOccurrence:
    section_anchor: str  # anchor of the enclosing section ("" = preamble)
    target_anchor: str
    kind: str  # references | cites


@dataclass
class ProcessedHtml:
    title: str
    authors: str
    article_html: str
    targets: list[Target] = field(default_factory=list)
    occurrences: list[RefOccurrence] = field(default_factory=list)
    image_srcs: list[str] = field(default_factory=list)


_KIND_BY_CLASS = [
    ("ltx_bibitem", "citation"),
    ("ltx_equation", "equation"),
    ("ltx_equationgroup", "equation"),
    ("ltx_figure", "figure"),
    ("ltx_table", "table"),
    ("ltx_theorem", "theorem"),
    ("ltx_section", "section"),
    ("ltx_subsection", "section"),
    ("ltx_subsubsection", "section"),
    ("ltx_appendix", "section"),
    ("ltx_note", "footnote"),
]


def process(html: str, safe_id: str) -> ProcessedHtml:
    soup = BeautifulSoup(html, "lxml")
    article = soup.find("article") or soup.find("body") or soup

    title = _text(article.find(class_="ltx_title_document"))
    authors = _text(article.find(class_="ltx_authors"))

    _strip_dangerous(article)

    targets: dict[str, Target] = {}
    occurrences: list[RefOccurrence] = []

    for link in article.find_all("a", href=True):
        href = link["href"]
        if not href.startswith("#"):
            # external links open in a new tab, never navigate the reader away
            link["target"] = "_blank"
            link["rel"] = "noopener"
            continue
        anchor = href[1:]
        element = article.find(id=anchor)
        if element is None:
            continue
        if anchor not in targets:
            target = _build_target(element, anchor)
            if target is None:
                continue
            targets[anchor] = target
        kind = "cites" if targets[anchor].kind == "citation" else "references"
        occurrences.append(
            RefOccurrence(
                section_anchor=_enclosing_section_anchor(link),
                target_anchor=anchor,
                kind=kind,
            )
        )
        link["data-verity"] = anchor
        link["data-verity-kind"] = targets[anchor].kind
        link["tabindex"] = "0"

    image_srcs = _rewrite_images(article, safe_id)

    return ProcessedHtml(
        title=title,
        authors=authors,
        article_html=str(article),
        targets=list(targets.values()),
        occurrences=occurrences,
        image_srcs=image_srcs,
    )


def _strip_dangerous(article: Tag) -> None:
    for tag in article.find_all(["script", "style", "link", "base", "iframe"]):
        tag.decompose()
    for tag in article.find_all(True):
        for attr in list(tag.attrs):
            if attr.lower().startswith("on"):
                del tag[attr]


def _text(element, limit: int = 400) -> str:
    if element is None:
        return ""
    text = re.sub(r"\s+", " ", element.get_text(" ", strip=True))
    return text[:limit]


def _classify(element: Tag, anchor: str) -> str:
    classes = element.get("class") or []
    class_str = " ".join(classes)
    for needle, kind in _KIND_BY_CLASS:
        if needle in class_str:
            return kind
    # Fall back to LaTeXML id conventions: S3, S3.SS2, S3.E4, S3.F2, S3.T1, bib.bib4
    if anchor.startswith("bib."):
        return "citation"
    tail = anchor.rsplit(".", 1)[-1]
    if re.match(r"^E\d+", tail):
        return "equation"
    if re.match(r"^F\d+", tail):
        return "figure"
    if re.match(r"^T\d+", tail):
        return "table"
    if re.match(r"^(S|SS|A)\d+", tail) or re.match(r"^[SA]\d+$", anchor):
        return "section"
    if anchor.lower().startswith("thm"):
        return "theorem"
    if "footnote" in anchor.lower():
        return "footnote"
    return "section"


def _build_target(element: Tag, anchor: str) -> Target | None:
    kind = _classify(element, anchor)
    label = _tag_label(element, kind)
    section_label = _section_label_for(element)

    if kind == "citation":
        excerpt_text = _text(element, 600)
        excerpt_html = ""
    elif kind == "equation":
        math = element.find("math")
        excerpt_html = str(math) if math else str(element)
        excerpt_text = (math.get("alttext", "") if math else "") or _text(element, 300)
    elif kind in ("figure", "table"):
        caption = element.find("figcaption") or element.find(class_="ltx_caption")
        excerpt_text = _text(caption, 500) or _text(element, 300)
        excerpt_html = ""
    elif kind == "theorem":
        excerpt_text = _text(element, 1000)
        excerpt_html = _inner_html_limited(element)
    elif kind == "footnote":
        excerpt_text = _text(element, 600)
        excerpt_html = ""
    else:  # section
        title_el = element.find(class_="ltx_title")
        title_text = _text(title_el, 200)
        first_para = element.find(class_="ltx_p")
        excerpt_text = title_text
        if first_para is not None:
            excerpt_text = f"{title_text} — {_text(first_para, 300)}" if title_text else _text(first_para, 300)
        excerpt_html = ""
        if not label:
            label = title_text

    if not excerpt_text and not excerpt_html:
        return None
    return Target(
        anchor=anchor,
        kind=kind,
        label=label or anchor,
        excerpt_text=excerpt_text,
        excerpt_html=excerpt_html,
        section_label=section_label,
    )


def _inner_html_limited(element: Tag, limit: int = 8000) -> str:
    html = "".join(str(c) for c in element.children)
    return html if len(html) <= limit else ""


_KIND_PREFIX = {
    "equation": "Eq.",
    "figure": "Figure",
    "table": "Table",
    "section": "§",
    "citation": "",
    "theorem": "",
    "footnote": "Footnote",
}


def _tag_label(element: Tag, kind: str) -> str:
    tag = element.find(class_="ltx_tag")
    if tag is not None:
        tag_text = _text(tag, 60)
        if tag_text:
            prefix = _KIND_PREFIX.get(kind, "")
            if kind == "section":
                return f"§{tag_text}" if not tag_text.startswith("§") else tag_text
            if kind == "theorem" or kind == "citation":
                return tag_text
            return f"{prefix} {tag_text}".strip()
    return ""


def _enclosing_section_anchor(link: Tag) -> str:
    for parent in link.parents:
        if isinstance(parent, Tag):
            classes = " ".join(parent.get("class") or [])
            if "ltx_section" in classes or "ltx_subsection" in classes or "ltx_appendix" in classes:
                if parent.get("id"):
                    return parent["id"]
    return ""


def _section_label_for(element: Tag) -> str:
    """Human label of the section containing this element, e.g. '§3.2'."""
    node = element
    while node is not None:
        if isinstance(node, Tag):
            classes = " ".join(node.get("class") or [])
            if any(c in classes for c in ("ltx_subsubsection", "ltx_subsection", "ltx_section", "ltx_appendix")):
                title = node.find(class_="ltx_title")
                if title is not None:
                    tag = title.find(class_="ltx_tag")
                    if tag is not None:
                        t = _text(tag, 40).rstrip(". ")
                        return f"§{t}" if not t.lower().startswith(("appendix", "§")) else t
                    return _text(title, 60)
        node = node.parent
    return ""


def _rewrite_images(article: Tag, safe_id: str) -> list[str]:
    srcs: list[str] = []
    for img in article.find_all("img", src=True):
        src = img["src"]
        if src.startswith(("http://", "https://", "data:")):
            continue
        srcs.append(src)
        img["src"] = f"/api/assets/{safe_id}/{src}"
        img["loading"] = "lazy"
    return srcs
