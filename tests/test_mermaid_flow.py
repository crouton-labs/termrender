"""End-to-end tests for the public ``render_flowchart`` entry point.

These exercise real mermaid source strings through the full pipeline
(``parse -> layout_flowgraph -> lines``) and assert genuine rendered
geometry/topology — arrowhead glyphs, edge labels, row ordering, and the
degradation contract — not merely "no exception raised".
"""

from __future__ import annotations

import re

import pytest

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


def test_multiple_labeled_back_edges_do_not_erase_each_other():
    # Regression: the router used to draw each edge's line+label inline in
    # declaration order, so a later edge's line could silently overwrite an
    # earlier edge's already-placed label. Both r1 and r2 must survive, and
    # with real separation — not just "r1" as a bare substring of a
    # concatenated "r2r1" run.
    source = "graph TD\nA-->B\nB-->C\nC-->|r1|A\nC-->|r2|B\n"
    lines = render_flowchart(source, width=80)
    assert lines
    text = "\n".join(lines)
    assert "r1" in text
    assert "r2" in text
    assert "r1r2" not in text and "r2r1" not in text


def test_lr_short_edge_label_renders_in_full():
    # Regression: the horizontal label placer used to constrain a label to
    # the clear run between two adjacent reserved box borders, clipping
    # "hello" down to just "el". The rank-band gap now widens to fit the
    # label (see mermaid_flow_layout._rank_gap_overrides).
    source = "graph LR\nA -->|hello| B\n"
    lines = render_flowchart(source, width=80)
    assert lines
    text = "\n".join(lines)
    assert "hello" in text


# --------------------------------------------------------------------------
# Labeled back-edge cycle — a shape that stresses the router's back-edge
# lane allocation and label placement
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
# Self-loop — a node edge back to itself
# --------------------------------------------------------------------------


def test_self_loop_renders_visible_loop_and_arrowhead():
    # A renderer that silently dropped self-loops would still pass a bare
    # "non-empty, contains A and B" smoke check — assert the loop's real
    # geometry: an arrowhead, and glyphs extending past the node's own box
    # border (a dropped loop renders only the bare box).
    source = "graph TD\nA-->B\nA-->A\n"
    lines = render_flowchart(source, width=80)
    assert lines
    text = "\n".join(lines)
    assert "A" in text and "B" in text
    assert _ARROW_RE.search(text)
    box_right_col = max(line.index("\u2510") for line in lines if "\u2510" in line)
    assert any(len(line.rstrip()) > box_right_col + 1 for line in lines), (
        "expected loop glyphs extending past a node box's right border"
    )


def test_labeled_self_loop_renders_loop_arrowhead_and_label():
    source = "graph TD\nA-->|again|A\n"
    lines = render_flowchart(source, width=80)
    assert lines
    text = "\n".join(lines)
    assert "A" in text
    assert "again" in text
    assert _ARROW_RE.search(text)
    box_right_col = max(line.index("\u2510") for line in lines if "\u2510" in line)
    assert any(len(line.rstrip()) > box_right_col + 1 for line in lines)


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
# Smoke: labeled fan-in/fan-out around one decision node
# --------------------------------------------------------------------------


