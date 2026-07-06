"""Executable contract test for the flowchart data model.

Constructs every dataclass and enum so the parser and layout children can
build against a proven-importable, proven-instantiable model.
"""

from __future__ import annotations

from termrender.renderers.mermaid_flow_model import (
    Direction,
    EdgeStyle,
    FlowEdge,
    FlowGraph,
    FlowNode,
    NodeShape,
    Subgraph,
)


def test_direction_members():
    assert {d.value for d in Direction} == {"TB", "LR", "RL", "BT"}


def test_node_shape_members():
    # All nine declared shape classes are present.
    assert {s.value for s in NodeShape} == {
        "rect",
        "round",
        "stadium",
        "subroutine",
        "cylinder",
        "circle",
        "diamond",
        "hexagon",
        "parallelogram",
    }


def test_edge_style_members():
    assert {e.value for e in EdgeStyle} == {"solid", "thick", "dotted"}


def test_flow_node_defaults():
    n = FlowNode(id="A", label="Alpha")
    assert n.id == "A"
    assert n.label == "Alpha"
    assert n.shape is NodeShape.RECT

    n2 = FlowNode(id="B", label="B", shape=NodeShape.DIAMOND)
    assert n2.shape is NodeShape.DIAMOND


def test_flow_edge_defaults():
    e = FlowEdge(src="A", dst="B")
    assert e.src == "A"
    assert e.dst == "B"
    assert e.style is EdgeStyle.SOLID
    assert e.label is None
    assert e.dst_arrow is True
    assert e.src_arrow is False


def test_flow_edge_full():
    e = FlowEdge(
        src="C",
        dst="A",
        style=EdgeStyle.DOTTED,
        label="retry",
        dst_arrow=True,
        src_arrow=True,
    )
    assert e.style is EdgeStyle.DOTTED
    assert e.label == "retry"
    assert e.dst_arrow and e.src_arrow


def test_subgraph_nesting():
    inner = Subgraph(id="inner", title="Inner", node_ids=["X"])
    outer = Subgraph(
        id="outer",
        title="Outer",
        node_ids=["A", "B"],
        children=[inner],
    )
    assert outer.node_ids == ["A", "B"]
    assert outer.children[0] is inner
    assert inner.node_ids == ["X"]

    # Defaults: empty lists, not shared mutable state.
    a = Subgraph(id="a", title="a")
    b = Subgraph(id="b", title="b")
    a.node_ids.append("z")
    assert b.node_ids == []


def test_flow_graph_construction():
    g = FlowGraph(
        direction=Direction.LR,
        nodes=[FlowNode(id="A", label="A"), FlowNode(id="B", label="B")],
        edges=[FlowEdge(src="A", dst="B")],
        subgraphs=[Subgraph(id="s", title="S", node_ids=["A"])],
    )
    assert g.direction is Direction.LR
    assert [n.id for n in g.nodes] == ["A", "B"]
    assert g.edges[0].dst == "B"
    assert g.subgraphs[0].node_ids == ["A"]


def test_flow_graph_defaults():
    g = FlowGraph(direction=Direction.TB)
    assert g.nodes == []
    assert g.edges == []
    assert g.subgraphs == []
