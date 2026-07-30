"""Structural tests for the mermaid flowchart parser.

Every test asserts real fields on the returned :class:`FlowGraph` (node
ids/labels/shapes, edge endpoints/style/label/arrows, subgraph membership,
direction) — never just "parse didn't raise".
"""

from __future__ import annotations

import pytest

from termrender.renderers.mermaid_flow_model import (
    Direction,
    EdgeStyle,
    NodeShape,
)
from termrender.renderers.mermaid_flow_parser import FlowchartError, parse


def _node(g, node_id):
    return next(n for n in g.nodes if n.id == node_id)


def _edges(g, src, dst):
    return [e for e in g.edges if e.src == src and e.dst == dst]


# --------------------------------------------------------------------------
# Header / direction
# --------------------------------------------------------------------------


def test_graph_td_normalizes_to_tb():
    g = parse("graph TD\nA-->B\n")
    assert g.direction is Direction.TB


def test_flowchart_lr():
    g = parse("flowchart LR\nA-->B\n")
    assert g.direction is Direction.LR


def test_direction_defaults_to_tb_when_omitted():
    g = parse("graph\nA-->B\n")
    assert g.direction is Direction.TB


def test_rl_and_bt_directions():
    assert parse("graph RL\nA-->B").direction is Direction.RL
    assert parse("graph BT\nA-->B").direction is Direction.BT


def test_subgraph_direction_is_valid_and_recorded():
    g = parse("flowchart TB\nsubgraph S[Group]\ndirection LR\nA-->B\nend")
    assert g.direction is Direction.TB
    assert g.subgraphs[0].direction is Direction.LR
    assert [(edge.src, edge.dst) for edge in g.edges] == [("A", "B")]


def test_semicolon_separated_statements_on_header_line():
    g = parse("graph TD; A-->B; A-->C")
    assert {n.id for n in g.nodes} == {"A", "B", "C"}
    assert len(g.edges) == 2


def test_missing_header_raises():
    with pytest.raises(FlowchartError):
        parse("A-->B\nB-->C\n")


def test_missing_header_after_prelude_still_raises():
    with pytest.raises(FlowchartError):
        parse("%% just a comment\nnot a flowchart at all\n")


# --------------------------------------------------------------------------
# Node shapes
# --------------------------------------------------------------------------


def test_bare_node_id_equals_label():
    g = parse("graph TD\nA\n")
    n = _node(g, "A")
    assert n.label == "A"
    assert n.shape is NodeShape.RECT


SHAPE_CASES = [
    ("A[Rect Label]", NodeShape.RECT, "Rect Label"),
    ("A(Round Label)", NodeShape.ROUND, "Round Label"),
    ("A{Diamond Label}", NodeShape.DIAMOND, "Diamond Label"),
    ("A([Stadium Label])", NodeShape.STADIUM, "Stadium Label"),
    ("A[(DB Label)]", NodeShape.CYLINDER, "DB Label"),
    ("A((Circle Label))", NodeShape.CIRCLE, "Circle Label"),
    ("A{{Hex Label}}", NodeShape.HEXAGON, "Hex Label"),
    ("A[[Subroutine Label]]", NodeShape.SUBROUTINE, "Subroutine Label"),
    ("A[/Para Label/]", NodeShape.PARALLELOGRAM, "Para Label"),
]


@pytest.mark.parametrize("spec,shape,label", SHAPE_CASES)
def test_each_node_shape(spec, shape, label):
    g = parse(f"graph TD\n{spec}\n")
    n = _node(g, "A")
    assert n.shape is shape
    assert n.label == label


def test_id_vs_label_split():
    g = parse("graph TD\nid1[The Label]\n")
    n = _node(g, "id1")
    assert n.id == "id1"
    assert n.label == "The Label"


# --------------------------------------------------------------------------
# Node re-declaration merge policy
# --------------------------------------------------------------------------


def test_bare_reference_does_not_downgrade_shaped_node():
    g = parse("graph TD\nA[Real Label]\nA-->B\n")
    n = _node(g, "A")
    assert n.label == "Real Label"
    assert n.shape is NodeShape.RECT


def test_shaped_declaration_updates_bare_node_in_place():
    g = parse("graph TD\nA-->B\nA{Now Diamond}\n")
    n = _node(g, "A")
    assert n.label == "Now Diamond"
    assert n.shape is NodeShape.DIAMOND
    # Still unique by id, first-seen order preserved.
    assert [x.id for x in g.nodes] == ["A", "B"]


