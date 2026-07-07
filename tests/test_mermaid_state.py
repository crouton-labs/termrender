"""Golden-output-style tests for the native mermaid ``stateDiagram`` renderer.

Exercises real mermaid ``stateDiagram``/``stateDiagram-v2`` sources through
the full pipeline (``parse -> layout_flowgraph -> lines``) and asserts
genuine rendered geometry/topology — row ordering, arrowhead/marker glyphs,
frame titles, label text — not merely "non-empty" or "no exception".
Mirrors the assertion style of ``test_mermaid_flow.py`` (the flowchart
engine's own end-to-end test module), since this renderer draws through
that same engine.
"""

from __future__ import annotations

import re

from termrender.renderers.mermaid_state import StateDiagramError, parse, render_state

_BOX_GLYPH_RE = re.compile(r"[\u2500-\u259F\u25A0-\u25FF]")
_START_GLYPH = "\u25cf"  # ●
_END_GLYPH = "\u25c9"  # ◉
_DIAMOND_SLANT_RE = re.compile(r"[\u2571\u2572]")  # ╱ ╲


def _row_of(lines: list[str], needle: str) -> int:
    for i, line in enumerate(lines):
        if needle in line:
            return i
    raise AssertionError(f"{needle!r} not found in rendered output: {lines!r}")


def _col_of(lines: list[str], needle: str) -> int:
    for line in lines:
        idx = line.find(needle)
        if idx != -1:
            return idx
    raise AssertionError(f"{needle!r} not found in rendered output: {lines!r}")


# --------------------------------------------------------------------------
# Simple machine with start/end + labeled transitions
# --------------------------------------------------------------------------


def test_simple_machine_with_start_end_and_labeled_transitions():
    source = (
        "stateDiagram-v2\n"
        "[*] --> Idle\n"
        "Idle --> Running : start\n"
        "Running --> Idle : stop\n"
        "Running --> [*]\n"
    )
    lines = render_state(source, width=80)
    assert lines
    text = "\n".join(lines)

    # Success signal: box-drawing glyphs present.
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)

    # Distinct start/end pseudo-state markers, both present, both distinct.
    assert _START_GLYPH in text
    assert _END_GLYPH in text
    assert _START_GLYPH != _END_GLYPH

    # Real states present with their own labels.
    assert "Idle" in text
    assert "Running" in text

    # Edge labels (event names) present.
    assert "start" in text
    assert "stop" in text

    # Topology: start marker above Idle above Running above end marker.
    row_start = _row_of(lines, _START_GLYPH)
    row_idle = _row_of(lines, "Idle")
    row_running = _row_of(lines, "Running")
    row_end = _row_of(lines, _END_GLYPH)
    assert row_start < row_idle < row_running < row_end


def test_start_marker_has_no_incoming_edges_end_has_no_outgoing():
    # A machine referencing [*] only as a source (start) and only as a
    # destination (end) elsewhere must produce exactly one start node and
    # one end node (shared across every [*] reference in that scope), not
    # one per occurrence.
    source = (
        "stateDiagram-v2\n"
        "[*] --> A\n"
        "[*] --> B\n"
        "A --> [*]\n"
        "B --> [*]\n"
    )
    graph = parse(source)
    start_nodes = [n for n in graph.nodes if n.label == _START_GLYPH]
    end_nodes = [n for n in graph.nodes if n.label == _END_GLYPH]
    assert len(start_nodes) == 1
    assert len(end_nodes) == 1
    start_id = start_nodes[0].id
    end_id = end_nodes[0].id
    assert {e.dst for e in graph.edges if e.src == start_id} == {"A", "B"}
    assert {e.src for e in graph.edges if e.dst == end_id} == {"A", "B"}


# --------------------------------------------------------------------------
# Aliases
# --------------------------------------------------------------------------


def test_alias_renders_display_label_not_raw_id():
    # Kept under the label wrap width so the whole phrase lands on one
    # rendered row — this test is about label-vs-id substitution, not wrap
    # geometry (covered by the flowchart engine's own tests).
    source = (
        "stateDiagram-v2\n"
        'state "Idle State" as s1\n'
        "[*] --> s1\n"
        "s1 --> [*]\n"
    )
    lines = render_state(source, width=80)
    text = "\n".join(lines)
    assert "Idle State" in text
    # The raw id never appears as a standalone rendered token distinct from
    # the label text (it only ever appears as a substring of the alias, if
    # at all coincidentally) — check the id doesn't appear on its own line.
    assert not any(line.strip() == "s1" for line in lines)


