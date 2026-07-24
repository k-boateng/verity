from verity.ingest import graph, html, latex

SAMPLE_HTML = r"""
<html><body><article class="ltx_document">
<h1 class="ltx_title ltx_title_document">A Sample Paper</h1>
<div class="ltx_authors">Ada Lovelace</div>
<section id="S1" class="ltx_section">
  <h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">1 </span>Introduction</h2>
  <div class="ltx_para"><p class="ltx_p">We refer to
    <a href="#S2.E1" class="ltx_ref"><span class="ltx_text">Eq. (1)</span></a> and
    <cite class="ltx_cite"><a href="#bib.bib1" class="ltx_ref">[1]</a></cite>.
    <script>alert('x')</script>
  </p></div>
</section>
<section id="S2" class="ltx_section">
  <h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">2 </span>Method</h2>
  <table id="S2.E1" class="ltx_equation">
    <tr><td><math alttext="A = QK^{T} / \sqrt{d_{k}}" id="S2.E1.m1"><mi>A</mi></math></td>
    <td><span class="ltx_tag ltx_tag_equation">(1)</span></td></tr>
  </table>
  <div class="ltx_para"><p class="ltx_p"><img src="x1.png"/></p></div>
  <figure id="S2.F1" class="ltx_figure">
    <figcaption class="ltx_caption"><span class="ltx_tag ltx_tag_figure">Figure 1:</span> An unreferenced picture.</figcaption>
  </figure>
</section>
<section id="bib" class="ltx_bibliography">
  <ul>
    <li id="bib.bib1" class="ltx_bibitem"><span class="ltx_tag">[1]</span>
      Vaswani et al. Attention is all you need. 2017.</li>
  </ul>
</section>
</article></body></html>
"""


def test_process_builds_targets_and_occurrences():
    processed = html.process(SAMPLE_HTML, "/api/assets/1234.5678")
    assert processed.title == "A Sample Paper"
    assert processed.authors == "Ada Lovelace"

    by_anchor = {t.anchor: t for t in processed.targets}
    assert by_anchor["S2.E1"].kind == "equation"
    assert "A = QK^{T}" in by_anchor["S2.E1"].excerpt_text
    assert by_anchor["bib.bib1"].kind == "citation"
    assert "Vaswani" in by_anchor["bib.bib1"].excerpt_text
    assert by_anchor["bib.bib1"].section_label == "References"

    # unreferenced-but-notable elements still become resolvable targets
    assert by_anchor["S2.F1"].kind == "figure"
    assert by_anchor["S2.F1"].label == "Figure 1"  # no "Figure Figure 1:"
    assert "unreferenced picture" in by_anchor["S2.F1"].excerpt_text

    kinds = {(o.target_anchor, o.kind) for o in processed.occurrences}
    assert ("S2.E1", "references") in kinds
    assert ("bib.bib1", "cites") in kinds
    # both occurrences originate in section S1
    assert all(o.section_anchor == "S1" for o in processed.occurrences)


def test_byline_replaces_author_block():
    processed = html.process(SAMPLE_HTML, "/api/assets/1234.5678", byline="Ada Lovelace, Charles Babbage")
    assert processed.authors == "Ada Lovelace, Charles Babbage"
    assert "verity-byline" in processed.article_html
    assert 'class="ltx_authors"' not in processed.article_html


def test_math_index_by_section():
    processed = html.process(SAMPLE_HTML, "/api/assets/1234.5678")
    assert "S2" in processed.math_by_section
    # normalized: braces and whitespace removed
    assert "d_k" in processed.math_by_section["S2"]


def test_process_stamps_and_sanitizes():
    processed = html.process(SAMPLE_HTML, "/api/assets/1234.5678")
    assert 'data-verity="S2.E1"' in processed.article_html
    assert 'data-verity-kind="citation"' in processed.article_html
    assert "<script" not in processed.article_html
    assert '/api/assets/1234.5678/x1.png' in processed.article_html
    assert processed.image_srcs == ["x1.png"]


def test_graph_merges_symbols_with_abstention():
    processed = html.process(SAMPLE_HTML, "/api/assets/1234.5678")
    info = latex.LatexInfo(
        macros={"R": "\\mathbb{R}", "todo": "\\textcolor{red}{[[#1]]}"},
        symbols=[{"token": "d_k", "count": 5}],
    )
    g = graph.build(processed, info)

    symbols = [n for n in g.nodes if n["kind"] == "symbol"]
    by_label = {n["label"]: n for n in symbols}

    # parameterized macros are commands, not notation
    assert "\\textcolor{red}{[[#1]]}" not in by_label

    # macro is labelled by its EXPANSION (what the reader sees), not the name
    assert "\\mathbb{R}" in by_label
    assert "\\R" not in by_label
    assert by_label["\\mathbb{R}"]["data"]["macro_name"] == "\\R"

    # bare-letter plumbing macros are dropped as noise
    g2 = graph.build(processed, latex.LatexInfo(macros={"kq": "q"}))
    assert "q" not in {n["label"] for n in g2.nodes if n["kind"] == "symbol"}

    # no fabricated definitions â€” every fresh symbol is unresolved with no excerpt
    for node in symbols:
        assert node["excerpt"] == ""
        assert node["data"]["definition_status"] == "unresolved"

    # scanned token carries its rendered form and where it appears
    dk = by_label["d_k"]
    assert dk["data"]["sections"] == ["S2"]
    assert dk["data"]["label_mathml"].startswith("<math")

    edge_kinds = {e["kind"] for e in g.edges}
    assert edge_kinds == {"references", "cites"}