def test_labeled_fan_in_and_fan_out_around_one_decision_node():
    # Check is a crowded junction: two labeled edges fan in (go, wait, both
    # crossing the same Alpha/Beta-to-Check band) and two fan out (yes, no,
    # both crossing the same Check-to-Proceed/Abort band). Each sibling in
    # a band must get its own jog row so its label survives distinct and
    # unfused, rather than the pair piling onto one shared row.
    source = (
        "flowchart TD\n"
        "    Alpha -->|go| Check{Ready?}\n"
        "    Beta -->|wait| Check\n"
        "    Check -->|yes| Proceed[Continue]\n"
        "    Check -->|no| Abort[Stop]\n"
    )
    lines = render_flowchart(source, width=100)
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)
    text = "\n".join(lines)
    labels = ["go", "wait", "yes", "no"]
    for label in labels:
        assert text.count(label) == 1, f"{label!r} must appear exactly once: {lines!r}"
    for name in ("Alpha", "Beta", "Ready?", "Continue", "Stop"):
        assert name in text

    # None fused onto a node's own name/border row.
    for label in labels:
        row = _row_of(lines, label)
        for name in ("Alpha", "Beta", "Ready?", "Continue", "Stop"):
            assert name not in lines[row], (
                f"{label!r} landed on {name}'s own row: {lines[row]!r}"
            )

    # None detached below the whole diagram body.
    last_box_row = max(i for i, line in enumerate(lines) if _BOX_GLYPH_RE.search(line))
    for label in labels:
        row = _row_of(lines, label)
        assert row <= last_box_row, f"{label!r} detached below the diagram: {lines!r}"

    # Each pair of labeled edges sharing one band (fan-in into Check,
    # fan-out from Check) must land on its own distinct row rather than
    # fusing onto one shared row.
    for a, b in (("go", "wait"), ("yes", "no")):
        row_a, row_b = _row_of(lines, a), _row_of(lines, b)
        assert row_a != row_b, (
            f"{a!r} and {b!r} both landed on row {row_a}: {lines[row_a]!r}"
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


def test_unrecognized_body_line_forces_raw_echo():
    source = "graph TD\nA-->B\nthis is not mermaid ┌"
    lines = render_flowchart(source, width=80)
    assert lines == ["graph TD", "A-->B", "this is not mermaid ?"]
    text = "\n".join(lines)
    assert not _BOX_GLYPH_RE.search(text)


def test_unterminated_subgraph_forces_raw_echo():
    source = "graph TD\nsubgraph S\nA-->B"
    lines = render_flowchart(source, width=80)
    assert lines == ["graph TD", "subgraph S", "A-->B"]
    text = "\n".join(lines)
    assert not _BOX_GLYPH_RE.search(text)


@pytest.mark.parametrize(
    "source",
    [
        "graph TD\nA-->B\nclass\n",
        "graph TD\nA-->B\nclassDef\n",
        "graph TD\nA-->B\nclassDef important\n",
        "graph TD\nA-->B\nstyle\n",
        "graph TD\nA-->B\nclick\n",
        "graph TD\nA-->B\nlinkStyle\n",
        "graph TD\nA-->B\naccTitle\n",
        "graph TD\nA-->B\naccDescr\n",
    ],
)
def test_malformed_presentational_directive_forces_raw_echo(source):
    lines = render_flowchart(source, width=80)
    assert lines == [line.rstrip() for line in source.splitlines()]
    text = "\n".join(lines)
    assert not _BOX_GLYPH_RE.search(text)


def test_presentational_directives_with_acc_title_and_descr_still_render_natively():
    source = """graph TD
A-->B
classDef important fill:#f00
class A important
style A fill:#fff
click A \"http://example.com\"
linkStyle 0 stroke:#f00
accTitle Demo title
accDescr Demo description
accTitle: Demo title
accDescr: Demo description
"""
    lines = render_flowchart(source, width=80)
    text = "\n".join(lines)
    assert "A" in text and "B" in text
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)


def test_degraded_echo_sanitizes_box_glyphs_present_in_raw_source():
    # Regression: the raw-echo path used to be a plain rstrip of the
    # source, so a literal box-drawing/geometric glyph typed into
    # otherwise-malformed source (e.g. a stray "\u250c") survived into the
    # echo, which the downstream attach viewer could misdetect as a
    # successful render. The echo must now contain NONE of those glyphs.
    source = "not a diagram\n\u250c\n"
    lines = render_flowchart(source, width=80)
    text = "\n".join(lines)
    assert not _BOX_GLYPH_RE.search(text)
    assert lines[0] == "not a diagram"
    assert "\u250c" not in lines[1]


def test_render_flowchart_never_raises_and_degrades_cleanly_on_garbage_input():
    # Defensive: assorted odd inputs must never raise. A bare
    # "isinstance(lines, list)" would also accept a renderer that returned
    # `[]`, a raw echo, or a bogus boxed diagram for every case — assert
    # the actual degradation semantics instead: whichever inputs don't
    # render real box glyphs must be an *exact* rstripped echo of the
    # source (the load-bearing contract), not merely "some list".
    for source in ("", "\n\n\n", "graph", "flowchart LR\n", "graph TD\nA-->\n"):
        lines = render_flowchart(source, width=80)
        assert isinstance(lines, list)
        text = "\n".join(lines)
        if not _BOX_GLYPH_RE.search(text):
            assert lines == [line.rstrip() for line in source.splitlines()], (
                f"degraded output for {source!r} must be an exact raw echo, got {lines!r}"
            )
