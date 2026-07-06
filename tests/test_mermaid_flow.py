"""End-to-end tests for the public ``render_flowchart`` entry point.

These exercise real mermaid source strings through the full pipeline
(``parse -> layout_flowgraph -> lines``) and assert genuine rendered
geometry/topology — arrowhead glyphs, edge labels, row ordering, and the
degradation contract — not merely "no exception raised".
"""

from __future__ import annotations

import re

from termrender.renderers.mermaid_flow import render_flowchart

_BOX_GLYPH_RE = re.compile(r"[\u2500-\u259F\u25A0-\u25FF]")
_ARROW_RE = re.compile(r"[\u25b2\u25bc\u25b6\u25c0]")  # ▲▼▶◀


def _row_of(lines: list[str], label: str) -> int:
    for i, line in enumerate(lines):
        if label in line:
            return i
    raise AssertionError(f"label {label!r} not found in rendered output: {lines!r}")


# --------------------------------------------------------------------------
# Forward DAG — arrowheads point down into children
# --------------------------------------------------------------------------


def test_forward_dag_renders_with_arrowheads_into_children():
    source = "graph TD\nA-->B\nA-->C\n"
    lines = render_flowchart(source, width=80)
    assert lines
    text = "\n".join(lines)
    for label in ("A", "B", "C"):
        assert label in text
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)
    # Real topology: A is above both its children.
    row_a = _row_of(lines, "A")
    assert row_a < _row_of(lines, "B")
    assert row_a < _row_of(lines, "C")
    # A down-pointing arrowhead lands on a child's top border.
    assert "\u25bc" in text


# --------------------------------------------------------------------------
# Edge label — |label| form
# --------------------------------------------------------------------------


def test_pipe_label_edge_shows_label_text():
    source = "graph TD\nA-->|hello|B\n"
    lines = render_flowchart(source, width=80)
    assert lines
    text = "\n".join(lines)
    assert "A" in text and "B" in text
    assert "hello" in text
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)


def test_inline_label_edge_shows_label_text():
    source = "graph TD\nA -- go now --> B\n"
    lines = render_flowchart(source, width=80)
    assert lines
    text = "\n".join(lines)
    assert "go now" in text


# --------------------------------------------------------------------------
# Labeled back-edge cycle — the exact shape that panics the Go binary
# --------------------------------------------------------------------------


def test_labeled_back_edge_cycle_renders_all_boxes_label_and_arrow():
    source = "graph TD\nA-->B\nB-->C\nC-->|retry|A\n"
    lines = render_flowchart(source, width=80)
    assert lines, "must render, never raise or degrade to echo"
    text = "\n".join(lines)
    for label in ("A", "B", "C"):
        assert label in text
    assert "retry" in text
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)
    # An arrowhead lands somewhere (the back-edge's ◀/▲ into A, or the
    # forward edges' ▼ into B/C) — at minimum the diagram is not headless.
    assert _ARROW_RE.search(text)
    # Real topology check: the forward chain A -> B -> C still orders
    # top-to-bottom despite the labeled back-edge C -> A.
    row_a, row_b, row_c = _row_of(lines, "A"), _row_of(lines, "B"), _row_of(lines, "C")
    assert row_a < row_b < row_c


# --------------------------------------------------------------------------
# Multi-parent DAG — both edges attach to the shared child
# --------------------------------------------------------------------------


def test_multi_parent_dag_attaches_both_edges_to_shared_child():
    source = "graph TD\nA-->C\nB-->C\n"
    lines = render_flowchart(source, width=80)
    assert lines
    text = "\n".join(lines)
    for label in ("A", "B", "C"):
        assert label in text
    row_a, row_b, row_c = _row_of(lines, "A"), _row_of(lines, "B"), _row_of(lines, "C")
    assert row_a < row_c
    assert row_b < row_c

    # Real geometry: A and B sit side by side in the same rank (row), and
    # each routes its own vertical leg down toward C — the inter-rank gap
    # rows must show line glyphs at (at least) two distinct columns,
    # evidencing two separate incoming connections rather than one shared
    # trunk that happens to touch both labels.
    assert row_a == row_b
    gap_lo, gap_hi = min(row_a, row_b) + 1, row_c
    vertical_cols: set[int] = set()
    for row in range(gap_lo, gap_hi):
        if row < 0 or row >= len(lines):
            continue
        for col, ch in enumerate(lines[row]):
            if ch in "\u2502\u2514\u2518\u250c\u2510\u251c\u2524\u252c\u2534\u253c":
                vertical_cols.add(col)
    assert len(vertical_cols) >= 2, (
        f"expected >=2 distinct incoming columns into C, got {vertical_cols}"
    )


# --------------------------------------------------------------------------
# Headless edge — `---` draws a line with no arrowhead
# --------------------------------------------------------------------------


def test_headless_edge_has_no_arrowhead():
    source = "graph TD\nA---B\n"
    lines = render_flowchart(source, width=80)
    assert lines
    text = "\n".join(lines)
    assert "A" in text and "B" in text
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)
    assert not _ARROW_RE.search(text), "`---` must draw a plain line, no arrowhead"


# --------------------------------------------------------------------------
# Degradation contract
# --------------------------------------------------------------------------


def test_malformed_input_raw_echoes_with_no_box_glyphs():
    source = "not a diagram\njust some text\n"
    lines = render_flowchart(source, width=80)
    assert lines == ["not a diagram", "just some text"]
    text = "\n".join(lines)
    assert not _BOX_GLYPH_RE.search(text), "raw echo must contain no box-drawing glyphs"


def test_empty_body_headed_diagram_raw_echoes():
    source = "graph TD\n%% just a comment, no nodes\n"
    lines = render_flowchart(source, width=80)
    assert lines == ["graph TD", "%% just a comment, no nodes"]
    text = "\n".join(lines)
    assert not _BOX_GLYPH_RE.search(text)


def test_render_flowchart_never_raises_on_garbage_input():
    # Defensive: assorted odd inputs must never raise, always return a list.
    for source in ("", "\n\n\n", "graph", "flowchart LR\n", "graph TD\nA-->\n"):
        lines = render_flowchart(source, width=80)
        assert isinstance(lines, list)
