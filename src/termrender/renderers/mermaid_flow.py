"""Public entry point for the native mermaid flowchart/graph renderer.

Standalone module: exposes a single pure function, :func:`render_flowchart`.
Not yet wired into ``mermaid.py``'s dispatcher (a later, orchestrator-owned
phase) — nothing in this package imports it. This module is a thin
orchestrator over the parser and layout engine; it owns none of the grammar
or layout logic itself, only header sniffing and the degradation contract.

Layout model
------------
``render_flowchart`` is ``parse -> layout_flowgraph -> lines``, wrapped in a
degradation guard (see *Degradation contract* below). :func:`~termrender.
renderers.mermaid_flow_parser.parse` turns mermaid source into a
:class:`~termrender.renderers.mermaid_flow_model.FlowGraph`;
:func:`~termrender.renderers.mermaid_flow_layout.layout_flowgraph` lays it
out with ``grandalf`` (pure-Python Sugiyama) and rasterizes it — bordered
rectangle nodes, an orthogonal edge router (L/Z paths for forward edges,
growing side lanes for back-edges/cycles, arrowheads, edge labels,
self-loops) — onto a char grid. See ``mermaid_flow_parser.py`` and
``mermaid_flow_layout.py``'s module docstrings for the full grammar and
routing model; this module covers only the public contract.

Grammar supported
------------------
Header: ``graph``/``flowchart`` + direction (``TD``/``TB``/``LR``/``RL``/
``BT``). Node shapes: ``[rect]``, ``(round)``, ``([stadium])``,
``[(cylinder)]``, ``((circle))``, ``{diamond}``, ``{{hexagon}}``,
``[[subroutine]]``, ``[/parallelogram/]`` — each renders with a distinct
shape-specific border (diamond/parallelogram slant tapers, round/stadium/
circle rounded corners, a cylinder's rounded cap over a square base, a
hexagon's cut corners, a subroutine's double-bar sides); only a shape whose
box is too small for its own drawer falls back to the plain rectangle
border. Edges: ``-->``, ``---``, ``-.->``, ``==>`` (and bidirectional
forms), with ``|label|`` and inline ``A -- text --> B`` labels, and ``&``
fan-out. ``subgraph ... end`` blocks (including nested subgraphs) render as
enclosing frames with a left-anchored title when their members place
contiguously enough for a clean rect; otherwise a block flattens (no frame,
members still placed and drawn) rather than draw a frame that would
visually claim a non-member node. ``class``/``classDef``/``style``/
``click``/``linkStyle`` lines are ignored.

Known degradations (by design, not bugs)
-----------------------------------------
- A subgraph whose members aren't placed contiguously enough for a clean
  enclosing rect flattens (drops its frame and title) rather than draw a
  frame that visually claims a non-member node.
- See ``mermaid_flow_layout.py``'s module docstring for the edge-routing
  degradations (dense-graph crossings, label-lane overlap, CJK wrapping,
  minimum-box-size self-loop cosmetics).
- ``width`` is advisory only: like the other native renderers in this
  package, this renderer sizes to content and may overflow a narrow
  terminal rather than truncate the diagram.
"""

from __future__ import annotations

from termrender.renderers.mermaid_flow_layout import layout_flowgraph
from termrender.renderers.mermaid_flow_parser import FlowchartError, parse

__all__ = ["render_flowchart"]


def render_flowchart(source: str, width: int) -> list[str]:
    """Render a mermaid ``graph``/``flowchart`` source to unicode lines.

    Pure and total: never raises. Degrades to a raw echo of ``source``
    (each line ``\\n``-split and ``.rstrip()``-ed, containing no
    box-drawing glyphs) exactly when:

    1. The source isn't a flowchart at all (no ``graph``/``flowchart``
       header on its first non-blank, post-prelude line) — :func:`parse`
       raises :class:`FlowchartError`.
    2. Parsing succeeds but yields zero nodes (an empty or comment-only
       diagram body) — nothing to draw.
    3. Any unexpected exception escapes :func:`layout_flowgraph` — a
       defensive catch-all; this should never happen for well-typed input,
       but the guarantee is "never crash, degrade" regardless.

    Otherwise, returns the rendered diagram: guaranteed to contain unicode
    box-drawing glyphs (every node is a bordered box), never ANSI escapes.
    The distinction matters downstream — code that detects render success
    by the *presence* of box-drawing glyphs relies on the echo path never
    emitting any.

    Args:
        source: The mermaid fence body (with or without the surrounding
            fence markers — only the text between them).
        width: Advisory terminal width. See the module docstring's
            "Known degradations" for why this is advisory rather than a
            hard wrap.

    Returns:
        Rendered lines on success, or a raw-echo of ``source`` on any of
        the three degradation conditions above.
    """
    try:
        graph = parse(source)
    except FlowchartError:
        return _raw_echo(source)

    if not graph.nodes:
        return _raw_echo(source)

    try:
        lines = layout_flowgraph(graph, width)
    except Exception:
        return _raw_echo(source)

    if not lines:
        return _raw_echo(source)

    return lines


def _raw_echo(source: str) -> list[str]:
    return [line.rstrip() for line in source.splitlines()]
