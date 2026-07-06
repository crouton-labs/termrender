"""Layout + rasterization engine for the native mermaid flowchart renderer.

Public entry point: :func:`layout_flowgraph` — turns a parsed
:class:`~termrender.renderers.mermaid_flow_model.FlowGraph` into a char grid
(``list[str]``). This module owns four concerns, marked by section comments
below: the grandalf adapter (node coordinates), the :class:`Canvas` grid
(shared mutable rasterization surface), box rasterization, and edge routing.
See ``flow-design.md`` (this renderer's design-of-record, referenced from the
orchestrator context dir) for the full architecture; this docstring covers
only what a reader of this file needs.

Layout model
------------
Node positions come from ``grandalf`` (pure-Python Sugiyama layered layout,
v0.8) — this module does no layering or crossing-minimization itself. One
:class:`grandalf.graphs.Vertex` is built per :class:`FlowNode`, sized via
``VertexViewer(w, h)`` in *cell* units so grandalf's coordinates come out
directly in char space; one :class:`grandalf.graphs.Edge` per
:class:`FlowEdge` (self-loops excluded — they add no ranking information).
Each connected component (``Graph.C``) is laid out independently, then
stacked left-to-right in the direction-neutral "native" coordinate frame
(grandalf always lays out top-to-bottom internally). grandalf's per-vertex
floats are snapped to a clean non-overlapping integer cell grid: nodes are
grouped into rank *bands* (rows for TB, later transposed for LR/RL), and
within a band sorted by grandalf's provisional column and nudged apart to
guarantee a minimum gap — this preserves grandalf's crossing-minimized
*ordering* without trusting its raw floats for exact spacing.

Rank-flow direction (``TB``/``BT``/``LR``/``RL``) is never passed to
grandalf (it has no such parameter) — it is a post-hoc coordinate transform
applied to the final integer (col, band) placement: identity for TB, a
vertical mirror for BT, an axis transpose for LR, and transpose + horizontal
mirror for RL. For LR/RL the adapter feeds grandalf *swapped* box dimensions
(``w=box_h, h=box_w``) so its in-layer spacing math reserves the right
amount of room along each post-transpose axis.

**Cycle handling requires no pre-processing.** grandalf's ``init_all()``
detects strongly-connected components and marks back-edges ``feedback=True``
internally for ranking purposes only; it never mutates the edge objects we
hand it, and we always draw using the model's original ``src -> dst``
direction. A cyclic :class:`FlowGraph` (e.g. ``A->B->C->A``) lays out and
renders without any manual cycle-breaking — confirmed empirically against
grandalf 0.8 (see the design doc's "grandalf adapter recipe" section).

Grammar / scope this phase
---------------------------
This module renders every node as a bordered **rectangle** regardless of its
declared :class:`NodeShape` — distinct shape borders (diamond, round,
stadium, circle, ...) are a later phase. Edges are drawn as a **placeholder**
straight line or simple two-segment L path between each pair's facing border
midpoints — no arrowheads, no back-edge side-lane routing, no edge labels;
the full orthogonal router (arrowheads, labels, back-edge lanes, self-loops)
is a later phase built on top of the :class:`Canvas`/:class:`BoxRect`
exported here. Subgraph frames (:meth:`Canvas.draw_frame`) are implemented
as part of the shared grid contract but not yet invoked by
:func:`layout_flowgraph`.

Known degradations (by design, not bugs)
-----------------------------------------
- Node labels wrap via :func:`termrender.style.wrap_text`, which measures
  with ``len()`` internally (a pre-existing termrender limitation, see the
  root ``CLAUDE.md``) — CJK/wide-glyph labels may wrap at the wrong point.
  Box *dimensions*, however, are always computed from :func:`visual_len` of
  the wrapped lines, so the box itself is never too narrow for its content.
- Dense graphs may show edge-line crossings and label overlap once the real
  router lands; this phase draws no labels at all.
- An edge referencing a node id absent from the graph (a malformed/hand-built
  :class:`FlowGraph`) is silently skipped rather than raised — the parser is
  expected to guarantee valid endpoints, but this module never crashes on a
  dangling reference.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from grandalf.graphs import Edge, Graph, Vertex
from grandalf.layouts import SugiyamaLayout, VertexViewer

from termrender.renderers.mermaid_flow_model import (
    Direction,
    EdgeStyle,
    FlowEdge,
    FlowGraph,
    FlowNode,
    NodeShape,
)
from termrender.style import visual_center, visual_len, wrap_text

__all__ = ["layout_flowgraph", "Canvas", "BoxRect"]


# --------------------------------------------------------------------------
# --- canvas ---
# --------------------------------------------------------------------------

# Direction bitmask for line-glyph junction resolution (see Canvas._write_line_cell).
_UP, _DOWN, _LEFT, _RIGHT = 1, 2, 4, 8

_JUNCTIONS: dict[int, str] = {
    0: " ",
    _UP: "\u2502",
    _DOWN: "\u2502",
    _UP | _DOWN: "\u2502",
    _LEFT: "\u2500",
    _RIGHT: "\u2500",
    _LEFT | _RIGHT: "\u2500",
    _DOWN | _RIGHT: "\u250c",
    _DOWN | _LEFT: "\u2510",
    _UP | _RIGHT: "\u2514",
    _UP | _LEFT: "\u2518",
    _UP | _DOWN | _RIGHT: "\u251c",
    _UP | _DOWN | _LEFT: "\u2524",
    _DOWN | _LEFT | _RIGHT: "\u252c",
    _UP | _LEFT | _RIGHT: "\u2534",
    _UP | _DOWN | _LEFT | _RIGHT: "\u253c",
}

_STYLE_V = {
    EdgeStyle.SOLID: "\u2502",
    EdgeStyle.THICK: "\u2503",
    EdgeStyle.DOTTED: "\u254e",
}
_STYLE_H = {
    EdgeStyle.SOLID: "\u2500",
    EdgeStyle.THICK: "\u2501",
    EdgeStyle.DOTTED: "\u254c",
}
_STRAIGHT_BITS = {
    0,
    _UP,
    _DOWN,
    _UP | _DOWN,
    _LEFT,
    _RIGHT,
    _LEFT | _RIGHT,
}


class Canvas:
    """Mutable 2D char grid shared by the rasterizer and the edge router.

    Two parallel planes: ``grid`` (the visible characters) and a boolean
    "reserved" plane marking box interiors + borders, which the router must
    never overwrite via :meth:`draw_segment` (but :meth:`draw_glyph` may,
    e.g. an arrowhead landing on a border cell). Line-drawing state (which
    directions a cell connects, and which :class:`EdgeStyle` drew it) is
    tracked internally so intersecting segments compose into the correct
    box-drawing junction glyph rather than clobbering each other.
    """

    def __init__(self, width: int, height: int) -> None:
        self._width = max(width, 0)
        self._height = max(height, 0)
        self.grid: list[list[str]] = [[" "] * self._width for _ in range(self._height)]
        self.reserved: list[list[bool]] = [
            [False] * self._width for _ in range(self._height)
        ]
        self._bits: dict[tuple[int, int], int] = {}
        self._style: dict[tuple[int, int], EdgeStyle | None] = {}

    def ensure(self, x: int, y: int) -> None:
        if x < 0 or y < 0:
            return
        if y >= len(self.grid):
            for _ in range(y + 1 - len(self.grid)):
                self.grid.append([" "] * self._width)
                self.reserved.append([False] * self._width)
            self._height = len(self.grid)
        if x >= self._width:
            new_width = x + 1
            for row in self.grid:
                row.extend([" "] * (new_width - len(row)))
            for row in self.reserved:
                row.extend([False] * (new_width - len(row)))
            self._width = new_width

    def set_char(self, x: int, y: int, ch: str, *, reserve: bool = False) -> None:
        if x < 0 or y < 0:
            return
        self.ensure(x, y)
        self.grid[y][x] = ch
        if reserve:
            self.reserved[y][x] = True

    def get_char(self, x: int, y: int) -> str:
        if y < 0 or x < 0 or y >= len(self.grid) or x >= len(self.grid[y]):
            return " "
        return self.grid[y][x]

    def is_reserved(self, x: int, y: int) -> bool:
        if y < 0 or x < 0 or y >= len(self.reserved) or x >= len(self.reserved[y]):
            return False
        return self.reserved[y][x]

    def draw_box(self, rect: "BoxRect", shape: NodeShape, label: str) -> None:
        """Draw a bordered box + centered wrapped label; reserve every cell.

        ``shape`` is accepted for interface stability with later phases —
        this phase draws every shape as a plain rectangle (distinct shape
        borders are a later phase's responsibility).
        """
        del shape
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        if w <= 0 or h <= 0:
            return

        right, bottom = x + w - 1, y + h - 1
        self.set_char(x, y, "\u250c", reserve=True)
        self.set_char(right, y, "\u2510", reserve=True)
        self.set_char(x, bottom, "\u2514", reserve=True)
        self.set_char(right, bottom, "\u2518", reserve=True)
        for cx in range(x + 1, right):
            self.set_char(cx, y, "\u2500", reserve=True)
            self.set_char(cx, bottom, "\u2500", reserve=True)
        for cy in range(y + 1, bottom):
            self.set_char(x, cy, "\u2502", reserve=True)
            self.set_char(right, cy, "\u2502", reserve=True)
            for cx in range(x + 1, right):
                self.set_char(cx, cy, " ", reserve=True)

        inner_w, inner_h = w - 2, h - 2
        if inner_w <= 0 or inner_h <= 0:
            return
        lines = wrap_text(label or "", inner_w)
        top_line = y + 1 + max(0, (inner_h - len(lines)) // 2)
        for i, line in enumerate(lines[:inner_h]):
            centered = visual_center(line, inner_w)
            for j, ch in enumerate(centered):
                self.set_char(x + 1 + j, top_line + i, ch, reserve=True)

    def draw_frame(self, rect: "BoxRect", title: str) -> None:
        """Draw a subgraph enclosure: light border, left-anchored title.

        Frame cells are NOT reserved — nodes and edges live inside a
        subgraph frame; only the four border runs are drawn.
        """
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        if w < 2 or h < 2:
            return
        inner = w - 2
        prefix = f"\u2500 {title} " if title else "\u2500 "
        fill = max(inner - visual_len(prefix), 0)
        top = "\u250c" + prefix + "\u2500" * fill + "\u2510"
        bottom = "\u2514" + "\u2500" * inner + "\u2518"
        for i, ch in enumerate(top[:w]):
            self.set_char(x + i, y, ch)
        for i, ch in enumerate(bottom[:w]):
            self.set_char(x + i, y + h - 1, ch)
        for cy in range(y + 1, y + h - 1):
            self.set_char(x, cy, "\u2502")
            self.set_char(x + w - 1, cy, "\u2502")

    def _write_line_cell(self, x: int, y: int, bits: int, style: EdgeStyle) -> None:
        if self.is_reserved(x, y):
            return
        self.ensure(x, y)
        key = (x, y)
        existing_bits = self._bits.get(key, 0)
        combined = existing_bits | bits
        if existing_bits == 0:
            new_style: EdgeStyle | None = style
        else:
            prev_style = self._style.get(key)
            new_style = (
                prev_style
                if prev_style == style and combined in _STRAIGHT_BITS
                else None
            )
        self._bits[key] = combined
        self._style[key] = new_style
        if new_style is not None and combined in _STRAIGHT_BITS:
            if combined & (_LEFT | _RIGHT) and not combined & (_UP | _DOWN):
                glyph = _STYLE_H[new_style]
            elif combined & (_UP | _DOWN):
                glyph = _STYLE_V[new_style]
            else:
                glyph = _JUNCTIONS[0]
        else:
            glyph = _JUNCTIONS.get(combined, "\u253c")
        self.grid[y][x] = glyph

    def draw_segment(
        self, x0: int, y0: int, x1: int, y1: int, style: EdgeStyle = EdgeStyle.SOLID
    ) -> None:
        """Draw one straight H or V run (``x0 == x1`` or ``y0 == y1``).

        Not axis-aligned input is a caller-contract violation and is
        silently ignored (this module's only caller always supplies
        axis-aligned runs) rather than raised.
        """
        if x0 == x1:
            ylo, yhi = (y0, y1) if y0 <= y1 else (y1, y0)
            for y in range(ylo, yhi + 1):
                bits = 0
                if y > ylo:
                    bits |= _UP
                if y < yhi:
                    bits |= _DOWN
                self._write_line_cell(x0, y, bits, style)
        elif y0 == y1:
            xlo, xhi = (x0, x1) if x0 <= x1 else (x1, x0)
            for x in range(xlo, xhi + 1):
                bits = 0
                if x > xlo:
                    bits |= _LEFT
                if x < xhi:
                    bits |= _RIGHT
                self._write_line_cell(x, y0, bits, style)
        # else: diagonal request — not axis-aligned, ignored (total function).

    def draw_glyph(self, x: int, y: int, ch: str) -> None:
        """Unconditional single-glyph write (arrowheads, corners, labels).

        Overwrites unconditionally — does not participate in the line-join
        bitmask system, and does not skip reserved cells (an arrowhead is
        meant to visibly land on a box border).
        """
        if x < 0 or y < 0:
            return
        self.ensure(x, y)
        self.grid[y][x] = ch

    def to_lines(self) -> list[str]:
        lines = ["".join(row).rstrip() for row in self.grid]
        while lines and lines[-1] == "":
            lines.pop()
        return lines


@dataclass
class BoxRect:
    """A placed node's rectangle: top-left cell + extents, plus border
    anchor points used by the edge router. Engine-internal (not part of the
    parser/model contract)."""

    x: int
    y: int
    w: int
    h: int

    @property
    def top_mid(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y)

    @property
    def bottom_mid(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h - 1)

    @property
    def left_mid(self) -> tuple[int, int]:
        return (self.x, self.y + self.h // 2)

    @property
    def right_mid(self) -> tuple[int, int]:
        return (self.x + self.w - 1, self.y + self.h // 2)

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)


# --------------------------------------------------------------------------
# --- rasterizer sizing ---
# --------------------------------------------------------------------------

_MAX_LABEL_CONTENT_WIDTH = 20
_MIN_BOX_W = 5
_MIN_BOX_H = 3


def _box_dims(label: str) -> tuple[int, int]:
    """Content-driven box extents (cells), used both to size the grandalf
    ``VertexViewer`` and later to actually draw the box — sizing always goes
    through :func:`visual_len` so wide glyphs are never under-reserved (see
    the design doc's CJK open risk)."""
    lines = wrap_text(label or "", _MAX_LABEL_CONTENT_WIDTH) or [""]
    content_w = max((visual_len(line) for line in lines), default=0)
    w = max(content_w + 4, _MIN_BOX_W)
    h = max(len(lines) + 2, _MIN_BOX_H)
    return w, h


# --------------------------------------------------------------------------
# --- adapter ---
# --------------------------------------------------------------------------

_GAP_X = 3          # minimum border-to-border gap between boxes in one rank/band
_ROW_GAP = 2         # minimum gap between rank bands
_COMPONENT_GUTTER = 4  # gap between independently-laid-out components


def _native_extents(
    direction: Direction, box_w: int, box_h: int
) -> tuple[int, int]:
    """Dimensions fed to grandalf's VertexViewer, and used for our own
    band/column snap math. TB/BT lay out in their real orientation; LR/RL
    swap w/h before layout so grandalf's in-layer spacing reserves the right
    amount of room along each post-transpose axis (see module docstring)."""
    if direction in (Direction.LR, Direction.RL):
        return box_h, box_w
    return box_w, box_h


def _place_nodes(
    nodes: list[FlowNode], edges: list[FlowEdge], direction: Direction
) -> dict[str, BoxRect]:
    dims = {n.id: _box_dims(n.label) for n in nodes}
    native = {
        n.id: _native_extents(direction, *dims[n.id]) for n in nodes
    }

    vertices: dict[str, Vertex] = {}
    for n in nodes:
        v = Vertex(n.id)
        nw, nh = native[n.id]
        v.view = VertexViewer(w=nw, h=nh)
        vertices[n.id] = v

    grandalf_edges = [
        Edge(vertices[e.src], vertices[e.dst])
        for e in edges
        if e.src != e.dst and e.src in vertices and e.dst in vertices
    ]

    graph = Graph(list(vertices.values()), grandalf_edges)

    # node_id -> (col, band_top) in the shared native (pre-transform) frame.
    placements: dict[str, tuple[int, int]] = {}
    running_x_offset = 0

    for component in graph.C:
        comp_vertices = list(component.sV)
        if not comp_vertices:
            continue
        sug = SugiyamaLayout(component)
        sug.xspace = _GAP_X
        sug.yspace = _ROW_GAP
        sug.init_all()
        sug.draw()

        ranks: dict[int, list[Vertex]] = defaultdict(list)
        for v in comp_vertices:
            ranks[sug.grx[v].rank].append(v)

        band_top_for_rank: dict[int, int] = {}
        cursor = 0
        for r in sorted(ranks):
            band_top_for_rank[r] = cursor
            max_h = max(native[v.data][1] for v in ranks[r])
            cursor += max_h + _ROW_GAP

        min_x = min(v.view.xy[0] for v in comp_vertices)
        provisional = {v: round(v.view.xy[0] - min_x) for v in comp_vertices}

        actual_col: dict[Vertex, int] = {}
        for r in sorted(ranks):
            row_nodes = sorted(ranks[r], key=lambda v: provisional[v])
            prev_col: int | None = None
            prev_w = 0
            for v in row_nodes:
                nw = native[v.data][0]
                if prev_col is None:
                    col = provisional[v]
                else:
                    min_col = prev_col + prev_w // 2 + nw // 2 + _GAP_X
                    col = max(provisional[v], min_col)
                actual_col[v] = col
                prev_col, prev_w = col, nw

        min_col = min(actual_col.values())
        if min_col < 0:
            for v in actual_col:
                actual_col[v] -= min_col

        comp_width = max(
            actual_col[v] + native[v.data][0] // 2 for v in comp_vertices
        )
        offset = running_x_offset
        for v in comp_vertices:
            col = actual_col[v] + offset
            band_top = band_top_for_rank[sug.grx[v].rank]
            placements[v.data] = (col, band_top)
        running_x_offset += comp_width + _COMPONENT_GUTTER

    if not placements:
        return {}

    band_axis_total = max(
        band_top + native[node_id][1] for node_id, (_, band_top) in placements.items()
    )

    rects: dict[str, BoxRect] = {}
    for n in nodes:
        if n.id not in placements:
            continue
        col, band_top = placements[n.id]
        native_w, native_h = native[n.id]
        box_w, box_h = dims[n.id]
        center = col - native_w // 2
        if direction is Direction.TB:
            x, y = center, band_top
        elif direction is Direction.BT:
            x, y = center, band_axis_total - (band_top + native_h)
        elif direction is Direction.LR:
            x, y = band_top, center
        else:  # Direction.RL
            x, y = band_axis_total - (band_top + native_h), center
        rects[n.id] = BoxRect(x=x, y=y, w=box_w, h=box_h)

    min_x = min(r.x for r in rects.values())
    min_y = min(r.y for r in rects.values())
    shift_x = -min_x if min_x < 0 else 0
    shift_y = -min_y if min_y < 0 else 0
    if shift_x or shift_y:
        for node_id, r in rects.items():
            rects[node_id] = BoxRect(x=r.x + shift_x, y=r.y + shift_y, w=r.w, h=r.h)

    return rects


# --------------------------------------------------------------------------
# --- router (placeholder — full orthogonal router is a later phase) ---
# --------------------------------------------------------------------------


def _facing_anchor(this: BoxRect, other: BoxRect) -> tuple[int, int]:
    """Pick the border midpoint of ``this`` box facing toward ``other``."""
    tcx, tcy = this.center
    ocx, ocy = other.center
    dx, dy = ocx - tcx, ocy - tcy
    if abs(dy) >= abs(dx):
        return this.bottom_mid if dy >= 0 else this.top_mid
    return this.right_mid if dx >= 0 else this.left_mid


def _draw_edge_stub(canvas: Canvas, rects: dict[str, BoxRect], edge: FlowEdge) -> None:
    """Draw a placeholder straight/L-shaped line between two placed boxes.

    Self-loops and edges referencing an unplaced node id are silently
    skipped (self-loops are excluded from the grandalf graph — see module
    docstring — and are a later phase's job to draw; a dangling reference
    is a defensive no-op, never a crash).
    """
    if edge.src == edge.dst:
        return
    src_rect = rects.get(edge.src)
    dst_rect = rects.get(edge.dst)
    if src_rect is None or dst_rect is None:
        return
    x0, y0 = _facing_anchor(src_rect, dst_rect)
    x1, y1 = _facing_anchor(dst_rect, src_rect)
    if x0 == x1 or y0 == y1:
        canvas.draw_segment(x0, y0, x1, y1, edge.style)
    else:
        canvas.draw_segment(x0, y0, x0, y1, edge.style)
        canvas.draw_segment(x0, y1, x1, y1, edge.style)


# --------------------------------------------------------------------------
# --- public entry point ---
# --------------------------------------------------------------------------


def layout_flowgraph(g: FlowGraph, width: int) -> list[str]:
    """Lay out and rasterize a parsed flowchart to char-grid lines.

    Total function: never raises for well-typed input. An empty graph (no
    nodes) returns ``[]`` — the orchestrator (a later phase's
    ``render_flowchart``) treats that as "nothing to draw" and degrades to
    a raw echo.

    Args:
        g: Parsed flowchart.
        width: Advisory terminal width — unused. Like the other native
            renderers in this package, layout sizes to content and may
            overflow; wrapping happens at the node-label level, not by
            constraining the overall canvas.

    Returns:
        Rendered lines: monochrome unicode box-drawing, no ANSI.
    """
    del width
    if not g.nodes:
        return []
    try:
        rects = _place_nodes(g.nodes, g.edges, g.direction)
        if not rects:
            return []
        max_x = max(r.x + r.w for r in rects.values())
        max_y = max(r.y + r.h for r in rects.values())
        canvas = Canvas(max_x, max_y)
        for n in g.nodes:
            rect = rects.get(n.id)
            if rect is not None:
                canvas.draw_box(rect, n.shape, n.label)
        for e in g.edges:
            _draw_edge_stub(canvas, rects, e)
        return canvas.to_lines()
    except Exception:
        return []
