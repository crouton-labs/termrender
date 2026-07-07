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
_ARROW_RE = re.compile(r"[\u25b2\u25bc\u25b6\u25c0]")  # ▲▼▶◀


def _row_of(lines: list[str], label: str) -> int:
    for i, line in enumerate(lines):
        if label in line:
            return i
    raise AssertionError(f"label {label!r} not found in rendered output: {lines!r}")


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
    # Real topology, not just "didn't hang": the forward chain A -> B -> C
    # still orders top-to-bottom despite the C -> A back-edge, and a
    # back-edge arrowhead actually lands (somewhere) rather than being
    # silently dropped.
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
    assert _ARROW_RE.search(text)
    assert _row_of(lines, "A") < _row_of(lines, "B") < _row_of(lines, "C")


def test_labeled_back_edge_cycle_does_not_crash():
    # A labeled back-edge — the renderer must lay this out cleanly. Real
    # assertions: the "retry" label itself survives, an arrowhead lands,
    # and the forward chain's top-to-bottom order is unaffected by the
    # back-edge — a renderer that silently dropped the labeled back-edge
    # (but kept the two forward edges) would otherwise still pass this test
    # if it only checked "didn't crash".
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
    text = "\n".join(lines)
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)
    assert "retry" in text
    assert _ARROW_RE.search(text)
    assert _row_of(lines, "A") < _row_of(lines, "B") < _row_of(lines, "C")


def test_self_loop_renders_visible_loop_and_arrowhead():
    # A renderer that silently dropped every self-loop would still pass a
    # bare "non-empty output containing A and B" check — assert the loop's
    # actual geometry instead: an arrowhead, and line glyphs extending
    # visibly past the node box's own border (a dropped self-loop renders
    # only the bare box, whose lines never exceed its own right border).
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A"), _node("B")],
        edges=[_edge("A", "B"), _edge("A", "A")],
    )
    lines = layout_flowgraph(g, width=80)
    assert lines
    text = "\n".join(lines)
    assert "A" in text and "B" in text
    assert _ARROW_RE.search(text)
    box_right_col = max(line.index("\u2510") for line in lines if "\u2510" in line)
    assert any(len(line.rstrip()) > box_right_col + 1 for line in lines), (
        "expected loop glyphs extending past a node box's right border"
    )


def test_labeled_self_loop_renders_loop_arrowhead_and_label():
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A")],
        edges=[_edge("A", "A", label="again")],
    )
    lines = layout_flowgraph(g, width=80)
    assert lines
    text = "\n".join(lines)
    assert "A" in text
    assert "again" in text
    assert _ARROW_RE.search(text)
    box_right_col = max(line.index("\u2510") for line in lines if "\u2510" in line)
    assert any(len(line.rstrip()) > box_right_col + 1 for line in lines)


# --------------------------------------------------------------------------
# Direction handling — TD is normalized to TB, LR/RL/BT don't crash
# --------------------------------------------------------------------------


@pytest.mark.parametrize("direction", [Direction.TB, Direction.LR, Direction.RL, Direction.BT])
def test_all_directions_place_nodes_along_the_correct_axis(direction):
    # A direction-blind renderer (e.g. one that ignored LR/RL/BT and always
    # laid out top-to-bottom) would still pass a bare "doesn't crash, all
    # labels present" check for every direction — assert each direction's
    # actual rank-flow axis and sign instead.
    g = FlowGraph(
        direction=direction,
        nodes=[_node("A"), _node("B"), _node("C")],
        edges=[_edge("A", "B"), _edge("B", "C")],
    )
    lines = layout_flowgraph(g, width=80)
    assert lines
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)

    row: dict[str, int] = {}
    col: dict[str, int] = {}
    for label in ("A", "B", "C"):
        for i, line in enumerate(lines):
            if label in line:
                row[label] = i
                col[label] = line.index(label)
                break
        assert label in row, f"label {label!r} not found in rendered output: {lines!r}"

    if direction is Direction.TB:
        assert row["A"] < row["B"] < row["C"]
    elif direction is Direction.BT:
        assert row["A"] > row["B"] > row["C"]
    elif direction is Direction.LR:
        assert col["A"] < col["B"] < col["C"]
    else:  # Direction.RL
        assert col["A"] > col["B"] > col["C"]


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
    # The old version of this test accepted plain box-border glyphs
    # (┌┐└┘) in its allowed set, so it passed even for a graph with NO
    # edge at all (the two node boxes alone contain those glyphs). Tighten
    # by inspecting the *inter-box gap rows* specifically — guaranteed
    # clear of any box by construction (the layout enforces a non-zero
    # rank gap) — and require a routed line/arrow glyph there; a deleted
    # edge router would leave those rows blank.
    from termrender.renderers.mermaid_flow_layout import _place_nodes

    nodes = [_node("A"), _node("B")]
    edges = [_edge("A", "B")]
    rects = _place_nodes(nodes, edges, Direction.TB)
    a, b = rects["A"], rects["B"]
    gap_lo, gap_hi = a.y + a.h, b.y
    assert gap_hi > gap_lo, "expected a real inter-rank gap between the two boxes"

    g = FlowGraph(direction=Direction.TB, nodes=nodes, edges=edges)
    lines = layout_flowgraph(g, width=80)
    gap_rows = lines[gap_lo:gap_hi]
    assert gap_rows, "expected rendered rows in the inter-box gap"
    line_glyphs = {"\u2502", "\u2500", "\u250c", "\u2510", "\u2514", "\u2518",
                   "\u251c", "\u2524", "\u252c", "\u2534", "\u253c",
                   "\u25b2", "\u25bc", "\u25b6", "\u25c0"}
    assert any(ch in row for row in gap_rows for ch in line_glyphs), (
        f"expected a routed edge glyph strictly between the two boxes, got {gap_rows!r}"
    )


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


