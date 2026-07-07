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

Shapes and subgraph frames
---------------------------
Each node is rasterized by a shape-specific :class:`Canvas` drawer keyed off
its declared :class:`NodeShape`: ``DIAMOND`` and ``PARALLELOGRAM`` taper on
slant glyphs (╱╲), ``ROUND``/``STADIUM``/``CIRCLE`` share a rounded-corner
(╭╮╰╯) border (``CIRCLE`` sized wider so it reads as an oval), ``CYLINDER``
pairs a rounded top cap with a square bottom, ``HEXAGON`` cuts its four
corners on the diagonal, and ``SUBROUTINE`` adds an inner double-bar side —
``RECT`` (and any shape whose box is too small for its own drawer's minimum
dimensions) falls back to the plain rectangle border. Every drawer reserves
its full bounding box (see :meth:`Canvas.draw_box`), so the router treats
every shape as an impassable rectangle regardless of its visual outline.
``subgraph`` blocks are drawn as enclosing frames via :meth:`Canvas.draw_frame`
(bottom-up bounding rect of their members plus padding, left-anchored title,
nesting handled by :func:`_build_subgraph_frames`) when their members are
placed contiguously enough for a clean rect; otherwise the subgraph flattens
(no frame, members still drawn) rather than draw a frame that visually
claims a non-member node. Frames are drawn first (behind), then node boxes,
then edges.

Edges get the full orthogonal router. Per edge, endpoint anchors are chosen
by the two boxes' *relative rank position* (their spans along the rank axis
either overlap — same rank — or one is strictly ahead of the other, a test
that holds regardless of direction because rank bands are always separated
by a clear gap): a forward edge exits/enters the border facing the rank-flow
direction (``bottom_mid``/``top_mid`` for TB, mirrored/transposed for
BT/LR/RL); a same-rank edge uses the two boxes' facing side mids; a back-edge
(destination at an earlier rank — the cycle case) exits/enters the side
perpendicular to the rank axis and routes through a growing side lane so
stacked back-edges never collide (the right side for TB/BT, the bottom side
for LR/RL, per the axis swap). Forward paths are a single straight run when
the two anchors already share a column/row, else a Z/staircase through a jog
row/column between the two ranks' facing borders. That jog defaults to the
band's midpoint, but when 2+ labeled forward edges cross the identical
inter-rank band (TB/BT only — one node fanning out to, or in from, several
labeled neighbors across the same rank transition), each gets its own jog
row spread across the band's interior instead of stacking on one shared row
(:func:`_forward_row_overrides`; the band itself is pre-widened to fit them,
see :func:`_rank_gap_overrides`). Arrowheads (``▼▲▶◀``) are chosen from the
final segment's direction of travel and overwrite the border cell they land
on. Edge labels center on the path's longest straight run (or, for a
row-stacked edge, its own dedicated jog segment specifically), shifting
along it to the nearest cell span clear of a box, a subgraph frame title, a
sibling edge's already-drawn line, or an already-placed label. Self-loops
(``src == dst``, excluded from the grandalf graph) draw a small loop off the
same side used for back-edge lanes, stacking outward per repeated self-loop
on one node.

The router draws only axis-aligned L/Z/C paths and does no global crossing
minimization or obstacle avoidance — a path that would cross another box
simply has those cells skipped by :meth:`Canvas.draw_segment` (reserved
cells are never overwritten by a line). This matches the medium's ceiling
for small (≤~20 node) agent-emitted graphs; see the design doc's
"Orthogonal edge routing" section for the full rationale.

Known degradations (by design, not bugs)
-----------------------------------------
- Node labels wrap via :func:`termrender.style.wrap_text`, which measures
  with ``len()`` internally (a pre-existing termrender limitation, see the
  root ``CLAUDE.md``) — CJK/wide-glyph labels may wrap at the wrong point.
  Box *dimensions*, however, are always computed from :func:`visual_len` of
  the wrapped lines, so the box itself is never too narrow for its content.
- Dense graphs may show edge-line crossings, and two edge labels sharing a
  crowded lane may overlap each other even after the nearest-clear-run
  shift — an accepted limit of the medium, not a routing bug.
- A self-loop or back-edge on/into a minimum-size box (``_MIN_BOX_W``/
  ``_MIN_BOX_H``) may land its arrowhead on a corner glyph rather than a
  straight border cell, since a 1-interior-row/column box has no other
  distinct anchor point to use — cosmetic only.
- An edge referencing a node id absent from the graph (a malformed/hand-built
  :class:`FlowGraph`) is silently skipped rather than raised — the parser is
  expected to guarantee valid endpoints, but this module never crashes on a
  dangling reference.

UML extension points (compartments and arrow kinds)
-----------------------------------------------------
Two opt-in, backward-compatible extension points support UML-flavored
callers (e.g. the mermaid class-diagram renderer) reusing this engine
rather than duplicating its layout/routing:

- A :class:`FlowNode` with ``compartments`` set draws as a plain rectangle
  with a horizontal separator row between each compartment (see
  :meth:`Canvas._draw_rect_compartments` and :func:`_compartment_box_dims`)
  instead of the shape-specific single-label border — the mechanism behind
  a class diagram's name/fields/methods bands. ``compartments is None``
  (every existing caller) is byte-for-byte the original path.
- A :class:`FlowEdge`'s ``dst_arrow_kind``/``src_arrow_kind`` (default
  ``"default"``) select a glyph family independent of ``style`` —
  ``"triangle_hollow"`` (inheritance/realization), ``"diamond_filled"``
  (composition) and ``"diamond_hollow"`` (aggregation) — layered on top of
  the existing direction-computed ``▼▲▶◀`` selection (see
  :func:`_arrow_glyph`).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from grandalf.graphs import Edge, Graph, Vertex
from grandalf.layouts import SugiyamaLayout, VertexViewer

