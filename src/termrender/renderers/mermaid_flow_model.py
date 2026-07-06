"""Data model for the native mermaid flowchart/graph renderer.

Pure dataclasses + enums, zero logic — the contract between the parser
(``mermaid_flow_parser.py``, source → :class:`FlowGraph`) and the layout
engine (``mermaid_flow_layout.py``, :class:`FlowGraph` → char grid). Neither
side imports the other; both import this module. Nothing here has behavior.

Model shape
-----------
A :class:`FlowGraph` carries a :class:`Direction`, a declaration-ordered
list of unique :class:`FlowNode` (id is the graph key, label is the drawn
text), a declaration-ordered list of :class:`FlowEdge` with ``&`` fan-out
already expanded to individual edges, and the top-level :class:`Subgraph`
blocks (nesting via ``Subgraph.children``). Arrowheads are two per-endpoint
booleans (``dst_arrow``/``src_arrow``) independent of the line
:class:`EdgeStyle`. Ignored source directives (class/classDef/style/click/
linkStyle) leave no trace in the model — the parser drops them.

See ``flow-design.md`` (this node's orchestrator context dir) for the full
architecture and the decisions baked into these shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "Direction",
    "NodeShape",
    "EdgeStyle",
    "FlowNode",
    "FlowEdge",
    "Subgraph",
    "FlowGraph",
]


class Direction(Enum):
    """Rank-flow direction. ``TD`` is a mermaid alias for ``TB`` and is
    normalized to ``TB`` by the parser (never stored as a separate member)."""

    TB = "TB"  # top → bottom
    LR = "LR"  # left → right
    RL = "RL"  # right → left
    BT = "BT"  # bottom → top


class NodeShape(Enum):
    """Declared node shape. The engine renders ``DIAMOND``, ``ROUND``/
    ``STADIUM`` (rounded corners) and ``CIRCLE`` distinctly where cheap; every
    other shape falls back to a rectangle border. Only the shape class + label
    text are load-bearing."""

    RECT = "rect"                    # [text]
    ROUND = "round"                  # (text)
    STADIUM = "stadium"              # ([text])
    SUBROUTINE = "subroutine"        # [[text]]
    CYLINDER = "cylinder"            # [(text)]
    CIRCLE = "circle"                # ((text))
    DIAMOND = "diamond"              # {text}
    HEXAGON = "hexagon"              # {{text}}
    PARALLELOGRAM = "parallelogram"  # [/text/]


class EdgeStyle(Enum):
    """Edge line style. Arrowheads are orthogonal to style (see
    :class:`FlowEdge`)."""

    SOLID = "solid"    # --- / -->
    THICK = "thick"    # === / ==>
    DOTTED = "dotted"  # -.- / -.->


@dataclass
class FlowNode:
    """A graph node. ``id`` is the graph key (dedup + edge endpoints);
    ``label`` is the drawn text. Bare ``A`` yields ``id == label == "A"``.
    Re-declaring an id keeps the first-seen node; a later declaration that
    carries a shape/label updates it in place (parser policy)."""

    id: str
    label: str
    shape: NodeShape = NodeShape.RECT


@dataclass
class FlowEdge:
    """A directed edge between node ids. ``dst_arrow``/``src_arrow`` are the
    drawn arrowheads: ``-->`` → dst_arrow=True, src_arrow=False; ``---`` → both
    False (plain line); ``<-->`` → both True. ``label`` is the optional edge
    label (``|text|`` or the ``-- text -->`` inline form); ``None`` when absent
    (empty-string labels are stored as ``None``)."""

    src: str
    dst: str
    style: EdgeStyle = EdgeStyle.SOLID
    label: str | None = None
    dst_arrow: bool = True
    src_arrow: bool = False


@dataclass
class Subgraph:
    """A ``subgraph id [title] ... end`` block. ``node_ids`` are the ids
    declared directly inside this block (NOT those inside nested children).
    ``children`` are nested subgraphs. ``title`` is the display title (defaults
    to id when the block has no explicit title)."""

    id: str
    title: str
    node_ids: list[str] = field(default_factory=list)
    children: list["Subgraph"] = field(default_factory=list)


@dataclass
class FlowGraph:
    """Parsed flowchart. ``nodes`` is in first-seen declaration order, unique
    by id. ``edges`` is in declaration order, with ``&`` fan-out already
    expanded to individual edges. ``subgraphs`` are the top-level blocks
    (nesting via ``Subgraph.children``). Ignored lines (class/classDef/style/
    click/linkStyle) leave no trace."""

    direction: Direction
    nodes: list[FlowNode] = field(default_factory=list)
    edges: list[FlowEdge] = field(default_factory=list)
    subgraphs: list[Subgraph] = field(default_factory=list)