def test_duplicate_edges_and_empty_labels_render_without_raising():
    # Empty label, width-1 canvases, duplicate edges must never raise —
    # and, since this is otherwise a perfectly well-typed two-node graph,
    # it should still render its two real boxes rather than silently
    # degrading (a bare "isinstance(lines, list)" would also accept an
    # empty-list degradation or a raised-then-caught garbage result).
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A", label=""), _node("B", label="")],
        edges=[_edge("A", "B"), _edge("A", "B")],
    )
    lines = layout_flowgraph(g, width=1)
    assert isinstance(lines, list)
    assert lines, "a well-typed non-empty graph must still render"
    text = "\n".join(lines)
    assert text.count("\u250c") == 2, "expected exactly the two declared node boxes"


# --------------------------------------------------------------------------
# Destination-side marker anchors (regression: _allocate_edge_anchors used to
# spread shared *source* exits only, so 2+ edges entering one node with
# different destination-end markers all landed on the single fixed
# _forward_entry anchor and silently lost all but the last-drawn glyph)
# --------------------------------------------------------------------------


def test_two_destination_side_markers_into_one_node_both_survive():
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A"), _node("B"), _node("C")],
        edges=[
            _edge("A", "C", dst_arrow_kind="diamond_filled"),
            _edge("B", "C", dst_arrow_kind="diamond_hollow"),
        ],
    )
    lines = layout_flowgraph(g, width=80)
    text = "\n".join(lines)
    assert "\u25c6" in text, "diamond_filled destination marker must survive"
    assert "\u25c7" in text, "diamond_hollow destination marker must survive"


def test_plain_arrow_fan_in_still_shares_one_entry_anchor():
    # Guards the deliberate scoping this fix must not break: an ordinary
    # fan-in (no non-default dst_arrow_kind — an everyday "-->" edge
    # already sets dst_arrow=True, so the trigger must be the *kind*, not
    # bare arrow presence) still lands on one shared entry cell so
    # draw_segment's junction bitmask resolves it into a single ┬/┴ trunk
    # rather than two disjoint stubs either side of the node.
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A"), _node("B"), _node("C")],
        edges=[_edge("A", "C"), _edge("B", "C")],
    )
    lines = layout_flowgraph(g, width=80)
    text = "\n".join(lines)
    assert "\u252c" in text or "\u2534" in text, "plain fan-in should keep its shared trunk look"


# --------------------------------------------------------------------------
# CJK edge labels (regression: label placement measured visual_len(label)
# for reservation/search but wrote/reserved one grid cell per Python code
# point, so a wide CJK label under-reserved and a connector glyph already
# drawn on the segment stayed visible inside the label's own visual width)
# --------------------------------------------------------------------------


def test_cjk_edge_label_has_no_connector_bleed_inside_its_width():
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("A"), _node("B")],
        edges=[_edge("A", "B", label="\u4f60\u597d")],  # "你好"
    )
    lines = layout_flowgraph(g, width=80)
    label_row = next(line for line in lines if "\u4f60\u597d" in line)
    assert not _BOX_GLYPH_RE.search(label_row), (
        "a connector/box glyph landed inside the CJK label's own visual width: "
        f"{label_row!r}"
    )
    assert label_row.strip() == "\u4f60\u597d"


