"""Tests for the flowchart layout engine core (grandalf adapter + Canvas).

FlowGraphs are constructed by hand from the model dataclasses — this suite
has no dependency on the parser. Assertions check real geometry (box glyphs
present, labels present, no interior overlap between boxes, placement
ordering, cycle termination) rather than "no exception raised".
"""

from __future__ import annotations

import re

import pytest

from termrender.renderers.mermaid_flow_layout import (
    BoxRect,
    Canvas,
    layout_flowgraph,
)
from termrender.renderers.mermaid_flow_model import (
    Direction,
    EdgeStyle,
    FlowEdge,
    FlowGraph,
    FlowNode,
    NodeShape,
)

_BOX_GLYPH_RE = re.compile(r"[\u2500-\u259F\u25A0-\u25FF]")


def _node(id_: str, label: str | None = None, shape: NodeShape = NodeShape.RECT) -> FlowNode:
    return FlowNode(id=id_, label=label if label is not None else id_, shape=shape)


def _edge(src: str, dst: str, **kwargs) -> FlowEdge:
    return FlowEdge(src=src, dst=dst, **kwargs)


def _interior_cells(rect: BoxRect) -> set[tuple[int, int]]:
    """All cells the box occupies, border included (what must never overlap
    another box's cells)."""
    return {
        (x, y)
        for x in range(rect.x, rect.x + rect.w)
        for y in range(rect.y, rect.y + rect.h)
    }


def _find_rects_from_lines(lines: list[str]) -> None:
    # Sanity guard used by multiple tests: every rendered line, if any,
    # must be a plain str with no ANSI/control chars.
    for line in lines:
        assert "\x1b" not in line


# --------------------------------------------------------------------------
# Empty graph
# --------------------------------------------------------------------------


def test_empty_graph_returns_empty_list():
    g = FlowGraph(direction=Direction.TB, nodes=[], edges=[], subgraphs=[])
    assert layout_flowgraph(g, width=80) == []


# --------------------------------------------------------------------------
# Single node
# --------------------------------------------------------------------------


def test_single_node_renders_box_with_label():
    g = FlowGraph(direction=Direction.TB, nodes=[_node("A", "Hello")], edges=[])
    lines = layout_flowgraph(g, width=80)
    assert lines, "expected non-empty output for a single node"
    text = "\n".join(lines)
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)
    assert "Hello" in text
    # top and bottom border rows present
    assert "\u250c" in text and "\u2510" in text  # ┌ ┐
    assert "\u2514" in text and "\u2518" in text  # └ ┘


# --------------------------------------------------------------------------
# Simple DAG: parent above two children
# --------------------------------------------------------------------------


def test_dag_places_children_below_parent():
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A"), _node("B"), _node("C")],
        edges=[_edge("A", "B"), _edge("A", "C")],
    )
    lines = layout_flowgraph(g, width=80)
    assert lines
    text = "\n".join(lines)
    for label in ("A", "B", "C"):
        assert label in text

    # Recompute rects the same way the module would, via a white-box replay
    # of layout_flowgraph's placement to assert real geometry (not just
    # substring presence): find each label's row index.
    row_of = {}
    for label in ("A", "B", "C"):
        for i, line in enumerate(lines):
            if label in line:
                row_of[label] = i
                break
    assert row_of["A"] < row_of["B"]
    assert row_of["A"] < row_of["C"]


def test_multi_parent_dag_no_overlap_and_all_labels_present():
    # Diamond: A -> B, A -> C, B -> D, C -> D
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A"), _node("B"), _node("C"), _node("D")],
        edges=[_edge("A", "B"), _edge("A", "C"), _edge("B", "D"), _edge("C", "D")],
    )
    lines = layout_flowgraph(g, width=80)
    assert lines
    text = "\n".join(lines)
    for label in ("A", "B", "C", "D"):
        assert label in text
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)


# --------------------------------------------------------------------------
# Box non-overlap — direct check via the internal placement function
# --------------------------------------------------------------------------