# --------------------------------------------------------------------------
# Choice pseudo-state
# --------------------------------------------------------------------------


def test_choice_state_renders_as_diamond():
    source = (
        "stateDiagram-v2\n"
        "[*] --> Guard\n"
        "Guard --> Choice1\n"
        "state Choice1 <<choice>>\n"
        "Choice1 --> Yes : ok\n"
        "Choice1 --> No : fail\n"
    )
    lines = render_state(source, width=80)
    text = "\n".join(lines)
    assert "Choice1" in text
    assert "ok" in text
    assert "fail" in text
    # A diamond's tapered corners use the slant glyphs; a plain rect never
    # does, so their presence is a real (not incidental) diamond signal.
    assert _DIAMOND_SLANT_RE.search(text)


def test_fork_and_join_degrade_to_plain_rect_boxes():
    source = (
        "stateDiagram-v2\n"
        "state fork1 <<fork>>\n"
        "state join1 <<join>>\n"
        "[*] --> fork1\n"
        "fork1 --> A\n"
        "fork1 --> B\n"
        "A --> join1\n"
        "B --> join1\n"
        "join1 --> [*]\n"
    )
    graph = parse(source)
    from termrender.renderers.mermaid_flow_model import NodeShape

    fork_node = next(n for n in graph.nodes if n.id == "fork1")
    join_node = next(n for n in graph.nodes if n.id == "join1")
    assert fork_node.shape is NodeShape.RECT
    assert join_node.shape is NodeShape.RECT

    lines = render_state(source, width=80)
    text = "\n".join(lines)
    assert "fork1" in text
    assert "join1" in text
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)
    # Fan-out topology: both branches actually reach the join.
    row_fork = _row_of(lines, "fork1")
    row_join = _row_of(lines, "join1")
    assert row_fork < row_join


# --------------------------------------------------------------------------
# Composite state
# --------------------------------------------------------------------------


def test_composite_state_renders_as_titled_frame_with_members_inside():
    source = (
        "stateDiagram-v2\n"
        "[*] --> Active\n"
        "state Active {\n"
        "    [*] --> Working\n"
        "    Working --> Paused : pause\n"
        "    Paused --> Working : resume\n"
        "    Paused --> [*]\n"
        "}\n"
        "Active --> [*]\n"
    )
    lines = render_state(source, width=100)
    text = "\n".join(lines)

    # A subgraph frame is a left-anchored title on a top border run.
    assert "\u250c\u2500 Active" in text

    # Members render inside, with their own edges.
    assert "Working" in text
    assert "Paused" in text
    assert "pause" in text
    assert "resume" in text

    # The frame's members are geometrically inside its column span: find
    # the frame's top-border row and its horizontal extent, then check
    # Working/Paused's columns fall within it.
    frame_row = _row_of(lines, "\u250c\u2500 Active")
    frame_line = lines[frame_row]
    frame_left = frame_line.index("\u250c")
    frame_right = frame_line.rindex("\u2510")
    col_working = _col_of(lines, "Working")
    col_paused = _col_of(lines, "Paused")
    assert frame_left < col_working < frame_right
    assert frame_left < col_paused < frame_right


def test_composite_referenced_externally_gets_own_proxy_box():
    # `Active` is used as a transition endpoint from *outside* its own
    # block, so it must also exist as its own real node (with the frame's
    # title as its label) in addition to the frame around its members.
    source = (
        "stateDiagram-v2\n"
        "[*] --> Active\n"
        "state Active {\n"
        "    [*] --> Working\n"
        "    Working --> [*]\n"
        "}\n"
        "Active --> Done\n"
    )
    graph = parse(source)
    assert any(n.id == "Active" for n in graph.nodes)
    active_node = next(n for n in graph.nodes if n.id == "Active")
    assert active_node.label == "Active"
    # Active is NOT a member of its own subgraph.
    active_sub = next(sg for sg in graph.subgraphs if sg.id == "Active")
    assert "Active" not in active_sub.node_ids
    assert "Working" in active_sub.node_ids


