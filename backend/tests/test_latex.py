from pathlib import Path

from verity.ingest import latex

FIXTURE = Path(__file__).parent / "fixtures" / "sample.tex"


def load():
    return latex.parse(FIXTURE.read_text(encoding="utf-8"))


def test_labels_with_environment_kind():
    info = load()
    assert info.labels["eq:attn"] == "equation"
    assert info.labels["lem:lipschitz"] == "lem"
    assert "sec:intro" in info.labels


def test_refs_and_cites():
    info = load()
    assert "sec:method" in info.refs
    assert "lem:lipschitz" in info.refs
    assert info.cite_keys == ["vaswani2017", "bahdanau2015"]


def test_comments_are_stripped():
    info = load()
    assert "ignored" not in info.cite_keys


def test_bibliography_entries():
    info = load()
    assert "vaswani2017" in info.bibliography
    assert "Attention is all you need" in info.bibliography["vaswani2017"]


def test_macros():
    info = load()
    assert info.macros["R"] == "\\mathbb{R}"
    assert info.macros["softmax"] == "softmax"
    assert "attn" in info.macros


def test_theorem_environments_including_custom_names():
    info = load()
    lemmas = [t for t in info.theorems if t["kind"] == "lemma"]
    assert len(lemmas) == 1
    assert lemmas[0]["label"] == "lem:lipschitz"
    assert "1-Lipschitz" in lemmas[0]["statement"]
    assert lemmas[0]["title"] == "Stability"


def test_sections():
    info = load()
    titles = [s["title"] for s in info.sections]
    assert titles == ["Introduction", "Method"]
    assert info.sections[1]["label"] == "sec:method"


def test_symbol_candidates():
    info = load()
    tokens = {s["token"] for s in info.symbols}
    assert "d_k" in tokens
    assert "\\alpha" in tokens
    assert "W^Q" in tokens