def test_later_shaped_declaration_wins():
    g = parse("graph TD\nA[First]\nA[Second]\n")
    n = _node(g, "A")
    assert n.label == "Second"


def test_nodes_unique_by_id_first_seen_order():
    g = parse("graph TD\nA-->B\nB-->C\nA-->C\n")
    assert [n.id for n in g.nodes] == ["A", "B", "C"]


# --------------------------------------------------------------------------
# Edge styles / arrows
# --------------------------------------------------------------------------


def test_solid_arrow():
    g = parse("graph TD\nA-->B\n")
    e = _edges(g, "A", "B")[0]
    assert e.style is EdgeStyle.SOLID
    assert e.dst_arrow is True
    assert e.src_arrow is False


def test_solid_line_no_arrow():
    g = parse("graph TD\nA---B\n")
    e = _edges(g, "A", "B")[0]
    assert e.style is EdgeStyle.SOLID
    assert e.dst_arrow is False
    assert e.src_arrow is False


def test_dotted_arrow():
    g = parse("graph TD\nA-.->B\n")
    e = _edges(g, "A", "B")[0]
    assert e.style is EdgeStyle.DOTTED
    assert e.dst_arrow is True


def test_thick_arrow():
    g = parse("graph TD\nA==>B\n")
    e = _edges(g, "A", "B")[0]
    assert e.style is EdgeStyle.THICK
    assert e.dst_arrow is True


def test_bidirectional_arrow():
    g = parse("graph TD\nA<-->B\n")
    e = _edges(g, "A", "B")[0]
    assert e.dst_arrow is True
    assert e.src_arrow is True


def test_pipe_label_form():
    g = parse("graph TD\nA-->|yes| B\n")
    e = _edges(g, "A", "B")[0]
    assert e.label == "yes"


def test_pipe_label_quoted_contains_literal_pipe():
    # mermaid.js allows a literal `|` inside a quoted edge label; the pipe
    # delimiter is closed by the quote, not the first inner `|`. Regression:
    # the plabel capture must honor `"..."` quoting instead of stopping at the
    # first `|`, otherwise the whole diagram raw-echoes.
    g = parse('graph TD\nA-->|"deployed | error"| B\n')
    e = _edges(g, "A", "B")[0]
    # The quotes delimit the label; mermaid.js does not display them.
    assert e.label == "deployed | error"


def test_node_label_quotes_stripped():
    g = parse('graph TD\nA["quoted label"]-->B\n')
    assert _node(g, "A").label == "quoted label"


def test_literal_newlines_inside_quoted_labels_remain_label_content():
    source = (
        'flowchart TB\n'
        'APP["applet server fn<br/>template\n src/server/connectors.ts"]\n'
        'ROUTES -.->|"execute → 200\n {ok:false,<br/>errorClass:connection-required}"| APP\n'
    )
    g = parse(source)
    assert _node(g, "APP").label == "applet server fn\ntemplate\n src/server/connectors.ts"
    assert _edges(g, "ROUTES", "APP")[0].label == (
        "execute → 200 {ok:false, errorClass:connection-required}"
    )


def test_semicolon_inside_quoted_edge_label_does_not_split_statement():
    g = parse('graph TD\nA-->|"first; second"|B\n')
    assert _edges(g, "A", "B")[0].label == "first; second"


def test_unmatched_quote_in_comment_does_not_join_following_statement():
    g = parse('graph TD\n%% someone said "hello\nA-->B\n')
    assert len(_edges(g, "A", "B")) == 1


def test_node_label_br_becomes_newline():
    # <br/> (any case, with or without the slash/spaces) is a hard line
    # break in a node label — stored as \n so wrap_text honors it.
    g = parse('graph TD\nA["CP Worker<br/>API_KEY"]-->B[x<BR>y<br />z]\n')
    assert _node(g, "A").label == "CP Worker\nAPI_KEY"
    assert _node(g, "B").label == "x\ny\nz"


def test_edge_label_br_flattens_to_space():
    # Edge labels render on a single line, so <br/> flattens to a space.
    g = parse('graph TD\nA-->|"connect<br/>(OAuth)"| B\n')
    assert _edges(g, "A", "B")[0].label == "connect (OAuth)"


def test_literal_backslash_n_is_a_line_break():
    # A literal backslash-n is the other way authors write a break; it must
    # behave exactly like <br/> rather than showing up verbatim in the box.
    g = parse(
        "graph TD\n"
        "A[Acquisition service\\nlive list]-->|matching executor\\n(no nav)|B\n"
        "subgraph s1[Top\\nhalf]\nA\nend\n"
    )
    assert _node(g, "A").label == "Acquisition service\nlive list"
    assert _edges(g, "A", "B")[0].label == "matching executor (no nav)"
    assert g.subgraphs[0].title == "Top half"