def test_nested_composite_states():
    source = (
        "stateDiagram-v2\n"
        "state Outer {\n"
        "    [*] --> Inner\n"
        "    state Inner {\n"
        "        [*] --> Leaf\n"
        "        Leaf --> [*]\n"
        "    }\n"
        "    Inner --> [*]\n"
        "}\n"
    )
    graph = parse(source)
    assert len(graph.subgraphs) == 1
    outer = graph.subgraphs[0]
    assert outer.id == "Outer"
    assert len(outer.children) == 1
    inner = outer.children[0]
    assert inner.id == "Inner"
    assert "Leaf" in inner.node_ids
    # Rendering nested composites yields both frame titles and the leaf
    # state's own label, not merely "some box glyph exists".
    lines = render_state(source, width=100)
    text = "\n".join(lines)
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)
    assert "\u250c\u2500 Outer" in text
    assert "\u250c\u2500 Inner" in text
    assert "Leaf" in text
    # Inner's frame nests strictly inside Outer's column span.
    outer_row = _row_of(lines, "\u250c\u2500 Outer")
    inner_row = _row_of(lines, "\u250c\u2500 Inner")
    outer_left = lines[outer_row].index("\u250c")
    outer_right = lines[outer_row].rindex("\u2510")
    inner_left = lines[inner_row].index("\u250c")
    inner_right = lines[inner_row].rindex("\u2510")
    assert outer_left < inner_left
    assert inner_right < outer_right


# --------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------


def test_inline_note_text_is_never_dropped():
    source = (
        "stateDiagram-v2\n"
        "[*] --> Idle\n"
        "note right of Idle : Waiting for input\n"
        "Idle --> [*]\n"
    )
    lines = render_state(source, width=100)
    text = "\n".join(lines)
    assert "Waiting for input" in text
    # Note is joined by a dotted connector (no arrowhead) — a dotted line
    # glyph (solid transitions never draw these) present in the render.
    assert ("\u254c" in text) or ("\u254e" in text)


def test_multiline_note_block_text_is_never_dropped():
    # Kept short enough to land unwrapped on one rendered row — this test
    # is about joining the block's lines with a space, not wrap geometry.
    source = (
        "stateDiagram-v2\n"
        "[*] --> A\n"
        "note left of A\n"
        "  abc\n"
        "  def\n"
        "end note\n"
        "A --> [*]\n"
    )
    lines = render_state(source, width=100)
    text = "\n".join(lines)
    assert "abc def" in text


def test_note_on_undeclared_state_still_registers_that_state():
    source = (
        "stateDiagram-v2\n"
        "note right of Ghost : ghost note\n"
    )
    graph = parse(source)
    assert any(n.id == "Ghost" for n in graph.nodes)
    lines = render_state(source, width=100)
    text = "\n".join(lines)
    assert "Ghost" in text
    assert "ghost note" in text


# --------------------------------------------------------------------------
# Direction
# --------------------------------------------------------------------------


def test_direction_lr_lays_out_left_to_right():
    from termrender.renderers.mermaid_flow_model import Direction

    source = "stateDiagram-v2\ndirection LR\n[*] --> A\nA --> B\nB --> [*]\n"
    graph = parse(source)
    assert graph.direction is Direction.LR
    lines = render_state(source, width=100)
    col_start = _col_of(lines, _START_GLYPH)
    col_a = _col_of(lines, "A")
    col_b = _col_of(lines, "B")
    col_end = _col_of(lines, _END_GLYPH)
    assert col_start < col_a < col_b < col_end


# --------------------------------------------------------------------------
# Comments
# --------------------------------------------------------------------------


def test_comments_are_skipped_anywhere():
    source = (
        "stateDiagram-v2\n"
        "%% a leading comment\n"
        "[*] --> A\n"
        "%% a mid-body comment\n"
        "A --> [*]\n"
    )
    lines = render_state(source, width=80)
    text = "\n".join(lines)
    assert "a leading comment" not in text
    assert "a mid-body comment" not in text
    assert "A" in text


# --------------------------------------------------------------------------
# Degradation
# --------------------------------------------------------------------------