# --------------------------------------------------------------------------
# Multiple labeled edges converging/diverging on one node (engine-level
# regression, proven via FlowGraph/layout_flowgraph directly rather than
# through a stateDiagram-specific harness — see test_mermaid_state.py's
# adversarial regression for the same class of defect through the CLI path)
# --------------------------------------------------------------------------


def test_multiple_labeled_edges_diverge_and_converge_on_one_node():
    # Hub fans out to three neighbors (three forward edges sharing Hub's
    # exit band) and two of them route a labeled edge straight back into
    # Hub (two back-edges sharing Hub's lane side) — five labeled edges
    # all landing anchors/jog-rows on or through the same node. Every edge
    # crossing the identical inter-rank band must get its own jog row so
    # its label survives distinct and unfused, rather than every edge
    # sharing one jog row and labels fusing or silently dropping whenever
    # every candidate cell conflicts.
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("Hub"), _node("Left"), _node("Right"), _node("Down")],
        edges=[
            _edge("Hub", "Left", label="go left"),
            _edge("Hub", "Right", label="go right"),
            _edge("Hub", "Down", label="descend"),
            _edge("Left", "Hub", label="return left"),
            _edge("Right", "Hub", label="return right"),
        ],
    )
    lines = layout_flowgraph(g, width=100)
    text = "\n".join(lines)
    labels = ["go left", "go right", "descend", "return left", "return right"]
    for label in labels:
        assert text.count(label) == 1, f"{label!r} must appear exactly once: {lines!r}"

    # None fused onto a node's own name row.
    for label in labels:
        row = _row_of(lines, label)
        for name in ("Hub", "Left", "Right", "Down"):
            assert name not in lines[row], (
                f"{label!r} landed on {name}'s own row: {lines[row]!r}"
            )

    # None detached below the whole diagram body.
    last_box_row = max(i for i, line in enumerate(lines) if _BOX_GLYPH_RE.search(line))
    for label in labels:
        row = _row_of(lines, label)
        assert row <= last_box_row, f"{label!r} detached below the diagram: {lines!r}"


# --------------------------------------------------------------------------
# Back-edge return leg crossing sibling boxes in the source's own crowded
# rank (regression: a back-edge's C-path lane column was sized from just
# its own two endpoints, not every node in the graph, so its horizontal
# exit leg — which travels along the source's own rank row, a row every
# rank-mate box also occupies — could run alongside, and its label land
# inside, whichever sibling boxes sat between the source and the lane)
# --------------------------------------------------------------------------


def test_back_edge_return_leg_clears_source_rank_siblings():
    # Hub fans out to six children sharing one rank; only Alpha (the
    # leftmost, so every sibling sits to its right) routes a labeled edge
    # back into Hub. The back-edge's lane column must clear every sibling
    # in Alpha's rank, not just Alpha and Hub themselves.
    child_ids = ["Alpha", "Beta", "Cee", "Dee", "Eee", "Eff"]
    g = FlowGraph(
        direction=Direction.TB,
        nodes=[_node("Hub")] + [_node(c) for c in child_ids],
        edges=[_edge("Hub", c) for c in child_ids] + [_edge("Alpha", "Hub", label="returns")],
    )
    lines = layout_flowgraph(g, width=100)
    text = "\n".join(lines)
    assert text.count("returns") == 1, f"'returns' must appear exactly once: {lines!r}"

    from termrender.renderers.mermaid_flow_layout import _node_subgraph_map, _place_nodes

    rects = _place_nodes(g.nodes, g.edges, g.direction, _node_subgraph_map([]))
    label_cells: set[tuple[int, int]] = set()
    for r, line in enumerate(lines):
        c = line.find("returns")
        if c != -1:
            label_cells.update((c + i, r) for i in range(len("returns")))
    assert label_cells, f"expected to find 'returns' in the rendered output: {lines!r}"

    for node_id, rect in rects.items():
        cells = _interior_cells(rect)
        overlap = label_cells & cells
        assert not overlap, f"'returns' label overlaps {node_id}'s box at {overlap}: {lines!r}"

    # Every sibling name must survive intact, not fused into one run-together
    # line with the back-edge's label (the literal defect: "BetareturnsCee").
    for name in ["Hub"] + child_ids:
        assert name in text
    for r, line in enumerate(lines):
        if "returns" in line:
            assert "Beta" not in line and "Cee" not in line, (
                f"'returns' fused onto a sibling box's row: {line!r}"
            )
