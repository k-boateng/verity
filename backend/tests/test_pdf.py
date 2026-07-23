"""PDF extraction on a synthetic paper — a real PDF built in-memory so the test
needs no network. Exercises heading detection, [N] reference parsing, and
inline-citation linking."""

import fitz
import pytest

from verity.ingest import pdf as pdf_mod


def _make_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    page.insert_text((72, y), "A Study of Widgets", fontsize=22, fontname="helv")
    y += 44
    page.insert_text((72, y), "1 Introduction", fontsize=14, fontname="hebo")
    y += 24
    page.insert_text(
        (72, y),
        "Widgets are central to gadgets [1]. Prior work explored them [2, 3].",
        fontsize=11,
    )
    y += 40
    page.insert_text((72, y), "2 Method", fontsize=14, fontname="hebo")
    y += 24
    page.insert_text((72, y), "We assemble widgets carefully, following [1].", fontsize=11)
    y += 40
    page.insert_text((72, y), "References", fontsize=14, fontname="hebo")
    y += 24
    for line in [
        "[1] A. Author. On widgets. Journal of Gadgets, 2020.",
        "[2] B. Builder. Widget theory. Proc. Widgetics, 2019.",
        "[3] C. Crafter. Assembling widgets. Widget Press, 2021.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    return doc.tobytes()


@pytest.fixture(scope="module")
def processed():
    return pdf_mod.extract(_make_pdf())


def test_title(processed):
    assert processed.title == "A Study of Widgets"


def test_sections_detected(processed):
    assert 'id="S1"' in processed.article_html
    assert "Introduction" in processed.article_html
    assert "Method" in processed.article_html


def test_references_parsed(processed):
    refs = {t.label: t.excerpt_text for t in processed.targets if t.kind == "citation"}
    assert set(refs) == {"[1]", "[2]", "[3]"}
    assert "On widgets" in refs["[1]"]


def test_inline_citations_linked(processed):
    assert 'data-verity="bib.bib1"' in processed.article_html
    # [2, 3] links to the first known number in the run
    assert 'data-verity="bib.bib2"' in processed.article_html
    kinds = {o.target_anchor for o in processed.occurrences}
    assert "bib.bib1" in kinds and "bib.bib3" in kinds


def test_page_count():
    assert pdf_mod.page_count(_make_pdf()) == 1