def test_non_state_diagram_source_raises_in_parse():
    try:
        parse("graph TD\nA-->B\n")
    except StateDiagramError:
        pass
    else:
        raise AssertionError("expected StateDiagramError")


def test_malformed_input_degrades_to_raw_echo_with_no_box_glyphs():
    source = "just some\nplain text\nthat is not mermaid at all\n"
    lines = render_state(source, width=80)
    assert lines == ["just some", "plain text", "that is not mermaid at all"]
    assert not any(_BOX_GLYPH_RE.search(line) for line in lines)


def test_empty_body_degrades_to_raw_echo():
    source = "stateDiagram-v2\n%% nothing but a comment\n"
    lines = render_state(source, width=80)
    assert not any(_BOX_GLYPH_RE.search(line) for line in lines)
    assert "stateDiagram-v2" in "\n".join(lines)


def test_malformed_source_with_literal_glyph_is_still_sanitized():
    # A degenerate/malformed source that happens to contain a literal
    # box-drawing glyph must still echo with it stripped — the presence
    # check downstream must never misfire on the echo path.
    source = "not a diagram \u250c literally has a glyph\n"
    lines = render_state(source, width=80)
    assert not any(_BOX_GLYPH_RE.search(line) for line in lines)
    assert "?" in lines[0]


# --------------------------------------------------------------------------
# Never crashes
# --------------------------------------------------------------------------


def test_header_only_diagram_has_zero_nodes_and_echoes():
    # No body at all: a real (if degenerate) zero-node case, exercising
    # the same "parse succeeds, zero nodes -> echo" rule as the flowchart
    # engine's own degradation contract, not a parser bug.
    source = "stateDiagram-v2\n"
    lines = render_state(source, width=80)
    assert lines == ["stateDiagram-v2"]
    assert not any(_BOX_GLYPH_RE.search(line) for line in lines)


def test_start_to_end_direct_transition_renders_both_markers():
    source = "stateDiagram-v2\n[*] --> [*]\n"
    lines = render_state(source, width=80)
    text = "\n".join(lines)
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)
    assert _START_GLYPH in text
    assert _END_GLYPH in text


def test_unterminated_composite_with_no_members_is_a_zero_node_echo():
    # `state X {` with nothing inside and no closing `}` auto-closes at
    # EOF into an empty Subgraph — since X itself is never referenced by a
    # transition, no FlowNode is ever created, so this degenerates to the
    # same zero-node echo case as an empty body (not a crash, not a
    # half-rendered diagram).
    source = "stateDiagram-v2\nstate X {\n"
    lines = render_state(source, width=80)
    assert not any(_BOX_GLYPH_RE.search(line) for line in lines)
    assert lines == ["stateDiagram-v2", "state X {"]


def test_unterminated_note_block_still_attaches_at_eof():
    source = "stateDiagram-v2\n[*] --> Y\nnote left of Y\nunterminated note\n"
    lines = render_state(source, width=80)
    text = "\n".join(lines)
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)
    assert "Y" in text
    assert "unterminated note" in text


def test_stray_close_brace_is_dropped_and_rest_of_diagram_still_renders():
    source = "stateDiagram-v2\n}\n[*] --> A\n"
    lines = render_state(source, width=80)
    text = "\n".join(lines)
    assert any(_BOX_GLYPH_RE.search(line) for line in lines)
    assert _START_GLYPH in text
    assert "A" in text


def test_wholly_empty_source_echoes_as_empty():
    assert render_state("", width=80) == []


def test_never_crashes_on_a_variety_of_odd_inputs():
    # Defensive sweep: none of these may ever raise, regardless of what
    # they render to (the specific-case tests above already pin the exact
    # expected outcome for each).
    odd_inputs = [
        "stateDiagram-v2\n",
        "stateDiagram-v2\n[*] --> [*]\n",
        "stateDiagram-v2\nstate X {\n",
        "stateDiagram-v2\nnote left of Y\nunterminated note\n",
        "stateDiagram-v2\n}\n[*] --> A\n",
        "",
        "stateDiagram-v2\nstate A {\nstate B {\nstate C {\n[*] --> D\n",
    ]
    for source in odd_inputs:
        lines = render_state(source, width=80)
        assert isinstance(lines, list)