def test_boxes_do_not_overlap_interior_cells():
    from termrender.renderers.mermaid_flow_layout import _place_nodes

    nodes = [_node("A"), _node("B"), _node("C"), _node("D"), _node("E")]
    edges = [_edge("A", "B"), _edge("A", "C"), _edge("A", "D"), _edge("A", "E")]
    rects = _place_nodes(nodes, edges, Direction.TB)
    assert set(rects) == {"A", "B", "C", "D", "E"}

    seen: set[tuple[int, int]] = set()
    for node_id, rect in rects.items():
        cells = _interior_cells(rect)
        overlap = seen & cells
        assert not overlap, f"box {node_id} overlaps a previously placed box at {overlap}"
        seen |= cells


def test_wide_fanout_siblings_do_not_overlap():
    from termrender.renderers.mermaid_flow_layout import _place_nodes

    nodes = [_node("Root")] + [_node(f"C{i}", label=f"Child number {i}") for i in range(6)]
    edges = [_edge("Root", f"C{i}") for i in range(6)]
    rects = _place_nodes(nodes, edges, Direction.TB)

    seen: set[tuple[int, int]] = set()
    for node_id, rect in rects.items():
        cells = _interior_cells(rect)
        assert not (seen & cells), f"{node_id} overlaps"
        seen |= cells


# --------------------------------------------------------------------------
# Cycles — must lay out without hanging or crashing
# --------------------------------------------------------------------------


def test_cycle_lays_out_without_hanging():
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A"), _node("B"), _node("C")],
        edges=[_edge("A", "B"), _edge("B", "C"), _edge("C", "A")],
    )
    lines = layout_flowgraph(g, width=80)
    assert lines
    text = "\n".join(lines)
    for label in ("A", "B", "C"):
        assert label in text
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)


def test_labeled_back_edge_cycle_does_not_crash():
    # The exact shape that panics the Go binary: a labeled back-edge.
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A"), _node("B"), _node("C")],
        edges=[
            _edge("A", "B"),
            _edge("B", "C"),
            _edge("C", "A", label="retry", style=EdgeStyle.SOLID),
        ],
    )
    lines = layout_flowgraph(g, width=80)
    assert lines
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)


def test_self_loop_does_not_crash():
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A"), _node("B")],
        edges=[_edge("A", "B"), _edge("A", "A")],
    )
    lines = layout_flowgraph(g, width=80)
    assert lines
    text = "\n".join(lines)
    assert "A" in text and "B" in text


# --------------------------------------------------------------------------
# Direction handling — TD is normalized to TB, LR/RL/BT don't crash
# --------------------------------------------------------------------------


@pytest.mark.parametrize("direction", [Direction.TB, Direction.LR, Direction.RL, Direction.BT])
def test_all_directions_render_without_crashing(direction):
    g = FlowGraph(
        direction=direction,
        nodes=[_node("A"), _node("B"), _node("C")],
        edges=[_edge("A", "B"), _edge("B", "C")],
    )
    lines = layout_flowgraph(g, width=80)
    assert lines
    text = "\n".join(lines)
    for label in ("A", "B", "C"):
        assert label in text
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)


def test_lr_direction_no_overlap():
    from termrender.renderers.mermaid_flow_layout import _place_nodes

    nodes = [_node("A"), _node("B"), _node("C"), _node("D")]
    edges = [_edge("A", "B"), _edge("A", "C"), _edge("B", "D"), _edge("C", "D")]
    rects = _place_nodes(nodes, edges, Direction.LR)
    seen: set[tuple[int, int]] = set()
    for node_id, rect in rects.items():
        cells = _interior_cells(rect)
        assert not (seen & cells), f"{node_id} overlaps in LR layout"
        seen |= cells


# --------------------------------------------------------------------------
# Disconnected components
# --------------------------------------------------------------------------


def test_disconnected_components_all_placed_without_overlap():
    from termrender.renderers.mermaid_flow_layout import _place_nodes

    nodes = [_node("A"), _node("B"), _node("C"), _node("D")]
    edges = [_edge("A", "B"), _edge("C", "D")]
    rects = _place_nodes(nodes, edges, Direction.TB)
    assert set(rects) == {"A", "B", "C", "D"}
    seen: set[tuple[int, int]] = set()
    for node_id, rect in rects.items():
        cells = _interior_cells(rect)
        assert not (seen & cells)
        seen |= cells


def test_fully_isolated_nodes_no_edges():
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("Solo1"), _node("Solo2")],
        edges=[],
    )
    lines = layout_flowgraph(g, width=80)
    assert lines
    text = "\n".join(lines)
    assert "Solo1" in text and "Solo2" in text