def test_subgraph_title_br_flattens_to_space():
    g = parse("graph TD\nsubgraph s1[Top<br/>half]\nA\nend\n")
    assert g.subgraphs[0].title == "Top half"


def test_inline_label_form():
    g = parse('graph TD\nA -- some text --> B\n')
    e = _edges(g, "A", "B")[0]
    assert e.label == "some text"
    assert e.style is EdgeStyle.SOLID
    assert e.dst_arrow is True


def test_inline_dotted_label_form():
    g = parse("graph TD\nA -. retry .-> B\n")
    e = _edges(g, "A", "B")[0]
    assert e.label == "retry"
    assert e.style is EdgeStyle.DOTTED


def test_compact_inline_dotted_label_form():
    g = parse("graph TD\nA -.hosted OAuth page.-> B\n")
    e = _edges(g, "A", "B")[0]
    assert e.label == "hosted OAuth page"
    assert e.style is EdgeStyle.DOTTED
    assert e.dst_arrow is True


def test_inline_thick_label_form():
    g = parse("graph TD\nA == fast === B\n")
    e = _edges(g, "A", "B")[0]
    assert e.label == "fast"
    assert e.style is EdgeStyle.THICK
    assert e.dst_arrow is False


def test_empty_pipe_label_stored_as_none():
    g = parse("graph TD\nA-->|| B\n")
    e = _edges(g, "A", "B")[0]
    assert e.label is None


def test_edge_with_no_label_has_none():
    g = parse("graph TD\nA-->B\n")
    e = _edges(g, "A", "B")[0]
    assert e.label is None


# --------------------------------------------------------------------------
# `&` fan-out
# --------------------------------------------------------------------------


def test_fanout_expands_to_cartesian_product():
    g = parse("graph TD\nA & B --> C & D\n")
    pairs = {(e.src, e.dst) for e in g.edges}
    assert pairs == {("A", "C"), ("A", "D"), ("B", "C"), ("B", "D")}
    assert len(g.edges) == 4


def test_fanout_edges_share_style_and_label():
    g = parse("graph TD\nA & B -->|go| C\n")
    assert all(e.label == "go" for e in g.edges)
    assert len(g.edges) == 2


def test_ampersand_inside_label_not_treated_as_fanout():
    g = parse("graph TD\nA[Foo & Bar] --> B\n")
    assert len(g.edges) == 1
    n = _node(g, "A")
    assert n.label == "Foo & Bar"


# --------------------------------------------------------------------------
# Chained edges (`A-->B-->C`)
# --------------------------------------------------------------------------


def test_two_link_chain():
    g = parse("graph TD\nA-->B-->C\n")
    assert [n.id for n in g.nodes] == ["A", "B", "C"]
    assert {(e.src, e.dst) for e in g.edges} == {("A", "B"), ("B", "C")}
    assert len(g.edges) == 2


def test_three_link_chain_with_labeled_back_edge():
    g = parse("graph TD\nA-->B-->C\nC-->|retry|A\n")
    assert [n.id for n in g.nodes] == ["A", "B", "C"]
    ab = _edges(g, "A", "B")[0]
    bc = _edges(g, "B", "C")[0]
    ca = _edges(g, "C", "A")[0]
    assert ab.label is None
    assert bc.label is None
    assert ca.label == "retry"
    assert all(e.style is EdgeStyle.SOLID and e.dst_arrow for e in (ab, bc, ca))


def test_chain_with_inline_label_on_one_link():
    g = parse("graph TD\nA-->B -- go --> C\n")
    ab = _edges(g, "A", "B")[0]
    bc = _edges(g, "B", "C")[0]
    assert ab.label is None
    assert bc.label == "go"


def test_chain_mixing_edge_styles_per_connector():
    g = parse("graph TD\nA-->B-.->C==>D\n")
    ab = _edges(g, "A", "B")[0]
    bc = _edges(g, "B", "C")[0]
    cd = _edges(g, "C", "D")[0]
    assert ab.style is EdgeStyle.SOLID
    assert bc.style is EdgeStyle.DOTTED
    assert cd.style is EdgeStyle.THICK
    assert [n.id for n in g.nodes] == ["A", "B", "C", "D"]


# --------------------------------------------------------------------------
# Connector-looking text inside bracketed labels
# --------------------------------------------------------------------------