from termrender.renderers.mermaid_flow_model import (
    Direction,
    EdgeStyle,
    FlowEdge,
    FlowGraph,
    FlowNode,
    NodeShape,
    Subgraph,
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

    def draw_box(
        self,
        rect: "BoxRect",
        shape: NodeShape,
        label: str,
        compartments: list[list[str]] | None = None,
    ) -> None:
        """Draw a bordered box + centered wrapped label; reserve every cell.

        Dispatches to a shape-specific border drawer. Every drawer reserves
        the *entire* bounding ``rect`` (border, interior, and any blank
        corner cells outside a non-rectangular outline, e.g. a diamond's
        tapered corners) so the router always treats the shape's full
        bounding box as impassable — a deliberate over-reservation that
        keeps every shape's anchor points (``top_mid``/``bottom_mid``/etc.,
        defined on the bounding rect) meaningful and keeps routing safety
        independent of each shape's exact visual outline.

        ``compartments``, when not ``None``, bypasses the shape drawer
        entirely in favor of :meth:`_draw_rect_compartments` (a plain
        rectangle is the only sensible outline for a multi-band UML box
        regardless of the node's declared ``shape``) — see
        :class:`~termrender.renderers.mermaid_flow_model.FlowNode`'s
        ``compartments`` field.
        """
        if rect.w <= 0 or rect.h <= 0:
            return
        if compartments is not None:
            self._draw_rect_compartments(rect, compartments)
            return
        drawer = _SHAPE_DRAWERS.get(shape, Canvas._draw_rect)
        drawer(self, rect, label or "")

    def _draw_rect_compartments(
        self, rect: "BoxRect", compartments: list[list[str]]
    ) -> None:
        """UML-style compartmented rectangle: a plain rect border with a
        horizontal ``├──┤`` separator row between adjacent compartments (a
        class diagram's name / fields / methods bands). Each compartment's
        lines are drawn exactly as given — no re-wrapping, callers
        pre-format each line to whatever width they want reflected in the
        box — so sizing (:func:`_compartment_box_dims`) and drawing always
        agree on the box's extents. The first compartment (conventionally a
        class/entity name) is centered; later compartments (fields,
        methods, ...) are left-indented by one cell, so the member list
        reads apart from the centered header the way UML tooling usually
        sets them apart. An empty compartment (no lines at all) still
        renders as one blank interior row, so its separators remain visible
        either side of it."""
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        right, bottom = x + w - 1, y + h - 1
        inner_left, inner_right = x + 1, right - 1
        inner_w = max(inner_right - inner_left + 1, 0)
        self.set_char(x, y, "\u250c", reserve=True)
        self.set_char(right, y, "\u2510", reserve=True)
        self.set_char(x, bottom, "\u2514", reserve=True)
        self.set_char(right, bottom, "\u2518", reserve=True)
        for cx in range(x + 1, right):
            self.set_char(cx, y, "\u2500", reserve=True)
            self.set_char(cx, bottom, "\u2500", reserve=True)

        cy = y + 1
        n = len(compartments)
        for i, comp in enumerate(compartments):
            lines = comp if comp else [""]
            for line in lines:
                self.set_char(x, cy, "\u2502", reserve=True)
                self.set_char(right, cy, "\u2502", reserve=True)
                text = visual_center(line, inner_w) if i == 0 else " " + line
                for j in range(inner_w):
                    ch = text[j] if j < len(text) else " "
                    self.set_char(inner_left + j, cy, ch, reserve=True)
                cy += 1
            if i < n - 1:
                self.set_char(x, cy, "\u251c", reserve=True)
                self.set_char(right, cy, "\u2524", reserve=True)
                for cx in range(x + 1, right):
                    self.set_char(cx, cy, "\u2500", reserve=True)
                cy += 1

    def _reserve_blank(self, rect: "BoxRect") -> None:
        """Fill the whole bounding rect with reserved blanks — the common
        first step for every shape drawer, so border glyphs then overlay a
        fully-reserved surface regardless of how much of it stays blank."""
        for cx in range(rect.x, rect.x + rect.w):
            for cy in range(rect.y, rect.y + rect.h):
                self.set_char(cx, cy, " ", reserve=True)

    def _draw_wrapped_label(self, label: str, rows: list[tuple[int, int, int]]) -> None:
        """Center ``label`` (word-wrapped, vertically centered) across a
        list of ``(y, left_x, right_x)`` inclusive per-row spans, top to
        bottom — the shared label-placement primitive every shape drawer
        uses. Rows may vary in width (e.g. the parallelogram's per-row
        skew); wrapping itself uses the narrowest row so no line overflows
        whichever row it lands on.
        """
        if not rows:
            return
        inner_w = min(right - left + 1 for _, left, right in rows)
        if inner_w <= 0:
            return
        lines = wrap_text(label, inner_w)
        start = max(0, (len(rows) - len(lines)) // 2)
        for i, line in enumerate(lines):
            ridx = start + i
            if ridx >= len(rows):
                break
            y, left, right = rows[ridx]
            row_w = right - left + 1
            centered = visual_center(line, row_w)
            for j, ch in enumerate(centered):
                self.set_char(left + j, y, ch, reserve=True)

    def _draw_rect(self, rect: "BoxRect", label: str) -> None:
        """``NodeShape.RECT`` — the plain bordered rectangle every other
        shape falls back to when its own drawer declines (box too small)."""
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
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
        if w - 2 > 0 and h - 2 > 0:
            rows = [(cy, x + 1, right - 1) for cy in range(y + 1, bottom)]
            self._draw_wrapped_label(label, rows)

    def _draw_rounded(self, rect: "BoxRect", label: str) -> None:
        """``NodeShape.ROUND``/``STADIUM``/``CIRCLE`` — rounded ``\u256d\u256e\u2570\u256f`` corners.
        CIRCLE reuses this exact border but is sized wider by
        :func:`_box_dims` so it reads as an oval rather than a plain
        rounded rect — the two shapes share a drawer, not a sizing formula.
        """
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        if w < 2 or h < 2:
            self._draw_rect(rect, label)
            return
        right, bottom = x + w - 1, y + h - 1
        self.set_char(x, y, "\u256d", reserve=True)
        self.set_char(right, y, "\u256e", reserve=True)
        self.set_char(x, bottom, "\u2570", reserve=True)
        self.set_char(right, bottom, "\u256f", reserve=True)
        for cx in range(x + 1, right):
            self.set_char(cx, y, "\u2500", reserve=True)
            self.set_char(cx, bottom, "\u2500", reserve=True)
        for cy in range(y + 1, bottom):
            self.set_char(x, cy, "\u2502", reserve=True)
            self.set_char(right, cy, "\u2502", reserve=True)
            for cx in range(x + 1, right):
                self.set_char(cx, cy, " ", reserve=True)
        if w - 2 > 0 and h - 2 > 0:
            rows = [(cy, x + 1, right - 1) for cy in range(y + 1, bottom)]
            self._draw_wrapped_label(label, rows)

    def _draw_cylinder(self, rect: "BoxRect", label: str) -> None:
        """``NodeShape.CYLINDER`` (``db``) — a rect with a curved top cap
        (``\u256d\u2500\u256e``) and a square bottom, hinting at a database can without a full
        second-ellipse bottom curve."""
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        if w < 2 or h < 2:
            self._draw_rect(rect, label)
            return
        right, bottom = x + w - 1, y + h - 1
        self.set_char(x, y, "\u256d", reserve=True)
        self.set_char(right, y, "\u256e", reserve=True)
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
        if w - 2 > 0 and h - 2 > 0:
            rows = [(cy, x + 1, right - 1) for cy in range(y + 1, bottom)]
            self._draw_wrapped_label(label, rows)

    def _draw_subroutine(self, rect: "BoxRect", label: str) -> None:
        """``NodeShape.SUBROUTINE`` — a rect with an inner ``\u2502`` bar just inside
        each side, the classic double-border predefined-process look. Sized
        two cells wider than a plain rect (see :func:`_box_dims`) so the
        inner bars never eat into the label's own room."""
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        if w < 6 or h < 2:
            self._draw_rect(rect, label)
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
            self.set_char(x + 1, cy, "\u2502", reserve=True)
            self.set_char(right - 1, cy, "\u2502", reserve=True)
            for cx in range(x + 2, right - 1):
                self.set_char(cx, cy, " ", reserve=True)
        if right - 1 - (x + 2) >= 0 and h - 2 > 0:
            rows = [(cy, x + 2, right - 2) for cy in range(y + 1, bottom)]
            self._draw_wrapped_label(label, rows)

    def _draw_hexagon(self, rect: "BoxRect", label: str) -> None:
        """``NodeShape.HEXAGON`` — a rect with its four corner cells cut on the
        diagonal (``\u2571``/``\u2572``), an octagon-ish silhouette that reads as angled
        left/right sides without a full continuous-taper geometry."""
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        if w < 5 or h < 2:
            self._draw_rect(rect, label)
            return
        right, bottom = x + w - 1, y + h - 1
        self._reserve_blank(rect)
        self.set_char(x + 1, y, "\u2571", reserve=True)
        self.set_char(right - 1, y, "\u2572", reserve=True)
        self.set_char(x + 1, bottom, "\u2572", reserve=True)
        self.set_char(right - 1, bottom, "\u2571", reserve=True)
        for cx in range(x + 2, right - 1):
            self.set_char(cx, y, "\u2500", reserve=True)
            self.set_char(cx, bottom, "\u2500", reserve=True)
        for cy in range(y + 1, bottom):
            self.set_char(x, cy, "\u2502", reserve=True)
            self.set_char(right, cy, "\u2502", reserve=True)
        if h - 2 > 0:
            rows = [(cy, x + 1, right - 1) for cy in range(y + 1, bottom)]
            self._draw_wrapped_label(label, rows)

    def _draw_parallelogram(self, rect: "BoxRect", label: str) -> None:
        """``NodeShape.PARALLELOGRAM`` — both vertical sides drawn with the
        same slash direction (``\u2571``), shifted a little further right on
        earlier (higher) rows than later ones, so the whole box leans —
        the parallelogram look, as opposed to a diamond's opposite-facing
        slants. Sized ``_PARALLELOGRAM_SKEW`` cells wider than the logical
        content rect (see :func:`_box_dims`) to make room for the lean."""
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        logical_w = w - _PARALLELOGRAM_SKEW
        if logical_w < 3 or h < 2:
            self._draw_rect(rect, label)
            return
        self._reserve_blank(rect)
        rows: list[tuple[int, int, int]] = []
        for i in range(h):
            cy = y + i
            shift = (
                round(_PARALLELOGRAM_SKEW * (h - 1 - i) / (h - 1)) if h > 1 else 0
            )
            left = x + shift
            right = left + logical_w - 1
            self.set_char(left, cy, "\u2571", reserve=True)
            self.set_char(right, cy, "\u2571", reserve=True)
            if i in (0, h - 1):
                for cx in range(left + 1, right):
                    self.set_char(cx, cy, "\u2500", reserve=True)
            elif right - 1 >= left + 1:
                rows.append((cy, left + 1, right - 1))
        self._draw_wrapped_label(label, rows)

    def _draw_diamond(self, rect: "BoxRect", label: str) -> None:
        """``NodeShape.DIAMOND`` — a rhombus outline: ``taper`` rows of
        corner-inset ``\u2571``/``\u2572`` sides above and below a flat label band,
        where ``taper`` (derived from the label, see :func:`_diamond_taper`)
        matches what :func:`_box_dims` sized the box for. Falls back to a
        plain rect if the box is too small for any taper at all."""
        x, y, w, h = rect.x, rect.y, rect.w, rect.h
        if w < 5 or h < 3:
            self._draw_rect(rect, label)
            return
        max_taper = max(1, (w - 1) // 2)
        content_lines = wrap_text(label, max(w - 4, 1)) or [""]
        taper = max(1, (h - len(content_lines)) // 2)
        taper = min(taper, max_taper, (h - 1) // 2 or 1)
        if h - 2 * taper < 1:
            taper = max(1, (h - 1) // 2)
        self._reserve_blank(rect)
        right, bottom = x + w - 1, y + h - 1
        rows: list[tuple[int, int, int]] = []
        for i in range(h):
            cy = y + i
            if i < taper:
                indent = taper - i
            elif i >= h - taper:
                indent = i - (h - taper) + 1
            else:
                indent = 0
            left = x + indent
            rgt = right - indent
            if left > rgt:
                continue
            if indent == 0:
                self.set_char(x, cy, "\u2502", reserve=True)
                self.set_char(right, cy, "\u2502", reserve=True)
                rows.append((cy, x + 1, right - 1))
                continue
            upper_half = i < taper
            left_glyph = "\u2571" if upper_half else "\u2572"
            right_glyph = "\u2572" if upper_half else "\u2571"
            self.set_char(left, cy, left_glyph, reserve=True)
            if rgt != left:
                self.set_char(rgt, cy, right_glyph, reserve=True)
        self._draw_wrapped_label(label, rows)

    def draw_frame(self, rect: "BoxRect", title: str) -> None:
        """Draw a subgraph enclosure: light border, left-anchored title.

        Frame cells are NOT reserved — nodes and edges live inside a
        subgraph frame and may legitimately cross its border lines (a
        cross-boundary edge routing from a member to a non-member, or vice
        versa, draws right over the top/bottom/side border runs, which
        reads fine as an ordinary crossing). The title *text* is the one
        exception: it is reserved so a crossing edge's line segment is
        skipped there rather than clobbering a letter of the label — the
        router already treats a skipped reserved cell as an acceptable
        small gap in the line (the same tolerance it gives box interiors),
        which is far less visually broken than corrupted title text.
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
        if title:
            title_start = x + 3
            title_len = visual_len(title)
            for i in range(title_len):
                if title_start + i < x + w - 1:
                    self.reserved[y][title_start + i] = True

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


# NodeShape -> Canvas border-drawer method, consulted by draw_box. RECT (and
# any shape not listed here, defensively) falls back to _draw_rect.
_SHAPE_DRAWERS: dict[NodeShape, "Callable[[Canvas, BoxRect, str], None]"] = {
    NodeShape.RECT: Canvas._draw_rect,
    NodeShape.ROUND: Canvas._draw_rounded,
    NodeShape.STADIUM: Canvas._draw_rounded,
    NodeShape.CIRCLE: Canvas._draw_rounded,
    NodeShape.CYLINDER: Canvas._draw_cylinder,
    NodeShape.SUBROUTINE: Canvas._draw_subroutine,
    NodeShape.HEXAGON: Canvas._draw_hexagon,
    NodeShape.PARALLELOGRAM: Canvas._draw_parallelogram,
    NodeShape.DIAMOND: Canvas._draw_diamond,
}


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

# Per-shape extra cells added around the base rect sizing, so the interior
# usable area (where the wrapped label actually lands) is never smaller than
# a plain rect would give it — shapes whose border eats into the bounding
# box (diamond taper, hexagon's corner cut, subroutine's inner bars, the
# parallelogram's skew) get compensating extra width/height here rather than
# shrinking the label's room. See ``Canvas``'s ``_draw_*`` methods below for
# how each shape actually consumes this extra space.
_CIRCLE_EXTRA_W = 4      # wider than ROUND so it reads as an oval, not a rect.
_SUBROUTINE_EXTRA_W = 2  # room for the inner ``││`` double-bar sides.
_HEXAGON_EXTRA_W = 2     # room for the corner-cut cells at each side.
_PARALLELOGRAM_SKEW = 2  # total horizontal lean across the box's height.
_DIAMOND_MIN_TAPER = 1
_DIAMOND_MAX_TAPER = 2


def _diamond_taper(content_w: int) -> int:
    """Rows of corner-taper on each side of a diamond's flat label band —
    a small fixed range (not scaled to full 45° geometry, which would make
    short labels absurdly tall) so the point is visible without ballooning
    box height for the common short decision-label case."""
    return _DIAMOND_MIN_TAPER if content_w <= 3 else _DIAMOND_MAX_TAPER


def _compartment_box_dims(compartments: list[list[str]]) -> tuple[int, int]:
    """Content-driven extents for a UML-style compartmented box: width from
    the widest line across *every* compartment (no per-line wrap — see
    :meth:`Canvas._draw_rect_compartments`), height from the total line
    count plus one separator row between each adjacent pair of
    compartments. Mirrors :func:`_box_dims`'s ``+4``/``+2`` border+padding
    convention so a compartmented box sizes consistently with a plain one.
    """
    all_lines = [line for comp in compartments for line in (comp if comp else [""])]
    content_w = max((visual_len(line) for line in all_lines), default=0)
    content_h = sum(len(comp) if comp else 1 for comp in compartments)
    separators = max(len(compartments) - 1, 0)
    w = max(content_w + 4, _MIN_BOX_W)
    h = max(content_h + separators + 2, _MIN_BOX_H)
    return w, h


def _box_dims_for_node(n: FlowNode) -> tuple[int, int]:
    """Dispatch box sizing on whether ``n`` carries UML-style
    ``compartments`` — the model-level extension point that keeps every
    other node's sizing (and thus every existing golden-output test)
    byte-for-byte unchanged."""
    if n.compartments is not None:
        return _compartment_box_dims(n.compartments)
    return _box_dims(n.label, n.shape)


def _box_dims(label: str, shape: NodeShape = NodeShape.RECT) -> tuple[int, int]:
    """Content-driven box extents (cells), used both to size the grandalf
    ``VertexViewer`` and later to actually draw the box — sizing always goes
    through :func:`visual_len` so wide glyphs are never under-reserved (see
    the design doc's CJK open risk). Shape-aware: several shapes need more
    room than a plain rect to keep the label clear of their slanted/curved
    border (see the module-level ``_*_EXTRA_*`` constants)."""
    lines = wrap_text(label or "", _MAX_LABEL_CONTENT_WIDTH) or [""]
    content_w = max((visual_len(line) for line in lines), default=0)
    content_h = len(lines)

    if shape is NodeShape.DIAMOND:
        taper = _diamond_taper(content_w)
        w = max(content_w + 4, _MIN_BOX_W)
        h = max(content_h + 2 * taper, 2 * taper + 1)
        return w, h
    if shape is NodeShape.CIRCLE:
        w = max(content_w + 4 + _CIRCLE_EXTRA_W, _MIN_BOX_W + _CIRCLE_EXTRA_W)
        h = max(content_h + 2, _MIN_BOX_H)
        return w, h
    if shape is NodeShape.SUBROUTINE:
        w = max(content_w + 4 + _SUBROUTINE_EXTRA_W, _MIN_BOX_W + _SUBROUTINE_EXTRA_W)
        h = max(content_h + 2, _MIN_BOX_H)
        return w, h
    if shape is NodeShape.HEXAGON:
        w = max(content_w + 4 + _HEXAGON_EXTRA_W, _MIN_BOX_W + _HEXAGON_EXTRA_W)
        h = max(content_h + 2, _MIN_BOX_H)
        return w, h
    if shape is NodeShape.PARALLELOGRAM:
        w = max(content_w + 4, _MIN_BOX_W) + _PARALLELOGRAM_SKEW
        h = max(content_h + 2, _MIN_BOX_H)
        return w, h
    # RECT, ROUND, STADIUM, CYLINDER share the plain rect's base sizing —
    # their border decoration lives entirely in the existing border cells.
    w = max(content_w + 4, _MIN_BOX_W)
    h = max(content_h + 2, _MIN_BOX_H)
    return w, h


# --------------------------------------------------------------------------
# --- adapter ---
# --------------------------------------------------------------------------

_GAP_X = 3          # minimum border-to-border gap between boxes in one rank/band
_ROW_GAP = 2         # minimum gap between rank bands
_COMPONENT_GUTTER = 4  # gap between independently-laid-out components
_LABEL_GAP_PAD = 1   # cells of breathing room either side of a label's own text
                     # when it forces a rank-band gap wider than _ROW_GAP
                     # along the axis the label's text actually runs.
_LABELED_ROW_GAP = 3  # inter-rank gap when a label sits on that band's vertical
                      # run in *final* screen space (TB/BT): one blank row, the
                      # label's own row, one more blank row. A constant, not
                      # scaled by the label's text length — the label reads
                      # horizontally on a single row regardless of how many
                      # characters it has, so the row *count* needed is fixed.


def _rank_gap_overrides(
    edges: list[FlowEdge], rank_of: dict[str, int], direction: Direction
) -> dict[int, int]:
    """Minimum inter-rank-band gap keyed by the *lower* rank of each
    adjacent-rank transition, widened past ``_ROW_GAP`` wherever a labeled
    edge directly connects that transition's two ranks. A forward edge
    between adjacent ranks routes as a single straight run (or a Z path
    that still crosses the same inter-rank band) whose only clear space is
    this gap.

    The rank axis is native rows here, pre-direction-transform (see the
    adapter docstring) — whether that ends up as *vertical* or
    *horizontal* space on screen depends on ``direction``. For LR/RL the
    transpose turns this band into the final horizontal run the label
    reads along, so it genuinely needs ``visual_len(label)`` cells of
    width — at the base ``_ROW_GAP`` a label wider than a couple of cells
    has nowhere to go but onto the boxes it connects (the short
    LR/adjacent-rank clipped-label bug this closes); when several labeled
    edges share one LR/RL transition their labels land at different
    *secondary* (row) coordinates already (different destination nodes),
    so only the widest single label's width matters here, not the count.
    For TB/BT the band stays vertical on screen and each label is drawn
    horizontally *across* the connector column (:func:`_draw_label_on_segment`'s
    vertical-segment branch), one label per row — a single labeled edge
    needs only the small constant ``_LABELED_ROW_GAP`` (one blank row, the
    label's own row, one more blank row), but when ``n`` labeled edges
    cross the *same* adjacent-rank transition (e.g. one node forward-fans
    into several labeled destinations, or several labeled sources converge
    on one destination) each needs its own row, one blank row apart from
    its neighbors, so the gap grows by 2 native rows per additional edge
    (see :func:`_forward_row_overrides`, which spreads each such edge's
    jog row across this now-widened band's interior).

    Non-adjacent-rank edges (back-edges, multi-rank spans) don't constrain
    the gap here — they route through their own side lane, not this band.
    """
    overrides: dict[int, int] = {}
    counts: dict[int, int] = defaultdict(int)
    horizontal_on_screen = direction in (Direction.LR, Direction.RL)
    for e in edges:
        if e.src == e.dst or not e.label:
            continue
        r_src = rank_of.get(e.src)
        r_dst = rank_of.get(e.dst)
        if r_src is None or r_dst is None:
            continue
        lo_r, hi_r = (r_src, r_dst) if r_src <= r_dst else (r_dst, r_src)
        if hi_r - lo_r != 1:
            continue
        counts[lo_r] += 1
        if horizontal_on_screen:
            needed = visual_len(e.label) + 2 * _LABEL_GAP_PAD
        else:
            needed = _LABELED_ROW_GAP
        overrides[lo_r] = max(overrides.get(lo_r, _ROW_GAP), needed)
    if not horizontal_on_screen:
        for lo_r, n in counts.items():
            if n > 1:
                overrides[lo_r] = max(overrides[lo_r], _LABELED_ROW_GAP + (n - 1) * 2)
    return overrides


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
    nodes: list[FlowNode],
    edges: list[FlowEdge],
    direction: Direction,
    node_subgraph: dict[str, str] | None = None,
) -> dict[str, BoxRect]:
    node_subgraph = node_subgraph or {}
    dims = {n.id: _box_dims_for_node(n) for n in nodes}
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

        rank_of = {v.data: sug.grx[v].rank for v in comp_vertices}
        gap_overrides = _rank_gap_overrides(edges, rank_of, direction)

        band_top_for_rank: dict[int, int] = {}
        cursor = 0
        for r in sorted(ranks):
            band_top_for_rank[r] = cursor
            max_h = max(native[v.data][1] for v in ranks[r])
            cursor += max_h + gap_overrides.get(r, _ROW_GAP)

        min_x = min(v.view.xy[0] for v in comp_vertices)
        provisional = {v: round(v.view.xy[0] - min_x) for v in comp_vertices}

        # Cluster same-subgraph siblings within a rank: group by the outer
        # subgraph (if any) each node belongs to, order groups by their mean
        # provisional column (approximating grandalf's crossing-minimized
        # order), then order nodes within a group by their own provisional
        # column. This keeps a subgraph's members contiguous within a rank
        # — which is what makes a clean bounding-rect frame feasible —
        # without fighting grandalf's ordering across groups. "Reasonably
        # clustered", not a hard guarantee (see module docstring); a
        # subgraph frame that still isn't feasible after this flattens
        # gracefully at the frame-computation step.
        actual_col: dict[Vertex, int] = {}
        for r in sorted(ranks):
            row_nodes = ranks[r]
            groups: dict[str | None, list[Vertex]] = defaultdict(list)
            for v in row_nodes:
                groups[node_subgraph.get(v.data)].append(v)
            group_avg = {
                key: sum(provisional[v] for v in vs) / len(vs)
                for key, vs in groups.items()
            }
            row_nodes = sorted(
                row_nodes,
                key=lambda v: (group_avg[node_subgraph.get(v.data)], provisional[v]),
            )
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

        # ``actual_col`` is a *center* coordinate per node, not a left edge —
        # shifting so the smallest center is 0 (above) does not guarantee
        # the smallest node's own left edge (``col - native_w // 2``) is
        # non-negative. Re-shift so the component's true leftmost edge sits
        # at 0, so ``comp_width`` below (and thus the next component's
        # offset) reflects the component's real full extent rather than
        # under-counting by half of its leftmost node's width — otherwise
        # consecutive components end up flush against each other with the
        # component gutter silently eaten.
        left_edge_min = min(
            actual_col[v] - native[v.data][0] // 2 for v in comp_vertices
        )
        if left_edge_min < 0:
            for v in actual_col:
                actual_col[v] -= left_edge_min

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


def _node_subgraph_map(subgraphs: list[Subgraph]) -> dict[str, str]:
    """node id -> the id of the outer-most (top-level) subgraph transitively
    containing it. Used by :func:`_place_nodes` to cluster a subgraph's
    members within a rank — nested children share their top-level
    ancestor's key here, since clustering only needs to keep a whole
    subtree's nodes together, not distinguish nesting level."""
    mapping: dict[str, str] = {}

    def visit(sg: Subgraph, top_id: str) -> None:
        for nid in sg.node_ids:
            mapping.setdefault(nid, top_id)
        for child in sg.children:
            visit(child, top_id)

    for sg in subgraphs:
        visit(sg, sg.id)
    return mapping


_FRAME_PAD_X = 1     # columns of padding each side, between members and the frame border.
_FRAME_PAD_TOP = 1   # blank interior rows between the title border and the members.
_FRAME_PAD_BOTTOM = 1  # blank interior rows between the members and the bottom border.


def _member_ids(sg: Subgraph) -> set[str]:
    ids = set(sg.node_ids)
    for child in sg.children:
        ids |= _member_ids(child)
    return ids


def _rects_overlap(a: BoxRect, b: BoxRect) -> bool:
    return not (
        a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y
    )


def _build_subgraph_frames(
    sg: Subgraph, rects: dict[str, BoxRect]
) -> tuple[list[tuple[BoxRect, str]], BoxRect | None]:
    """Recursively compute one subgraph's frame(s) bottom-up, returning
    ``(frames_in_this_subtree, bound_for_parent)``.

    ``bound_for_parent`` is what the *enclosing* subgraph's own extent
    computation should treat this subtree as occupying: if ``sg`` itself
    gets a frame, that is its full padded ``frame_rect`` (border included)
    — never just the raw member extent — so a parent subgraph's own
    padding is guaranteed to land outside this child's frame border rather
    than colliding with it (the bug this replaces: two nested subgraphs
    whose members share the same column/row span used to produce
    identically-sized frame rects, so the inner frame's border landed
    exactly on the outer's, overwriting it). If ``sg`` flattens (or has no
    placed members at all), the bound is its raw member/child extent (or
    ``None``) instead, matching the old behavior for that case.

    ``None`` when nothing inside resolves to a placed node (an empty or
    entirely-dangling subgraph): the caller flattens in that case.
    """
    child_results = [_build_subgraph_frames(child, rects) for child in sg.children]
    child_frames: list[tuple[BoxRect, str]] = []
    for cframes, _ in child_results:
        child_frames.extend(cframes)

    boxes: list[BoxRect] = [rects[nid] for nid in sg.node_ids if nid in rects]
    boxes.extend(bound for _, bound in child_results if bound is not None)
    if not boxes:
        return child_frames, None

    x0 = min(b.x for b in boxes)
    y0 = min(b.y for b in boxes)
    x1 = max(b.x + b.w for b in boxes)
    y1 = max(b.y + b.h for b in boxes)
    extent = BoxRect(x=x0, y=y0, w=x1 - x0, h=y1 - y0)

    # +2 on width/height accounts for the frame's own border cells (draw_frame
    # draws them at the rect's edges); the pad constants are blank interior
    # rows/columns between those borders and the members themselves.
    frame_rect = BoxRect(
        x=extent.x - _FRAME_PAD_X - 1,
        y=extent.y - _FRAME_PAD_TOP - 1,
        w=extent.w + 2 * _FRAME_PAD_X + 2,
        h=extent.h + _FRAME_PAD_TOP + _FRAME_PAD_BOTTOM + 2,
    )
    # draw_frame left-anchors and truncates its title to whatever width it's
    # given (it does not widen itself) — widen here so a title longer than
    # the members' own bounding box still shows in full, extending rightward
    # only (title stays left-anchored).
    title_min_w = visual_len(f"\u2500 {sg.title} ") + 2 if sg.title else 4
    if title_min_w > frame_rect.w:
        frame_rect = BoxRect(
            x=frame_rect.x, y=frame_rect.y, w=title_min_w, h=frame_rect.h
        )

    member_ids = _member_ids(sg)
    foreign_overlap = any(
        node_id not in member_ids and _rects_overlap(frame_rect, r)
        for node_id, r in rects.items()
    )
    if foreign_overlap:
        # Flatten: no frame for sg itself, but its raw (unpadded) extent
        # still bounds whatever parent subgraph encloses it, and its
        # children's own frames (if any) are unaffected.
        return child_frames, extent
    return [(frame_rect, sg.title)] + child_frames, frame_rect


def _collect_frames(
    subgraphs: list[Subgraph], rects: dict[str, BoxRect]
) -> list[tuple[BoxRect, str]]:
    """Frame rects (padded, with room for the title border) for every
    subgraph feasible to enclose — outer subgraphs before their nested
    children, matching draw order (frames are drawn outer-to-inner, then
    node boxes on top of all of them; see ``layout_flowgraph``).

    A subgraph is skipped (flattened — its members still render as plain
    boxes, just with no enclosing frame) when its members aren't placed
    contiguously enough for a clean rect: if the padded bounding box would
    overlap any OTHER node's box (one not transitively a member of this
    subgraph), drawing the frame would visually claim a node that isn't
    inside it, which is worse than no frame. Each subgraph's feasibility is
    judged independently — a flattened parent doesn't suppress its
    children's own frames. Nesting is bottom-up (see
    :func:`_build_subgraph_frames`) so a parent's own frame always encloses
    its children's frames with real margin, never coinciding with one.
    """
    frames: list[tuple[BoxRect, str]] = []
    for sg in subgraphs:
        sg_frames, _ = _build_subgraph_frames(sg, rects)
        frames.extend(sg_frames)
    return frames


# --------------------------------------------------------------------------
# --- router ---
# --------------------------------------------------------------------------

# The full orthogonal router. Endpoint anchors are chosen from each edge's
# *relative rank position* (forward / same-rank / back-edge); forward edges
# route a straight or Z-shaped (staircase) path through the clear inter-rank
# band, same-rank edges route between facing side mids, and back-edges route
# through a growing side lane so they never overlay forward edges. See the
# design doc's "Orthogonal edge routing" section for the full rationale —
# this module implements it without re-deciding any of it.

_LANE_GAP = 2      # spacing between stacked back-edge side lanes
_LANE_MARGIN = 2   # gap from the involved boxes' far edge to the first lane
_LOOP_REACH = 3    # base horizontal/vertical extent of a self-loop

_ARROW_GLYPHS: dict[tuple[int, int], str] = {
    (1, 0): "\u25b6",   # ▶
    (-1, 0): "\u25c0",  # ◀
    (0, 1): "\u25bc",   # ▼
    (0, -1): "\u25b2",  # ▲
}

# Direction-aware hollow-triangle glyphs for FlowEdge.dst_arrow_kind/
# src_arrow_kind == "triangle_hollow" (UML inheritance/realization) — same
# shape as _ARROW_GLYPHS, hollow instead of filled.
_HOLLOW_TRIANGLE_GLYPHS: dict[tuple[int, int], str] = {
    (1, 0): "\u25b7",   # ▷
    (-1, 0): "\u25c1",  # ◁
    (0, 1): "\u25bd",   # ▽
    (0, -1): "\u25b3",  # △
}

# arrow-kind name -> either a direction glyph table (looked up the same way
# as _ARROW_GLYPHS) or a single direction-invariant glyph string (a diamond
# reads the same rotated, so composition/aggregation need no per-direction
# variants). An unrecognized kind (defensive: a hand-built FlowEdge with a
# typo'd kind string) falls back to "default" rather than raising.
_ARROW_KIND_GLYPHS: dict[str, dict[tuple[int, int], str] | str] = {
    "default": _ARROW_GLYPHS,
    "triangle_hollow": _HOLLOW_TRIANGLE_GLYPHS,
    "diamond_filled": "\u25c6",   # ◆ — composition
    "diamond_hollow": "\u25c7",   # ◇ — aggregation
}


def _facing_anchor(this: BoxRect, other: BoxRect) -> tuple[int, int]:
    """Pick the border midpoint of ``this`` box facing toward ``other`` —
    used for same-rank edges, where neither box is "ahead" of the other
    along the rank axis."""
    tcx, tcy = this.center
    ocx, ocy = other.center
    dx, dy = ocx - tcx, ocy - tcy
    if abs(dy) >= abs(dx):
        return this.bottom_mid if dy >= 0 else this.top_mid
    return this.right_mid if dx >= 0 else this.left_mid


def _arrow_glyph(
    frm: tuple[int, int], to: tuple[int, int], kind: str = "default"
) -> str:
    """The glyph an arrowhead landing at ``to`` should show, for the
    direction of travel from ``frm`` to ``to``. ``kind`` (see
    ``FlowEdge.dst_arrow_kind``/``src_arrow_kind``) selects the glyph
    family; ``"default"`` reproduces the original ``▼▲▶◀`` filled-triangle
    behavior exactly. A direction-invariant kind (a diamond) ignores
    ``frm``/``to`` beyond the degenerate same-point guard."""
    table = _ARROW_KIND_GLYPHS.get(kind, _ARROW_GLYPHS)
    if isinstance(table, str):
        return table
    dx, dy = to[0] - frm[0], to[1] - frm[1]
    if dx == 0 and dy == 0:
        return table[(0, 1)]
    if abs(dx) >= abs(dy):
        return table[(1 if dx > 0 else -1, 0)]
    return table[(0, 1 if dy > 0 else -1)]


def _rank_is_horizontal(direction: Direction) -> bool:
    """True when the rank-flow axis is x (LR/RL) rather than y (TB/BT)."""
    return direction in (Direction.LR, Direction.RL)


def _forward_increasing(direction: Direction) -> bool:
    """True when rank number increases with increasing coordinate along the
    rank axis (TB: increasing y; LR: increasing x) — false for BT/RL, whose
    adapter coordinate transform mirrors that axis (see module docstring)."""
    return direction in (Direction.TB, Direction.LR)


def _rank_extent(direction: Direction, rect: BoxRect) -> tuple[int, int]:
    """``rect``'s [min, max] span along the rank axis. Two boxes in the same
    rank always have overlapping spans (the adapter places a whole rank in
    one top/bottom-aligned band); boxes in different ranks never do, since
    ``_ROW_GAP``/``_GAP_X`` guarantee a clear gap between bands — so span
    overlap is a direction-agnostic same-rank test."""
    if _rank_is_horizontal(direction):
        return (rect.x, rect.x + rect.w - 1)
    return (rect.y, rect.y + rect.h - 1)


def _forward_exit(direction: Direction, rect: BoxRect) -> tuple[int, int]:
    """``rect``'s border anchor facing *downstream* along the rank axis."""
    horiz = _rank_is_horizontal(direction)
    forward = _forward_increasing(direction)
    if horiz:
        return rect.right_mid if forward else rect.left_mid
    return rect.bottom_mid if forward else rect.top_mid


def _forward_entry(direction: Direction, rect: BoxRect) -> tuple[int, int]:
    """``rect``'s border anchor facing *upstream* — the mirror image of
    :func:`_forward_exit`, used on the destination side of a forward edge."""
    horiz = _rank_is_horizontal(direction)
    forward = _forward_increasing(direction)
    if horiz:
        return rect.left_mid if forward else rect.right_mid
    return rect.top_mid if forward else rect.bottom_mid


def _lane_anchor(direction: Direction, rect: BoxRect) -> tuple[int, int]:
    """``rect``'s border anchor on the side used for back-edge side lanes
    and self-loops: the side perpendicular to the rank axis and away from
    it — the right side for TB/BT, the bottom side for LR/RL ("the right
    lane becomes the bottom lane" after LR/RL's axis swap)."""
    return rect.bottom_mid if _rank_is_horizontal(direction) else rect.right_mid


# --- shared-anchor fan-out (multiple edges through one node's side) ---
#
# The four anchor functions above always return the *same* single point for
# a given (direction, rect) — correct for the common case of one edge per
# side, but when 2+ edges share a node's exit or entry side (e.g. two
# forward edges leaving the same node), every one of them would otherwise
# start/end its path on the exact same cell. Two visible bugs follow: a
# src-side arrow-kind marker glyph landing there survives only for the
# last-drawn edge (see mermaid_class.py's UML composition/aggregation
# case), and — whenever the shared first/last segment happens to tie in
# length with each edge's own distinguishing segment (routine in LR/RL,
# where a node's fan-out run and its branch runs can all measure the same
# few cells) — :func:`_longest_segment`'s tie-break picks the *shared*
# segment for both edges' labels, so a second label lands on cells the
# first already claimed and is silently dropped. ``_allocate_edge_anchors``
# is a pre-pass that spreads such shared anchors along the side's usable
# span; groups of size 1 (the overwhelming majority of edges) are left
# alone entirely (no override), so every existing single-edge-per-side
# render is byte-for-byte unchanged.


def _forward_exit_side(direction: Direction) -> str:
    """Side name matching :func:`_forward_exit` for ``direction`` — a
    node's forward exit side is the same physical side for every node in
    the graph (it depends only on direction), which is exactly what makes
    grouping by ``(node_id, side)`` meaningful."""
    horiz = _rank_is_horizontal(direction)
    forward = _forward_increasing(direction)
    if horiz:
        return "right" if forward else "left"
    return "bottom" if forward else "top"


def _forward_entry_side(direction: Direction) -> str:
    """Side name matching :func:`_forward_entry` — the mirror image of
    :func:`_forward_exit_side`."""
    horiz = _rank_is_horizontal(direction)
    forward = _forward_increasing(direction)
    if horiz:
        return "left" if forward else "right"
    return "top" if forward else "bottom"


def _lane_side(direction: Direction) -> str:
    """Side name matching :func:`_lane_anchor`."""
    return "bottom" if _rank_is_horizontal(direction) else "right"


def _diamond_straight_span(rect: BoxRect, label: str) -> tuple[int, int]:
    """A ``NodeShape.DIAMOND``'s left/right sides are only straight (``│``)
    across its flat label band, between the two tapered corners — mirrors
    :meth:`Canvas._draw_diamond`'s own taper calculation exactly (kept in
    sync deliberately: this is the sizing-time read of that drawing-time
    geometry) so a spread anchor never lands in the taper region, where
    the ``│`` a plain rect would have is instead a blank cell just outside
    the diamond's slanted outline (or the slant glyph itself) — either way
    a line touching down there reads as visually detached from the shape.
    Collapses to a single point (``lo == hi``) for a diamond too small to
    have more than one straight row, exactly reproducing the un-spread
    single-anchor point in that case."""
    x, y, w, h = rect.x, rect.y, rect.w, rect.h
    if w < 5 or h < 3:
        return y + h // 2, y + h // 2
    max_taper = max(1, (w - 1) // 2)
    content_lines = wrap_text(label or "", max(w - 4, 1)) or [""]
    taper = max(1, (h - len(content_lines)) // 2)
    taper = min(taper, max_taper, (h - 1) // 2 or 1)
    if h - 2 * taper < 1:
        taper = max(1, (h - 1) // 2)
    lo, hi = y + taper, y + h - taper - 1
    if lo > hi:
        lo = hi = y + h // 2
    return lo, hi


def _side_span_for_node(
    node: "FlowNode | None", rect: BoxRect, side: str
) -> tuple[int, int]:
    """Usable ``[lo, hi]`` anchor span along one border side of a placed
    node — shape-aware only where a shape's straight border cells don't
    already span the full bounding-rect side (currently just
    ``NodeShape.DIAMOND``; every other shape's visible border decoration
    lives entirely within the bounding-rect span :func:`_side_interior_span`
    already describes, including shapes whose glyphs aren't literally
    straight everywhere, e.g. the hexagon's corner cut or the
    parallelogram's skew — those already anchor at the plain bounding-rect
    mid in the single-edge case, so reusing that same span here keeps the
    multi-edge case consistent with it rather than introducing a second,
    stricter geometry only this function knows about). A diamond's
    top/bottom sides are a single tip point, not a span — collapsed to the
    bounding-rect mid column/row, same as :func:`_forward_exit` already
    anchors there.
    """
    if node is not None and node.compartments is None and node.shape is NodeShape.DIAMOND:
        if side in ("left", "right"):
            return _diamond_straight_span(rect, node.label)
        mid = rect.x + rect.w // 2
        return mid, mid
    return _side_interior_span(rect, side)


def _side_interior_span(rect: BoxRect, side: str) -> tuple[int, int]:
    """Usable ``[lo, hi]`` span (inclusive) along one border side of
    ``rect``, corners excluded when the side is long enough to spare them
    (falls back to the full span at minimum box size, where the interior
    excluding corners would otherwise be empty). This is deliberately a
    *different* (slightly narrower) span than the single-anchor
    ``top_mid``/``bottom_mid``/``left_mid``/``right_mid`` properties use —
    only :func:`_allocate_edge_anchors` (the 2+-edges-per-side case)
    consults this, so the single-edge case's existing anchor point (and
    every golden built on it) is untouched."""
    if side in ("top", "bottom"):
        lo, hi = rect.x + 1, rect.x + rect.w - 2
        if lo > hi:
            lo, hi = rect.x, rect.x + rect.w - 1
        return lo, hi
    lo, hi = rect.y + 1, rect.y + rect.h - 2
    if lo > hi:
        lo, hi = rect.y, rect.y + rect.h - 1
    return lo, hi


def _side_point(rect: BoxRect, side: str, along: int) -> tuple[int, int]:
    """A border point on ``rect``'s ``side`` at the given along-the-side
    coordinate (from :func:`_side_interior_span`/:func:`_spread_points`)."""
    if side == "top":
        return (along, rect.y)
    if side == "bottom":
        return (along, rect.y + rect.h - 1)
    if side == "left":
        return (rect.x, along)
    return (rect.x + rect.w - 1, along)  # "right"


def _spread_points(lo: int, hi: int, n: int) -> list[int]:
    """``n`` coordinates evenly spread across ``[lo, hi]`` inclusive (the
    first at ``lo``, the last at ``hi``) — callers only ever invoke this
    for ``n >= 2``."""
    if n <= 1:
        return [(lo + hi) // 2]
    span = hi - lo
    return [lo + round(i * span / (n - 1)) for i in range(n)]


def _classify_edge(
    rects: dict[str, BoxRect], direction: Direction, edge: FlowEdge
) -> str | None:
    """One of ``"same-rank"``, ``"forward"``, ``"back"``, or ``None``
    (dangling node-id reference — the parser guarantees valid endpoints,
    but this module never crashes on one). Shared by
    :func:`_allocate_edge_anchors` and :func:`_route_edge_path` so the two
    never disagree about which routing branch an edge takes."""
    src_rect = rects.get(edge.src)
    dst_rect = rects.get(edge.dst)
    if src_rect is None or dst_rect is None:
        return None
    src_extent = _rank_extent(direction, src_rect)
    dst_extent = _rank_extent(direction, dst_rect)
    same_rank = not (dst_extent[1] < src_extent[0] or src_extent[1] < dst_extent[0])
    if same_rank:
        return "same-rank"
    src_center = (src_extent[0] + src_extent[1]) / 2
    dst_center = (dst_extent[0] + dst_extent[1]) / 2
    forward = (dst_center > src_center) == _forward_increasing(direction)
    return "forward" if forward else "back"


def _spread_group_anchors(
    rects: dict[str, BoxRect],
    direction: Direction,
    edges: list[FlowEdge],
    node_by_id: dict[str, "FlowNode"],
    groups: dict[tuple[str, str], list[int]],
    needs_spread,
    other_end,
) -> dict[int, tuple[int, int]]:
    """Shared spreading logic behind :func:`_allocate_edge_anchors`'s two
    passes (source exits, destination entries): for each ``(node_id,
    side)`` group of 2+ edges that share a border side at ``node_id``,
    spread every edge in the group along that side's usable span (see
    :func:`_side_interior_span`) — but only when 2+ of the group's edges
    are ``needs_spread`` (carry an arrow marker on the end at ``node_id``,
    or carry a label — see :func:`_allocate_edge_anchors` for why both
    count as a reason to spread). ``other_end(edge)`` gives the node id at
    the *other* end of an edge, used only to order the spread
    left-to-right/top-to-bottom by where each edge's far endpoint sits
    off-axis, so the spread reads in the same visual order the paths
    already fan out in. Returns a dict keyed by index into ``edges``;
    groups left ungrouped (size < 2) or with fewer than 2 edges needing a
    spread are entirely absent from it.
    """
    overrides: dict[int, tuple[int, int]] = {}
    for (node_id, side), idxs in groups.items():
        if len(idxs) < 2:
            continue
        spreadable = [i for i in idxs if needs_spread(edges[i])]
        if len(spreadable) < 2:
            continue
        rect = rects.get(node_id)
        if rect is None:
            continue
        ordered = sorted(
            idxs, key=lambda i: _abstract(direction, rects[other_end(edges[i])].center)[1]
        )
        lo, hi = _side_span_for_node(node_by_id.get(node_id), rect, side)
        spread = _spread_points(lo, hi, len(ordered))
        for idx, along in zip(ordered, spread):
            overrides[idx] = _side_point(rect, side, along)
    return overrides


def _allocate_edge_anchors(
    rects: dict[str, BoxRect],
    direction: Direction,
    edges: list[FlowEdge],
    nodes: list[FlowNode] | None = None,
) -> tuple[dict[int, tuple[int, int]], dict[int, tuple[int, int]]]:
    """Pre-pass over every edge: group forward/back edges by the border
    side they share with sibling edges at the *same* node, on **both**
    ends independently — exit side at the source (``(src, exit side)`` for
    forward edges, ``(src, lane side)`` for back-edges) and entry side at
    the destination (``(dst, entry side)`` for forward edges, ``(dst, lane
    side)`` for back-edges, since a back-edge's destination anchor is also
    :func:`_lane_anchor`, the same physical side as its source anchor).
    Within each group, spread every edge along that side's usable span
    (see :func:`_side_interior_span`) — but **only** when 2+ of the
    group's edges *need* it at that shared node: either carrying an arrow
    marker on that end, or carrying a label. Both are first-class reasons
    to spread, closing the same underlying defect from two different
    angles: a marker glyph or a label is each something that specific
    anchor cell must render distinctly, and two of either landing on one
    shared cell silently loses all but the last-drawn one (for a label,
    this shows up one step removed — via :func:`_longest_segment`'s
    tie-break picking the same shared segment for two edges rather than
    literally the same cell, but the fix is the same: give each edge its
    own anchor so there is no shared segment/cell left to tie on).

    The marker test is asymmetric between the two ends, deliberately not
    symmetric in *how* it detects one even though the label test is
    shared: an exit group tests ``src_arrow or src_arrow_kind !=
    "default"`` (a source-side arrowhead of any kind is already rare —
    most edges have none — so its mere presence is already a meaningful
    signal), while an entry group tests only ``dst_arrow_kind !=
    "default"`` (a destination-side arrowhead is the *default* for an
    ordinary ``-->`` edge — ``dst_arrow`` is ``True`` almost everywhere —
    so testing its bare presence would spread every ordinary fan-in; only
    a non-default *kind*, the UML composition/aggregation diamond case
    documented in ``mermaid_class.py``, is the actual collision this
    closes). Left stacked on one shared anchor otherwise (the overwhelming
    majority of groups): a plain edge with neither a marker nor a label —
    an ordinary multi-edge fan-out (``A-->B; A-->C``) or fan-in
    (``A-->C; B-->C``) — *relies* on sharing one exit/entry cell for its
    trunk-then-tee look (draw_segment's junction bitmask resolves the
    shared point into a single ┬/┴, not two disjoint stubs); spreading it
    would only change this module's own aesthetic choice of where the fan
    visually splits, not fix anything, and would break that look for
    every existing fan-out/merge golden. Returns a ``(exit_overrides,
    entry_overrides)`` pair, each a dict keyed by index into ``edges``; an
    edge absent from one keeps the engine's single fixed anchor on that
    end (:func:`_forward_exit`/:func:`_forward_entry`/:func:`_lane_anchor`)
    unchanged. Same-rank edges and self-loops are never grouped here —
    same-rank anchors are already per-pair (:func:`_facing_anchor`,
    dynamic per destination, not a fixed shared side), and self-loops
    already stack via their own ``self_loop_counter``-driven reach.
    """
    node_by_id = {n.id: n for n in (nodes or [])}
    exit_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    entry_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, e in enumerate(edges):
        if e.src == e.dst:
            continue
        kind = _classify_edge(rects, direction, e)
        if kind == "forward":
            exit_groups[(e.src, _forward_exit_side(direction))].append(i)
            entry_groups[(e.dst, _forward_entry_side(direction))].append(i)
        elif kind == "back":
            exit_groups[(e.src, _lane_side(direction))].append(i)
            entry_groups[(e.dst, _lane_side(direction))].append(i)
        # "same-rank" / None (dangling): no override, unchanged behavior.

    exit_overrides = _spread_group_anchors(
        rects,
        direction,
        edges,
        node_by_id,
        exit_groups,
        lambda e: e.src_arrow or e.src_arrow_kind != "default" or bool(e.label),
        lambda e: e.dst,
    )
    entry_overrides = _spread_group_anchors(
        rects,
        direction,
        edges,
        node_by_id,
        entry_groups,
        lambda e: e.dst_arrow_kind != "default" or bool(e.label),
        lambda e: e.src,
    )
    return exit_overrides, entry_overrides


def _abstract(direction: Direction, point: tuple[int, int]) -> tuple[int, int]:
    """``point`` decomposed into (primary, secondary) = (rank-axis coord,
    off-axis coord) — the coordinate frame the path-shape helpers reason
    in, direction-agnostically. Inverse: :func:`_real`."""
    x, y = point
    return (x, y) if _rank_is_horizontal(direction) else (y, x)


def _real(direction: Direction, primary: int, secondary: int) -> tuple[int, int]:
    """Inverse of :func:`_abstract`: (primary, secondary) back to real
    ``(x, y)`` canvas coordinates."""
    return (primary, secondary) if _rank_is_horizontal(direction) else (secondary, primary)


def _z_path(
    direction: Direction,
    exit_pt: tuple[int, int],
    entry_pt: tuple[int, int],
    mid_p: int | None = None,
) -> list[tuple[int, int]]:
    """Forward-edge path: a single straight run when both anchors share the
    off-axis coordinate, else a Z/staircase — out of ``exit_pt``, across at
    the jog row/column between the two ranks' facing borders, into
    ``entry_pt``. The jog coordinate defaults to the midpoint of the two
    ranks' facing borders (``(p0 + p1) // 2``), but a caller sharing this
    band with sibling labeled edges (see :func:`_forward_row_overrides`)
    may pass its own ``mid_p`` so each sibling gets a distinct jog row
    instead of every edge crossing the same two ranks stacking their
    labels on the identical row. Passing ``mid_p`` also forces the 4-point
    staircase even when the anchors already share a column/row (``s0 ==
    s1``) — a caller only supplies ``mid_p`` because it specifically wants
    a dedicated jog row for its label, so collapsing to a straight 2-point
    run in that case would defeat the whole point.
    """
    p0, s0 = _abstract(direction, exit_pt)
    p1, s1 = _abstract(direction, entry_pt)
    if s0 == s1 and mid_p is None:
        return [exit_pt, entry_pt]
    m = mid_p if mid_p is not None else (p0 + p1) // 2
    return [exit_pt, _real(direction, m, s0), _real(direction, m, s1), entry_pt]


def _forward_row_overrides(
    rects: dict[str, BoxRect], direction: Direction, edges: list[FlowEdge]
) -> dict[int, int]:
    """Per-edge jog-row (``mid_p``) override for :func:`_z_path`, one entry
    per index into ``edges``, spreading multiple labeled forward edges that
    cross the identical inter-rank band into distinct rows within that
    band's interior, so N labeled edges diverging from (or converging on)
    one node each get their own jog row — and therefore their own label
    row — instead of every edge crossing the same two ranks piling onto
    the shared default midpoint (every edge crossing the same two ranks
    shares that band, see :func:`_rank_gap_overrides`).

    Grouped by an edge's ``(p0, p1)`` band — the *un-overridden*
    :func:`_forward_exit`/:func:`_forward_entry` border rows on the real
    placed rects, which is identical for every edge crossing the same two
    ranks (ranks are top-of-band aligned, see the adapter docstring) — so
    no grandalf rank number needs threading through to the router. Only
    groups of size 2+ get an override; a lone edge through a band is left
    out of the returned dict entirely, so :func:`_z_path` falls through to
    its own default midpoint — the exact value ``_spread_points`` would
    also produce for ``n == 1`` over this same interior span, so skipping
    the group entirely keeps this pass a no-op on every single-label-per-band
    render.

    TB/BT only. In a TB/BT fan-out/fan-in, sibling edges crossing the same
    rank transition default to the *identical* jog row (``_z_path``'s
    ``(p0 + p1) // 2``), so spreading them apart here is what keeps their
    labels off one shared row. In LR/RL the rank axis is horizontal, so
    that same shared band is a jog *column*, and sibling edges diverging
    to (or converging from) distinct secondary rows already write their
    labels on distinct rows by construction — nothing to stack there.
    Forcing a spread in LR/RL would be a real correctness bug: the render
    loop treats any row-overridden forward edge's dedicated jog segment as
    the one to label outright (skipping :func:`_longest_segment`'s
    ordinary tie-break), but for LR/RL that jog segment is the *vertical*
    middle leg of the Z-path, not the horizontal run beside the arrowhead
    that :func:`_longest_segment`'s last-segment tie-break deliberately
    prefers — forcing it would detach the label onto a different row than
    the arrowhead it labels.
    """
    if _rank_is_horizontal(direction):
        return {}
    groups: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, e in enumerate(edges):
        if e.src == e.dst or not e.label:
            continue
        if _classify_edge(rects, direction, e) != "forward":
            continue
        src_rect, dst_rect = rects.get(e.src), rects.get(e.dst)
        if src_rect is None or dst_rect is None:
            continue
        p0, _s0 = _abstract(direction, _forward_exit(direction, src_rect))
        p1, _s1 = _abstract(direction, _forward_entry(direction, dst_rect))
        if p0 == p1:
            continue
        lo, hi = (p0, p1) if p0 <= p1 else (p1, p0)
        groups[(lo, hi)].append(i)

    overrides: dict[int, int] = {}
    for (lo, hi), idxs in groups.items():
        if len(idxs) < 2:
            continue
        rows = _spread_points(lo + 1 + _LABEL_GAP_PAD, hi - 1 - _LABEL_GAP_PAD, len(idxs))
        for idx, row in zip(idxs, rows):
            overrides[idx] = row
    return overrides


def _lane_path(
    direction: Direction,
    exit_pt: tuple[int, int],
    entry_pt: tuple[int, int],
    lane_secondary: int,
) -> list[tuple[int, int]]:
    """Back-edge C-path: out of ``exit_pt`` to the side lane, along the lane,
    back into ``entry_pt`` — never overlaying the forward Z-paths, which
    stay within the involved boxes' own span on this axis."""
    p0, s0 = _abstract(direction, exit_pt)
    p1, s1 = _abstract(direction, entry_pt)
    del s0, s1
    return [
        exit_pt,
        _real(direction, p0, lane_secondary),
        _real(direction, p1, lane_secondary),
        entry_pt,
    ]


def _lane_offsets(
    rects: dict[str, BoxRect], direction: Direction, edges: list[FlowEdge]
) -> dict[int, int]:
    """Per-back-edge lane-column offset (added atop :func:`_lane_secondary_base`),
    one entry per index into ``edges`` — every back-edge gets an entry, in
    ``edges``' own encounter order, the same order a plain incrementing
    counter would have assigned lanes.

    Consecutive lanes step apart by ``_LANE_GAP`` by default, but the step
    widens when either edge of the pair carries a label wide enough that
    its centered text (see :func:`_draw_label_on_segment`'s vertical
    branch, which centers a lane label on its own lane column) would
    otherwise reach across the gap into the neighboring lane's column with
    no buffer cell left between the two — the vertical-segment analogue of
    :func:`_rank_gap_overrides` widening a rank gap for a labeled forward
    edge's own text. Two back-edges with no labels at all (or labels short
    enough to fit in the default gap) reproduce the original fixed-step
    spacing exactly.
    """
    offsets: dict[int, int] = {}
    prev_half = 0
    total = 0
    seen_any = False
    for i, e in enumerate(edges):
        if e.src == e.dst:
            continue
        if _classify_edge(rects, direction, e) != "back":
            continue
        half = visual_len(e.label) // 2 + 1 if e.label else 0
        if seen_any:
            total += max(_LANE_GAP, prev_half + half + 1)
        offsets[i] = total
        prev_half = half
        seen_any = True
    return offsets


def _lane_secondary_base(direction: Direction, rects: dict[str, BoxRect]) -> int:
    """Starting side-lane coordinate just past *every* placed node's far
    edge on the off-axis — the base that :func:`_route_edge_path` adds
    ``_LANE_MARGIN + lane_offset`` (see :func:`_lane_offsets`) to, per
    back-edge, to avoid stacking lanes.

    Scoped to the whole graph's rects, not just the one back-edge's own
    ``src``/``dst`` boxes: a back-edge's C-path runs its exit/entry legs
    along its own src/dst boxes' own rank-band rows (the off-axis-*rank*
    coordinate — the primary axis here is the off-axis, not the rank axis;
    see :func:`_abstract`), which any sibling node sharing that same band
    (every other node in the same rank) also occupies. Basing the lane on
    only the edge's own two boxes leaves the lane column short of a wider
    sibling in that rank, so the C-path's own corner would land inside —
    or its legs would sweep across — that sibling's box. Since every
    back-edge already shares one global lane-offset sequence (see
    :func:`_lane_offsets`, stacking lanes across the *whole* diagram, not
    per edge pair), reaching past the whole diagram's own far edge here is
    the same scope the stacking mechanism already assumes, not a new
    one."""
    if not rects:
        return 0
    if _rank_is_horizontal(direction):
        return max(r.y + r.h - 1 for r in rects.values())
    return max(r.x + r.w - 1 for r in rects.values())


def _segment_length(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _longest_segment(
    points: list[tuple[int, int]],
) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """The longest straight run in a polyline — where an edge label is
    centered. Ties break toward the *last* (furthest downstream) segment
    rather than the first. This matters specifically for a forward Z-path
    out of a node with 2+ outgoing edges: its first segment is the shared
    exit-side run common to every sibling edge leaving that node (see
    :func:`_allocate_edge_anchors`'s docstring), so on a tie it is the one
    segment guaranteed to collide with a sibling's own label. Preferring
    the last segment picks each edge's own distinguishing run near its
    destination instead — routine in LR/RL, where a node's shared fan-out
    run and its per-branch runs often measure the same few cells (TB
    rarely ties here at all: its branch runs are typically much longer
    than the shared trunk, so this tie-break is moot there and every
    existing TB/back-edge/self-loop golden is unaffected — see this
    module's test suite for the confirming corpus)."""
    segments = list(zip(points, points[1:]))
    if not segments:
        return None
    best = segments[0]
    best_len = _segment_length(*best)
    for seg in segments[1:]:
        length = _segment_length(*seg)
        if length >= best_len:
            best = seg
            best_len = length
    return best


def _label_positions(length: int, center: int, lo: int, hi: int) -> list[int]:
    """Candidate run-start offsets, nearest-``center`` first, for a run of
    ``length`` cells that fits entirely within ``[lo, hi]`` — how a label
    shifts off a reserved cell to the nearest clear run along its segment.
    A candidate is a *start* offset, so the valid range for one is
    ``[lo, hi - length + 1]``, not ``[lo, hi]`` itself: a start any later
    than that would spill the run's tail past ``hi`` — e.g. onto whatever
    real wall (a box border, a segment's own arrowhead-adjacent endpoint)
    is the very thing ``hi`` was computed to stay clear of. When the span
    is narrower than ``length`` altogether, no start can avoid spilling,
    so this falls back to ``lo`` alone (the caller's overflow-tolerated
    path handles writing past the end from there).
    """
    if hi - lo + 1 < length:
        return []
    lo_start, hi_start = lo, hi - length + 1
    ideal = max(lo_start, min(center - length // 2, hi_start))
    span = hi_start - lo_start + 1
    order = [ideal]
    seen = {ideal}
    for d in range(1, span + 1):
        for cand in (ideal + d, ideal - d):
            if cand not in seen and lo_start <= cand <= hi_start:
                order.append(cand)
                seen.add(cand)
    return order


def _reserve_label_margin(canvas: Canvas, x: int, y: int) -> None:
    """Mark one cell just past a label's edge as reserved, without
    altering whatever character (if any) already occupies it — a one-cell
    buffer so a second label placed on an adjacent/overlapping segment
    (e.g. two back-edge labels sharing a row) lands with visible separation
    instead of butting directly up against the first label's text."""
    if x < 0 or y < 0:
        return
    canvas.set_char(x, y, canvas.get_char(x, y), reserve=True)


def _label_cell_widths(label: str) -> list[int]:
    """Per-character visual width of ``label``, as successive
    :func:`~termrender.style.visual_len` prefix deltas — a wide
    CJK/fullwidth character reports ``2`` here without this module
    needing to duplicate ``visual_len``'s own east-asian-width table (the
    deltas telescope to ``visual_len(label)`` by construction, so this
    always agrees with the total cell count :func:`_draw_label_on_segment`
    already reserves for the label)."""
    widths = []
    prev = 0
    for i in range(1, len(label) + 1):
        cur = visual_len(label[: i])
        widths.append(cur - prev)
        prev = cur
    return widths


def _write_label_run(
    canvas: Canvas, start: int, row: int, label: str, check_reserved: bool
) -> None:
    """Write ``label`` into row ``row`` starting at column ``start``,
    advancing the write cursor by each character's own visual width (see
    :func:`_label_cell_widths`) instead of one grid cell per Python code
    point. A single-width character still occupies just its one cell; a
    wide CJK/fullwidth character's glyph lands in its first cell only,
    and the *next* cell it visually covers is marked reserved and left
    blank — without this, that second cell stays unreserved and a
    connector glyph drawn earlier (edges draw before labels, see
    :func:`layout_flowgraph`) remains visible inside the label's own
    visual width. ``check_reserved`` mirrors the two call sites' existing
    behavior: the "clear run found" placement writes unconditionally (the
    whole run was already verified clear by the caller), the
    overflow-tolerated fallback placement instead skips any individual
    cell that's already reserved, one cell at a time (never overwriting a
    box).
    """
    x = start
    for ch, w in zip(label, _label_cell_widths(label)):
        if not check_reserved or not canvas.is_reserved(x, row):
            canvas.set_char(x, row, ch, reserve=True)
        for extra in range(1, w):
            cx = x + extra
            if not check_reserved or not canvas.is_reserved(cx, row):
                canvas.set_char(cx, row, "", reserve=True)
        x += w


_LABEL_SCAN_CAP = 400  # generous bound on how far a label's clear-run search
                       # scans a row outward from its ideal center before
                       # giving up on widening — large enough to cross an
                       # entire small-to-medium (<=20 node) diagram's blank
                       # inter-rank gap, cheap enough to never matter for
                       # performance at that scale.


def _segment_cells(a: tuple[int, int], b: tuple[int, int]) -> frozenset[tuple[int, int]]:
    """Every cell on the straight run ``a``-``b`` (inclusive) — the set a
    label placement search exempts from :func:`_cell_blocks_label`'s
    occupied test, since that line belongs to the very edge being labeled
    and is expected to be overwritten by its own label (the normal
    ``───label───`` look), not treated as a collision the way a passing
    *sibling* edge's line is.
    """
    (x0, y0), (x1, y1) = a, b
    if x0 == x1:
        lo, hi = (y0, y1) if y0 <= y1 else (y1, y0)
        return frozenset((x0, y) for y in range(lo, hi + 1))
    lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
    return frozenset((x, y0) for x in range(lo, hi + 1))


def _cell_blocks_label(
    canvas: Canvas, x: int, y: int, own_cells: frozenset[tuple[int, int]]
) -> bool:
    """True when ``(x, y)`` should block a label's placement search:
    either formally reserved (a box border/interior, a subgraph frame
    title, an already-placed label) or already carrying a drawn
    connector-line/arrowhead glyph from some *other* edge. Line-drawing
    cells are never marked reserved (:class:`Canvas` reserves only for
    routing safety, not visual occupancy — a line may cross another
    line's cell freely), so without this a label's clear-run search would
    consider a passing sibling edge's ``│``/``─`` invisible and land
    flush against — or straight through — it: the same fused-label defect
    this router closes for box borders, just against a line instead of a
    border. ``own_cells`` (see :func:`_segment_cells`) exempts the label's
    own edge's own path, which is expected to be overwritten by its own
    label, not avoided.
    """
    if (x, y) in own_cells:
        return False
    return canvas.is_reserved(x, y) or canvas.get_char(x, y) != " "


def _row_clear_span(
    row: int, near_x: int, blocked: Callable[[int, int], bool]
) -> tuple[int, int]:
    """The maximal blank run on ``row`` reachable from ``near_x`` without
    crossing a cell ``blocked`` (see :func:`_cell_blocks_label`) considers
    occupied — a box border, a subgraph frame title, an already-placed
    label, or a sibling edge's already-drawn connector line — with a
    mandatory 1-cell buffer kept from whichever blocked cell actually
    stopped the scan (no buffer needed against the canvas's own edge).
    This is what lets :func:`_draw_label_on_segment` size its horizontal
    search window to the row's *real* available space instead of the
    width of whichever jog segment the label's own edge happens to travel
    through. At a labeled junction where several edges converge/diverge on
    one node, each edge's own Z/C-path jog can be just a few cells long
    (its exit/entry columns sit close together), far shorter than its
    label's text, while the row itself — blank across the whole inter-rank
    gap or side lane by construction — has far more room than that one
    edge's own short segment implies. Sizing the search window to the
    row's real clear span keeps a label wider than its own segment from
    overflowing straight through a sibling's already-placed label or line
    (fused text, or text flush against a connector) or landing flush
    against a box border with no separating cell (a label fused to the
    node's own text).

    Prefers a full blank-column buffer against a genuinely blocked
    neighbor (not merely "don't overwrite it") when the crowd leaves room
    to spare for one — a label read flush against a passing connector
    line (``│closed│``, no separating cell) is exactly as unreadable as
    one fused to a box border, so "blocked" alone isn't a strict enough
    stopping rule on its own. Falls back to the tighter touching span only
    when the crowd leaves no spare room at all, rather than shrinking the
    window below what the label itself needs.
    """
    left = near_x
    steps = 0
    while left > 0 and not blocked(left - 1, row) and steps < _LABEL_SCAN_CAP:
        left -= 1
        steps += 1
    left_blocked = left > 0 and blocked(left - 1, row)
    right = near_x
    steps = 0
    while not blocked(right + 1, row) and steps < _LABEL_SCAN_CAP:
        right += 1
        steps += 1
    right_blocked = blocked(right + 1, row)
    # left/right are each already the touching boundary (adjacent to
    # whichever blocked cell stopped the scan, zero gap): shifting each
    # one exactly one more cell out gives the buffered boundary. The shift
    # is applied only here, once, so the buffer stays exactly one cell —
    # the search window a tightly fitting label needs is the touching
    # span widened by one, no more.
    buffered_left = left + 1 if left_blocked else left
    buffered_right = right - 1 if right_blocked else right
    if buffered_left <= buffered_right:
        return buffered_left, buffered_right
    return left, right


def _draw_label_on_segment(
    canvas: Canvas,
    a: tuple[int, int],
    b: tuple[int, int],
    label: str,
    path_ends: tuple[tuple[int, int], tuple[int, int]] | None = None,
) -> None:
    """Center ``label`` on the straight run ``a``-``b``. A label always
    *reads* horizontally (measured with :func:`visual_len`): on a
    horizontal segment it centers along the segment's own x-span at the
    segment's row — but the *search window* for where along that row it
    may land is the row's real clear span (:func:`_row_clear_span`), not
    the segment's own two endpoints, since a short jog can be much
    narrower than its label's text (see that function's docstring); on a
    vertical segment (e.g. a back-edge's side lane) it still reads
    horizontally, centered on the segment's column, at a row chosen from
    the segment's y-span — matching the sequence renderer's self-loop
    label placement. Shifts along the search axis to the nearest span/row
    fully clear of a blocked cell — a box, a subgraph frame title, an
    already-placed label, or a sibling edge's already-drawn connector line
    (see :func:`_cell_blocks_label`); the label's own edge's own line is
    exempted (:func:`_segment_cells`), since overwriting it is the whole
    point of labeling it. If no clear run exists, writes at the ideal
    placement anyway (overflow tolerated) but skips individual reserved
    cells — a label never corrupts a box. Every written label cell is
    itself marked reserved (see :func:`layout_flowgraph`'s two-pass draw
    order): labels draw only after every edge's line+arrowheads are already
    on the canvas, so nothing draws over a label afterwards, and a *later*
    label's own clear-run search treats an earlier label's cells the same
    as a box's — skip, don't overwrite.

    ``path_ends`` (the labeled edge's overall first and last point, i.e.
    ``points[0]``/``points[-1]`` of its full routed path, not just this one
    segment's own two endpoints) tells the endpoint-buffer treatment below
    which of ``a``/``b`` — if either — is a genuine interior bend rather
    than the edge's own exit/entry anchor. An anchor is where an arrowhead
    lands (or a source marker sits), and the "label▶"/"◀label" convention
    specifically wants a label flush against *that*; only a mid-path
    corner, where the line turns but doesn't terminate, reads as fused
    when a label butts against it with no separating cell.
    """
    length = visual_len(label)
    if length <= 0:
        return
    (x0, y0), (x1, y1) = a, b
    # Two predicates, not one, because a segment's own two endpoints play
    # two different roles. ``loose`` (every cell of the segment, corners
    # included, exempt) is what the *scan* — measuring how far the row's
    # real clear space actually reaches — must use: on a Z/C-path jog
    # segment those endpoints are the path's own right-angle bends into a
    # perpendicular leg, not a real wall, so a scan that stopped there
    # would under-measure the row's true available room whenever the jog
    # itself is short (the very case this whole mechanism exists for).
    # ``strict`` is what *placement* prefers: it additionally treats a
    # small buffer zone hugging each endpoint (the corner cell itself plus
    # its immediate left/right neighbor on the same row) as blocked,
    # regardless of which side of the corner a candidate run approaches
    # from — a label run landing exactly flush against its own bend, with
    # no separating cell, reads exactly as fused as landing flush against
    # a foreign line, even though the glyph belongs to the same edge,
    # so "one cell short of the corner" isn't enough either; the
    # placement search needs a real gap on both possible sides. Try strict
    # first — it wins whenever the (loose-measured) window has room to
    # spare for the buffer — and only fall back to loose when the window
    # is so tight the label needs every last cell, corners included.
    # An endpoint that is also the edge's own overall exit/entry anchor
    # (see ``path_ends``) is excluded from this buffer entirely — it is
    # where an arrowhead lands, not a mid-path bend, and "label▶" flush
    # against it is the normal, wanted look, not a fused-looking defect.
    own_cells = _segment_cells(a, b)
    bend_corners = (a, b) if path_ends is None else tuple(
        p for p in (a, b) if p not in path_ends
    )
    endpoint_buffer = frozenset(
        (cx + dx, cy) for cx, cy in bend_corners for dx in (-1, 0, 1)
    )

    def loose_blocked(x: int, y: int) -> bool:
        return _cell_blocks_label(canvas, x, y, own_cells)

    def strict_blocked(x: int, y: int) -> bool:
        if (x, y) in endpoint_buffer:
            return True
        return _cell_blocks_label(canvas, x, y, own_cells)

    if y0 == y1:
        # Horizontal segment: search along x for a clear run at row y0,
        # widened to the row's real clear span (see _row_clear_span).
        seg_lo, seg_hi = (x0, x1) if x0 <= x1 else (x1, x0)
        row = y0
        center = (seg_lo + seg_hi) // 2
        lo, hi = _row_clear_span(row, center, loose_blocked)
        # strict's search window matches the widened [lo, hi] only when
        # *both* of this segment's endpoints are genuine interior bends
        # (see path_ends above) — that's the case the widening exists for
        # (Problem 1: a short jog far shorter than its own label, needing
        # the row's real floor space to find a bend-avoiding spot at all).
        # When either endpoint is instead the edge's own exit/entry anchor,
        # widening strict's search the same way lets it wander away from
        # that anchor into unrelated floor space back toward the segment's
        # far end — wrong specifically because that anchor (an arrowhead,
        # typically) is exactly what the label should stay adjacent to,
        # so strict is scoped to the segment's own natural extent there
        # instead; loose always keeps the full widened window regardless,
        # since it's the fallback tier that exists to use that extra room.
        if len(bend_corners) == 2:
            strict_lo, strict_hi = lo, hi
        else:
            strict_lo, strict_hi = max(lo, seg_lo), min(hi, seg_hi)

        def cells(start: int) -> list[tuple[int, int]]:
            return [(start + i, row) for i in range(length)]

        for check, w_lo, w_hi in (
            (strict_blocked, strict_lo, strict_hi),
            (loose_blocked, lo, hi),
        ):
            for start in _label_positions(length, center, w_lo, w_hi):
                run = cells(start)
                if not any(check(x, y) for x, y in run):
                    _write_label_run(canvas, start, row, label, check_reserved=False)
                    _reserve_label_margin(canvas, start - 1, row)
                    _reserve_label_margin(canvas, start + length, row)
                    return
        start = max(lo, min(center - length // 2, hi - length + 1))
        _write_label_run(canvas, start, row, label, check_reserved=True)
        return

    # Vertical segment: the label still reads horizontally, centered on
    # column x0 — unlike the horizontal branch, the column never shifts;
    # only which *row* it lands on is searched, so the label always stays
    # visually anchored beside the vertical line it labels (e.g. flush
    # after an LR forward edge's arrowhead) instead of sliding sideways
    # into whatever row happens to have the most open floor space. The
    # row search never strays outside the segment's own [lo, hi] y-span:
    # a row off that span isn't even on this edge's own path, so a
    # crowded column (every candidate row blocked by some sibling edge's
    # crossing line) falls through to the best-effort pick below instead
    # of wandering into blank rows elsewhere on the canvas, possibly far
    # below the whole diagram.
    lo, hi = (y0, y1) if y0 <= y1 else (y1, y0)
    col = x0
    start_x = max(0, col - length // 2)

    def row_cells(row: int) -> list[tuple[int, int]]:
        return [(start_x + i, row) for i in range(length)]

    def buffered_row_cells(row: int) -> list[tuple[int, int]]:
        # The label's own cells plus one buffer cell each side — the same
        # "don't butt flush against a foreign line" discipline the
        # horizontal branch gets for free from _row_clear_span's buffered
        # window (see that function's docstring): two back-edges' lane
        # columns can sit only _LANE_GAP cells apart, close enough that an
        # unbuffered row search would happily land one label's edge
        # directly against the neighboring lane's connector line.
        return [(start_x - 1, row), *row_cells(row), (start_x + length, row)]

    def find_row(cells_fn: Callable[[int], list[tuple[int, int]]]) -> int | None:
        for check in (strict_blocked, loose_blocked):
            for row in candidates:
                if not any(check(x, y) for x, y in cells_fn(row)):
                    return row
        return None

    center_row = (lo + hi) // 2
    candidates = _label_positions(1, center_row, lo, hi)
    # Prefer a row with the buffer cells clear too; fall back to a row
    # that's merely not overlapping the label's own cells when the column
    # is crowded enough that no row has buffer room to spare — mirrors
    # _row_clear_span's own buffered-vs-touching fallback.
    row = find_row(buffered_row_cells)
    if row is None:
        row = find_row(row_cells)
    if row is not None:
        _write_label_run(canvas, start_x, row, label, check_reserved=False)
        _reserve_label_margin(canvas, start_x - 1, row)
        _reserve_label_margin(canvas, start_x + length, row)
        return
    # No row within the segment's own span was fully clear even under the
    # loose check — pick whichever row has the fewest blocked cells
    # (best effort) and write there, skipping only genuinely reserved
    # cells, rather than overflowing past the segment's own span into
    # unrelated territory below/above the whole diagram.
    best_row = min(
        candidates,
        key=lambda row: sum(1 for x, y in row_cells(row) if loose_blocked(x, y)),
    )
    _write_label_run(canvas, start_x, best_row, label, check_reserved=True)


def _draw_polyline(canvas: Canvas, points: list[tuple[int, int]], style: EdgeStyle) -> None:
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        canvas.draw_segment(x0, y0, x1, y1, style)


def _draw_arrowheads(canvas: Canvas, points: list[tuple[int, int]], edge: FlowEdge) -> None:
    if edge.dst_arrow:
        canvas.draw_glyph(
            *points[-1], _arrow_glyph(points[-2], points[-1], edge.dst_arrow_kind)
        )
    if edge.src_arrow:
        canvas.draw_glyph(
            *points[0], _arrow_glyph(points[1], points[0], edge.src_arrow_kind)
        )


def _self_loop_points(
    direction: Direction, rect: BoxRect, lane: int
) -> list[tuple[int, int]]:
    """A small loop off the box's lane side — the flowchart analogue of the
    sequence renderer's self-message loop (``_self_loop_rows``). Uses the
    box's *full* border range (corners included) rather than only interior
    rows/columns so it stays correct even at ``_MIN_BOX_W``/``_MIN_BOX_H``,
    where there is only one interior row/column to work with."""
    reach = _LOOP_REACH + lane * 2
    ax, ay = _lane_anchor(direction, rect)
    if _rank_is_horizontal(direction):
        full_lo, full_hi = rect.x, rect.x + rect.w - 1
        lo = max(full_lo, ax - 1)
        hi = min(full_hi, ax + 1)
        if hi <= lo:
            hi = min(full_hi, lo + 1)
        if hi <= lo:
            lo = max(full_lo, hi - 1)
        far = ay + reach
        return [(lo, ay), (lo, far), (hi, far), (hi, ay)]
    full_lo, full_hi = rect.y, rect.y + rect.h - 1
    lo = max(full_lo, ay - 1)
    hi = min(full_hi, ay + 1)
    if hi <= lo:
        hi = min(full_hi, lo + 1)
    if hi <= lo:
        lo = max(full_lo, hi - 1)
    far = ax + reach
    return [(ax, lo), (far, lo), (far, hi), (ax, hi)]


def _route_edge_path(
    rects: dict[str, BoxRect],
    direction: Direction,
    edge: FlowEdge,
    self_loop_counter: dict[str, int],
    exit_anchor: tuple[int, int] | None = None,
    entry_anchor: tuple[int, int] | None = None,
    mid_p: int | None = None,
    lane_offset: int = 0,
) -> list[tuple[int, int]] | None:
    """Compute one edge's polyline points: anchors chosen by relative rank
    position, an L/Z/C path shape. Pure path computation only — drawing is
    the caller's job, split into two passes across *all* edges (see
    :func:`layout_flowgraph`) so that no edge's line ever overwrites
    another edge's already-placed label. Dangling node-id references
    return ``None`` (defensive no-op — the parser guarantees valid
    endpoints; this module never crashes on one).

    ``exit_anchor``/``entry_anchor``, when given (from
    :func:`_allocate_edge_anchors`), replace the src/dst border point that
    would otherwise come from :func:`_forward_exit`/:func:`_forward_entry`/
    :func:`_lane_anchor` — used only when this edge's exit/entry side is
    shared with a sibling edge that also carries an arrow marker on that
    same end; ``None`` (the overwhelming common case, for either) reproduces
    the original single-anchor behavior exactly on that end. ``mid_p``
    (from :func:`_forward_row_overrides`), forwarded only on the
    ``"forward"`` branch, gives this edge's own jog row/column instead of
    :func:`_z_path`'s shared-band default — used when this edge's inter-
    rank band is shared with 2+ sibling labeled edges. ``lane_offset``
    (from :func:`_lane_offsets`), used only on the back-edge branch, gives
    this edge's own lane-column offset instead of a plain per-edge
    increment — spacing stacked back-edge lanes apart by label width, not
    just a fixed step. Same-rank edges and self-loops ignore all four (see
    :func:`_allocate_edge_anchors`'s docstring for why).
    """
    src_rect = rects.get(edge.src)
    dst_rect = rects.get(edge.dst)
    if src_rect is None or dst_rect is None:
        return None

    if edge.src == edge.dst:
        lane = self_loop_counter.get(edge.src, 0)
        self_loop_counter[edge.src] = lane + 1
        return _self_loop_points(direction, src_rect, lane)

    kind = _classify_edge(rects, direction, edge)

    if kind == "same-rank":
        return [_facing_anchor(src_rect, dst_rect), _facing_anchor(dst_rect, src_rect)]

    if kind == "forward":
        exit_pt = exit_anchor if exit_anchor is not None else _forward_exit(direction, src_rect)
        entry_pt = entry_anchor if entry_anchor is not None else _forward_entry(direction, dst_rect)
        return _z_path(direction, exit_pt, entry_pt, mid_p=mid_p)

    lane_secondary = _lane_secondary_base(direction, rects) + _LANE_MARGIN + lane_offset
    exit_pt = exit_anchor if exit_anchor is not None else _lane_anchor(direction, src_rect)
    entry_pt = entry_anchor if entry_anchor is not None else _lane_anchor(direction, dst_rect)
    return _lane_path(direction, exit_pt, entry_pt, lane_secondary)


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
        node_subgraph = _node_subgraph_map(g.subgraphs)
        rects = _place_nodes(g.nodes, g.edges, g.direction, node_subgraph)
        if not rects:
            return []

        frames = _collect_frames(g.subgraphs, rects)

        # A frame's padding can push its top-left corner negative even
        # though every node rect is already non-negative (_place_nodes'
        # own normalization only accounts for node boxes) — shift
        # everything together so the canvas never has to address a
        # negative coordinate (which Canvas silently drops).
        min_x = min([r.x for r in rects.values()] + [fr.x for fr, _ in frames])
        min_y = min([r.y for r in rects.values()] + [fr.y for fr, _ in frames])
        shift_x = -min_x if min_x < 0 else 0
        shift_y = -min_y if min_y < 0 else 0
        if shift_x or shift_y:
            rects = {
                node_id: BoxRect(x=r.x + shift_x, y=r.y + shift_y, w=r.w, h=r.h)
                for node_id, r in rects.items()
            }
            frames = [
                (BoxRect(x=fr.x + shift_x, y=fr.y + shift_y, w=fr.w, h=fr.h), title)
                for fr, title in frames
            ]

        max_x = max([r.x + r.w for r in rects.values()] + [fr.x + fr.w for fr, _ in frames])
        max_y = max([r.y + r.h for r in rects.values()] + [fr.y + fr.h for fr, _ in frames])
        canvas = Canvas(max_x, max_y)

        # Frames first (behind), then boxes, then edges — a subgraph
        # enclosure never reserves cells, so nodes/edges draw over it
        # freely; node boxes reserve their cells so the router avoids them.
        for frame_rect, title in frames:
            canvas.draw_frame(frame_rect, title)
        for n in g.nodes:
            rect = rects.get(n.id)
            if rect is not None:
                canvas.draw_box(rect, n.shape, n.label, n.compartments)
        # Two passes across *all* edges, not one pass per edge: every
        # edge's line + arrowheads draw first, then every edge's label
        # draws last (see design doc). Interleaving line-then-label per
        # edge would let a later edge's line silently erase an earlier
        # edge's already-placed label whenever their paths shared a cell —
        # labels are only ever safe once no more lines are coming.
        self_loop_counter: dict[str, int] = {}
        exit_overrides, entry_overrides = _allocate_edge_anchors(
            rects, g.direction, g.edges, g.nodes
        )
        row_overrides = _forward_row_overrides(rects, g.direction, g.edges)
        lane_offsets = _lane_offsets(rects, g.direction, g.edges)
        edge_paths: list[tuple[int, FlowEdge, list[tuple[int, int]]]] = []
        for i, e in enumerate(g.edges):
            points = _route_edge_path(
                rects,
                g.direction,
                e,
                self_loop_counter,
                exit_overrides.get(i),
                entry_overrides.get(i),
                row_overrides.get(i),
                lane_offsets.get(i, 0),
            )
            if points is not None:
                edge_paths.append((i, e, points))
        for _i, e, points in edge_paths:
            _draw_polyline(canvas, points, e.style)
            _draw_arrowheads(canvas, points, e)
        for i, e, points in edge_paths:
            if not e.label:
                continue
            # A row-stacked forward edge (see _forward_row_overrides) was
            # given its own dedicated jog row specifically so its label
            # would land there — but _longest_segment picks by raw length,
            # and the z-path's *exit* leg (rank-axis run from the box out
            # to the jog row) can measure longer than the jog itself once
            # the jog is pushed toward one end of a widened, multi-edge
            # band, which would silently defeat the whole point of
            # stacking. Skip the length comparison for these edges and
            # address the jog segment (points[1]-points[2] of _z_path's
            # 4-point staircase) directly; every other edge keeps today's
            # longest-run selection unchanged.
            #
            # A back-edge's C-path (see _lane_path) gets the identical
            # treatment for a different reason: its exit/entry legs travel
            # along its own src/dst boxes' rank-band rows, which every
            # sibling node sharing that band also occupies, so a crowded
            # rank can make one of those legs measure longer than the
            # lane's own dedicated middle segment even though the legs
            # aren't genuinely open floor space the way the lane column is
            # (the lane sits past every node's own far edge — see
            # _lane_secondary_base). Raw-length comparison would then pick
            # a leg that merely *looks* long on paper, landing the label
            # beside — or on top of — whichever sibling boxes that leg
            # happens to run alongside. The lane's own middle segment is
            # always the one guaranteed clear of every node in the graph,
            # so a back-edge always addresses it directly, the same way a
            # row-stacked forward edge always addresses its own jog row.
            if i in row_overrides and len(points) == 4:
                seg = (points[1], points[2])
            elif len(points) == 4 and _classify_edge(rects, g.direction, e) == "back":
                seg = (points[1], points[2])
            else:
                seg = _longest_segment(points)
            if seg is not None:
                _draw_label_on_segment(
                    canvas, *seg, e.label, path_ends=(points[0], points[-1])
                )
        return canvas.to_lines()
    except Exception:
        return []