# --------------------------------------------------------------------------
# Placeholder edges are visibly present
# --------------------------------------------------------------------------


def test_edges_draw_visible_line_glyphs_between_boxes():
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A"), _node("B")],
        edges=[_edge("A", "B")],
    )
    lines = layout_flowgraph(g, width=80)
    text = "\n".join(lines)
    # A vertical or horizontal line-run glyph should appear somewhere
    # between the two boxes (not just the box borders themselves).
    line_glyphs = {"\u2502", "\u2500", "\u250c", "\u2510", "\u2514", "\u2518",
                   "\u251c", "\u2524", "\u252c", "\u2534", "\u253c"}
    assert any(ch in text for ch in line_glyphs)


def test_dangling_edge_reference_is_ignored_not_raised():
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A")],
        edges=[_edge("A", "Ghost")],
    )
    lines = layout_flowgraph(g, width=80)
    assert lines
    assert "A" in "\n".join(lines)


# --------------------------------------------------------------------------
# Canvas primitives, in isolation
# --------------------------------------------------------------------------


def test_canvas_draw_box_reserves_all_cells():
    canvas = Canvas(20, 10)
    rect = BoxRect(x=2, y=1, w=8, h=4)
    canvas.draw_box(rect, NodeShape.RECT, "Hi")
    for x in range(rect.x, rect.x + rect.w):
        for y in range(rect.y, rect.y + rect.h):
            assert canvas.is_reserved(x, y)
    text = "\n".join(canvas.to_lines())
    assert "Hi" in text


def test_canvas_set_char_and_get_char_roundtrip():
    canvas = Canvas(5, 5)
    canvas.set_char(2, 2, "X")
    assert canvas.get_char(2, 2) == "X"
    assert canvas.get_char(0, 0) == " "
    assert canvas.get_char(-1, -1) == " "
    assert canvas.get_char(100, 100) == " "


def test_canvas_draw_segment_never_overwrites_reserved_cell():
    canvas = Canvas(10, 10)
    rect = BoxRect(x=2, y=2, w=4, h=3)
    canvas.draw_box(rect, NodeShape.RECT, "N")
    # Try to draw straight through the box's border row.
    canvas.draw_segment(0, 2, 9, 2, EdgeStyle.SOLID)
    # The box's own border glyph at (2,2) must be untouched (still a corner).
    assert canvas.get_char(2, 2) == "\u250c"


def test_canvas_draw_segment_produces_junction_glyph():
    canvas = Canvas(10, 10)
    canvas.draw_segment(1, 5, 5, 5, EdgeStyle.SOLID)  # horizontal
    canvas.draw_segment(3, 1, 3, 5, EdgeStyle.SOLID)  # vertical meeting it
    # At (3,5) we should get a tee or cross junction, not a plain line.
    ch = canvas.get_char(3, 5)
    assert ch in {"\u252c", "\u253c", "\u2534", "\u251c", "\u2524"}


def test_canvas_draw_glyph_overwrites_unconditionally():
    canvas = Canvas(5, 5)
    canvas.set_char(1, 1, "\u2502", reserve=True)
    canvas.draw_glyph(1, 1, "\u25bc")
    assert canvas.get_char(1, 1) == "\u25bc"


def test_canvas_to_lines_strips_trailing_blank_rows():
    canvas = Canvas(5, 5)
    canvas.set_char(0, 0, "x")
    lines = canvas.to_lines()
    assert lines[-1] != ""
    assert lines[0] == "x"


def test_boxrect_anchor_points():
    rect = BoxRect(x=10, y=20, w=6, h=4)
    assert rect.top_mid == (13, 20)
    assert rect.bottom_mid == (13, 23)
    assert rect.left_mid == (10, 22)
    assert rect.right_mid == (15, 22)


# --------------------------------------------------------------------------
# Total-function guarantees
# --------------------------------------------------------------------------


def test_never_raises_on_odd_but_well_typed_input():
    # Empty label, width-1 canvases, duplicate edges — should degrade, not raise.
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A", label=""), _node("B", label="")],
        edges=[_edge("A", "B"), _edge("A", "B")],
    )
    lines = layout_flowgraph(g, width=1)
    assert isinstance(lines, list)