def test_arrow_connector_inside_rect_label_not_mistaken_for_edge():
    g = parse("graph TD\nA[Go --> Fast] --> B\n")
    n = _node(g, "A")
    assert n.label == "Go --> Fast"
    assert [n.id for n in g.nodes] == ["A", "B"]
    assert len(g.edges) == 1
    assert _edges(g, "A", "B")[0].dst_arrow is True


def test_plain_line_connector_inside_rect_label_not_mistaken_for_edge():
    g = parse("graph TD\nA[one --- two] --> B\n")
    n = _node(g, "A")
    assert n.label == "one --- two"
    assert len(g.edges) == 1


def test_dotted_connector_inside_round_label_not_mistaken_for_edge():
    g = parse("graph TD\nA(Try -.-> Retry) --> B\n")
    n = _node(g, "A")
    assert n.label == "Try -.-> Retry"
    assert len(g.edges) == 1


def test_thick_connector_inside_diamond_label_not_mistaken_for_edge():
    g = parse("graph TD\nA{Fast ==> Track} --> B\n")
    n = _node(g, "A")
    assert n.label == "Fast ==> Track"
    assert len(g.edges) == 1


# --------------------------------------------------------------------------
# Semicolon inside labels
# --------------------------------------------------------------------------


def test_semicolon_inside_rect_label_does_not_split_statement():
    g = parse("graph TD\nA[Check; validate] --> B\n")
    n = _node(g, "A")
    assert n.label == "Check; validate"
    assert [n.id for n in g.nodes] == ["A", "B"]
    assert len(g.edges) == 1


# --------------------------------------------------------------------------
# Subgraphs
# --------------------------------------------------------------------------


def test_subgraph_membership():
    src = """graph TD
    subgraph s1
    A-->B
    end
    """
    g = parse(src)
    assert len(g.subgraphs) == 1
    sg = g.subgraphs[0]
    assert sg.id == "s1"
    assert sg.title == "s1"
    assert set(sg.node_ids) == {"A", "B"}


def test_subgraph_explicit_title():
    src = """graph TD
    subgraph s1[My Title]
    A-->B
    end
    """
    g = parse(src)
    sg = g.subgraphs[0]
    assert sg.id == "s1"
    assert sg.title == "My Title"


def test_nested_subgraphs():
    src = """graph TD
    subgraph outer
    A
    subgraph inner
    B
    end
    end
    """
    g = parse(src)
    assert len(g.subgraphs) == 1
    outer = g.subgraphs[0]
    assert outer.id == "outer"
    assert outer.node_ids == ["A"]
    assert len(outer.children) == 1
    inner = outer.children[0]
    assert inner.id == "inner"
    assert inner.node_ids == ["B"]


def test_unterminated_subgraph_raises():
    src = """graph TD
    subgraph s1
    A
    """
    with pytest.raises(FlowchartError):
        parse(src)


# --------------------------------------------------------------------------
# Ignored lines
# --------------------------------------------------------------------------


def test_class_classdef_style_click_linkstyle_leave_no_trace():
    src = """graph TD
    A-->B
    classDef important fill:#f00
    class A important
    style A fill:#fff
    click A "http://example.com"
    linkStyle 0 stroke:#f00
    accTitle Demo title
    accDescr Demo description
    accTitle: Demo title
    accDescr: Demo description
    """
    g = parse(src)
    assert [n.id for n in g.nodes] == ["A", "B"]
    assert len(g.edges) == 1


@pytest.mark.parametrize(
    "line",
    [
        "class",
        "class A",
        "classDef",
        "classDef important",
        "style",
        "style A",
        "click",
        "click A",
        "linkStyle",
        "linkStyle 0",
        "accTitle",
        "accDescr",
    ],
)
def test_incomplete_presentational_directives_raise(line):
    with pytest.raises(FlowchartError):
        parse(f"graph TD\nA-->B\n{line}\n")


def test_comment_lines_dropped():
    g = parse("graph TD\n%% a comment\nA-->B\n")
    assert [n.id for n in g.nodes] == ["A", "B"]
    assert len(g.edges) == 1


# --------------------------------------------------------------------------
# Malformed body raises
# --------------------------------------------------------------------------


def test_malformed_body_line_raises():
    with pytest.raises(FlowchartError):
        parse("graph TD\nA-->B\n@@@not valid mermaid at all###\n")


def test_stray_end_with_nothing_open_raises():
    with pytest.raises(FlowchartError):
        parse("graph TD\nA-->B\nend\n")


def test_empty_body_returns_no_nodes():
    g = parse("graph TD\n")
    assert g.nodes == []
    assert g.edges == []
    assert g.subgraphs == []
