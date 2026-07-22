"""Checkpoint parsing robustness. The parser is line-based (not JSON) so that
LaTeX backslashes in a key point can't break it — a formatting hiccup must
never break a reader's checkpoint."""

from verity.llm.tasks import _parse_checkpoint


def test_parse_line_format():
    raw = "FEEDBACK: good start\nPOINT hit: A\nPOINT miss: B"
    out = _parse_checkpoint(raw)
    assert out["feedback"] == "good start"
    assert [p["status"] for p in out["key_points"]] == ["hit", "miss"]
    assert out["key_points"][0]["point"] == "A"


def test_parse_tolerates_latex_backslashes():
    raw = "FEEDBACK: nice\nPOINT hit: scaling by $\\sqrt{d_k}$ stabilizes gradients"
    out = _parse_checkpoint(raw)
    assert out["key_points"][0]["status"] == "hit"
    assert "sqrt" in out["key_points"][0]["point"]


def test_parse_case_insensitive_and_ignores_noise():
    raw = "here is my assessment\nFEEDBACK: ok\npoint PARTIAL: close enough\n"
    out = _parse_checkpoint(raw)
    assert out["feedback"] == "ok"
    assert out["key_points"][0]["status"] == "partial"


def test_parse_no_markers_falls_back_to_text():
    out = _parse_checkpoint("some unstructured reply")
    assert out["key_points"] == []
    assert out["feedback"] == "some unstructured reply"
