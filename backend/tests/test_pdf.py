"""PDF extraction on a synthetic paper — a real PDF built in-memory so the test
needs no network. Exercises heading detection, byline cleanup, [N] reference
parsing, inline-citation linking, and table rendering."""

import fitz
import pytest

from verity.ingest import pdf as pdf_mod


def _make_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    page.insert_text((72, y), "A Study of Widgets", fontsize=22, fontname="helv")
    y += 40
    page.insert_text((72, y), "Jane Doe", fontsize=11, fontname="helv")
    y += 16
    page.insert_text((72, y), "University of Somewhere", fontsize=10, fontname="helv")
    y += 16
    page.insert_text((72, y), "jane@example.com", fontsize=10, fontname="helv")
    y += 30
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


def test_byline_keeps_name_drops_affiliation_and_email(processed):
    assert processed.authors == "Jane Doe"


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
    assert 'data-verity="bib.bib2"' in processed.article_html
    kinds = {o.target_anchor for o in processed.occurrences}
    assert "bib.bib1" in kinds and "bib.bib3" in kinds


def test_page_count():
    assert pdf_mod.page_count(_make_pdf()) == 1


# --- unit tests for the trickier heuristics -------------------------------

def test_author_names_from_grid_block():
    # name + affiliation + email in one block → just the name
    assert pdf_mod._author_names("Ashish Vaswani∗ Google Brain avaswani@google.com") == [
        "Ashish Vaswani"
    ]


def test_author_names_from_comma_list():
    assert pdf_mod._author_names("Jane Doe, John Smith, and Bob Lee") == [
        "Jane Doe",
        "John Smith",
        "Bob Lee",
    ]


def test_notice_is_rejected():
    assert pdf_mod._is_notice("Copyright 2023, all rights reserved.")
    assert pdf_mod._is_notice(
        "Provided proper attribution, permission is granted to reproduce this work."
    )
    assert not pdf_mod._is_notice("Jane Doe")


def test_render_table():
    html = pdf_mod._render_table([["Model", "BLEU"], ["Transformer", "28.4"]])
    assert "<table" in html and "<th>Model</th>" in html and "<td>Transformer</td>" in html
