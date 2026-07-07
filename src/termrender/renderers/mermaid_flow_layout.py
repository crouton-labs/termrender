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
the two anchors already share a column/row, else a Z/staircase through the
midpoint of the clear inter-rank band. Arrowheads (``▼▲▶◀``) are chosen from
the final segment's direction of travel and overwrite the border cell they
land on. Edge labels center on the path's longest straight run, shifting
along it to the nearest cell span clear of any box if the ideal midpoint
lands on one. Self-loops (``src == dst``, excluded from the grandalf graph)
draw a small loop off the same side used for back-edge lanes, stacking
outward per repeated self-loop on one node.

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

    def draw_box(self, rect: "BoxRect", shape: NodeShape, label: str) -> None:
        """Draw a bordered box + centered wrapped label; reserve every cell.

        Dispatches to a shape-specific border drawer. Every drawer reserves
        the *entire* bounding ``rect`` (border, interior, and any blank
        corner cells outside a non-rectangular outline, e.g. a diamond's
        tapered corners) so the router always treats the shape's full
        bounding box as impassable — a deliberate over-reservation that
        keeps every shape's anchor points (``top_mid``/``bottom_mid``/etc.,
        defined on the bounding rect) meaningful and keeps routing safety
        independent of each shape's exact visual outline.
        """
        if rect.w <= 0 or rect.h <= 0:
            return
        drawer = _SHAPE_DRAWERS.get(shape, Canvas._draw_rect)
        drawer(self, rect, label or "")

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
                     # when it forces a rank-band gap wider than _ROW_GAP.


def _rank_gap_overrides(
    edges: list[FlowEdge], rank_of: dict[str, int]
) -> dict[int, int]:
    """Minimum inter-rank-band gap keyed by the *lower* rank of each
    adjacent-rank transition, widened past ``_ROW_GAP`` wherever a labeled
    edge directly connects that transition's two ranks. A forward edge
    between adjacent ranks routes as a single straight run (or a Z path
    that still crosses the same inter-rank band) whose only clear space is
    this gap — at the base ``_ROW_GAP`` a label wider than a couple of
    cells has nowhere to go but onto the boxes it connects, which is
    exactly the short LR/adjacent-rank clipped-label bug this closes.
    Non-adjacent-rank edges (back-edges, multi-rank spans) don't constrain
    the gap here — they route through their own side lane, not this band.
    """
    overrides: dict[int, int] = {}
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
        needed = visual_len(e.label) + 2 * _LABEL_GAP_PAD
        overrides[lo_r] = max(overrides.get(lo_r, _ROW_GAP), needed)
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
    dims = {n.id: _box_dims(n.label, n.shape) for n in nodes}
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
        gap_overrides = _rank_gap_overrides(edges, rank_of)

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


def _arrow_glyph(frm: tuple[int, int], to: tuple[int, int]) -> str:
    """``▼▲▶◀`` for the direction of travel from ``frm`` to ``to`` — the
    glyph an arrowhead landing at ``to`` should show."""
    dx, dy = to[0] - frm[0], to[1] - frm[1]
    if dx == 0 and dy == 0:
        return _ARROW_GLYPHS[(0, 1)]
    if abs(dx) >= abs(dy):
        return _ARROW_GLYPHS[(1 if dx > 0 else -1, 0)]
    return _ARROW_GLYPHS[(0, 1 if dy > 0 else -1)]


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
    direction: Direction, exit_pt: tuple[int, int], entry_pt: tuple[int, int]
) -> list[tuple[int, int]]:
    """Forward-edge path: a single straight run when both anchors share the
    off-axis coordinate, else a Z/staircase — out of ``exit_pt``, across at
    the midpoint between the two ranks' facing borders, into ``entry_pt``."""
    p0, s0 = _abstract(direction, exit_pt)
    p1, s1 = _abstract(direction, entry_pt)
    if s0 == s1:
        return [exit_pt, entry_pt]
    mid_p = (p0 + p1) // 2
    return [exit_pt, _real(direction, mid_p, s0), _real(direction, mid_p, s1), entry_pt]


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


def _lane_secondary_base(direction: Direction, a: BoxRect, b: BoxRect) -> int:
    """Starting side-lane coordinate just past the two involved boxes' far
    edge on the off-axis — the base that :func:`_route_edge` adds
    ``_LANE_MARGIN + lane * _LANE_GAP`` to, per back-edge, to avoid stacking
    lanes."""
    if _rank_is_horizontal(direction):
        return max(a.y + a.h - 1, b.y + b.h - 1)
    return max(a.x + a.w - 1, b.x + b.w - 1)


def _segment_length(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _longest_segment(
    points: list[tuple[int, int]],
) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """The longest straight run in a polyline — where an edge label is
    centered."""
    segments = list(zip(points, points[1:]))
    if not segments:
        return None
    return max(segments, key=lambda seg: _segment_length(*seg))


def _label_positions(length: int, center: int, lo: int, hi: int) -> list[int]:
    """Candidate run-start offsets within ``[lo, hi]``, nearest-``center``
    first — how a label shifts off a reserved cell to the nearest clear
    run along its segment."""
    span = max(hi - lo + 1, 1)
    if hi - lo + 1 >= length:
        ideal = max(lo, min(center - length // 2, hi - length + 1))
    else:
        ideal = lo
    order = [ideal]
    seen = {ideal}
    for d in range(1, span + 1):
        for cand in (ideal + d, ideal - d):
            if cand not in seen:
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


def _draw_label_on_segment(
    canvas: Canvas, a: tuple[int, int], b: tuple[int, int], label: str
) -> None:
    """Center ``label`` on the straight run ``a``-``b``. A label always
    *reads* horizontally (measured with :func:`visual_len`): on a
    horizontal segment it centers along the segment's own x-span at the
    segment's row; on a vertical segment (e.g. a back-edge's side lane) it
    still reads horizontally, centered on the segment's column, at a row
    chosen from the segment's y-span — matching the sequence renderer's
    self-loop label placement. Shifts along the search axis to the nearest
    span/row fully clear of a reserved (box) cell; if none exists, writes
    at the ideal placement anyway (overflow tolerated) but skips individual
    reserved cells — a label never corrupts a box. Every written label cell
    is itself marked reserved (see :func:`layout_flowgraph`'s two-pass draw
    order): labels draw only after every edge's line+arrowheads are already
    on the canvas, so nothing draws over a label afterwards, and a *later*
    label's own clear-run search treats an earlier label's cells the same
    as a box's — skip, don't overwrite.
    """
    length = visual_len(label)
    if length <= 0:
        return
    (x0, y0), (x1, y1) = a, b

    if y0 == y1:
        # Horizontal segment: search along x for a clear run at row y0.
        lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
        row = y0
        center = (lo + hi) // 2

        def cells(start: int) -> list[tuple[int, int]]:
            return [(start + i, row) for i in range(length)]

        for start in _label_positions(length, center, lo, hi):
            run = cells(start)
            if not any(canvas.is_reserved(x, y) for x, y in run):
                for (px, py), ch in zip(run, label):
                    canvas.set_char(px, py, ch, reserve=True)
                _reserve_label_margin(canvas, start - 1, row)
                _reserve_label_margin(canvas, start + length, row)
                return
        start = max(lo, min(center - length // 2, hi - length + 1))
        for (px, py), ch in zip(cells(start), label):
            if not canvas.is_reserved(px, py):
                canvas.set_char(px, py, ch, reserve=True)
        return

    # Vertical segment: the label still reads horizontally, centered on
    # column x0; search along y for a row whose horizontal run is clear.
    lo, hi = (y0, y1) if y0 <= y1 else (y1, y0)
    col = x0
    # Clamp rather than let the run go negative: a negative x is simply
    # unaddressable (Canvas has no left margin to grow into), which would
    # silently drop the label's leading characters instead of overflowing
    # visibly to the right like every other overflow case in this module.
    start_x = max(0, col - length // 2)

    def row_cells(row: int) -> list[tuple[int, int]]:
        return [(start_x + i, row) for i in range(length)]

    center_row = (lo + hi) // 2
    for row in _label_positions(1, center_row, lo, hi):
        run = row_cells(row)
        if not any(canvas.is_reserved(x, y) for x, y in run):
            for (px, py), ch in zip(run, label):
                canvas.set_char(px, py, ch, reserve=True)
            _reserve_label_margin(canvas, start_x - 1, row)
            _reserve_label_margin(canvas, start_x + length, row)
            return
    for (px, py), ch in zip(row_cells(center_row), label):
        if not canvas.is_reserved(px, py):
            canvas.set_char(px, py, ch, reserve=True)


def _draw_polyline(canvas: Canvas, points: list[tuple[int, int]], style: EdgeStyle) -> None:
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        canvas.draw_segment(x0, y0, x1, y1, style)


def _draw_arrowheads(canvas: Canvas, points: list[tuple[int, int]], edge: FlowEdge) -> None:
    if edge.dst_arrow:
        canvas.draw_glyph(*points[-1], _arrow_glyph(points[-2], points[-1]))
    if edge.src_arrow:
        canvas.draw_glyph(*points[0], _arrow_glyph(points[1], points[0]))


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
    lane_counter: list[int],
    self_loop_counter: dict[str, int],
) -> list[tuple[int, int]] | None:
    """Compute one edge's polyline points: anchors chosen by relative rank
    position, an L/Z/C path shape. Pure path computation only — drawing is
    the caller's job, split into two passes across *all* edges (see
    :func:`layout_flowgraph`) so that no edge's line ever overwrites
    another edge's already-placed label. Dangling node-id references
    return ``None`` (defensive no-op — the parser guarantees valid
    endpoints; this module never crashes on one).
    """
    src_rect = rects.get(edge.src)
    dst_rect = rects.get(edge.dst)
    if src_rect is None or dst_rect is None:
        return None

    if edge.src == edge.dst:
        lane = self_loop_counter.get(edge.src, 0)
        self_loop_counter[edge.src] = lane + 1
        return _self_loop_points(direction, src_rect, lane)

    src_extent = _rank_extent(direction, src_rect)
    dst_extent = _rank_extent(direction, dst_rect)
    same_rank = not (dst_extent[1] < src_extent[0] or src_extent[1] < dst_extent[0])

    if same_rank:
        return [_facing_anchor(src_rect, dst_rect), _facing_anchor(dst_rect, src_rect)]

    src_center = (src_extent[0] + src_extent[1]) / 2
    dst_center = (dst_extent[0] + dst_extent[1]) / 2
    forward = (dst_center > src_center) == _forward_increasing(direction)
    if forward:
        return _z_path(
            direction,
            _forward_exit(direction, src_rect),
            _forward_entry(direction, dst_rect),
        )

    lane = lane_counter[0]
    lane_counter[0] += 1
    lane_secondary = (
        _lane_secondary_base(direction, src_rect, dst_rect)
        + _LANE_MARGIN
        + lane * _LANE_GAP
    )
    return _lane_path(
        direction,
        _lane_anchor(direction, src_rect),
        _lane_anchor(direction, dst_rect),
        lane_secondary,
    )


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
                canvas.draw_box(rect, n.shape, n.label)
        # Two passes across *all* edges, not one pass per edge: every
        # edge's line + arrowheads draw first, then every edge's label
        # draws last (see design doc). Interleaving line-then-label per
        # edge (the old order) let a later edge's line silently erase an
        # earlier edge's already-placed label whenever their paths shared
        # a cell — labels are only ever safe once no more lines are coming.
        lane_counter = [0]
        self_loop_counter: dict[str, int] = {}
        edge_paths: list[tuple[FlowEdge, list[tuple[int, int]]]] = []
        for e in g.edges:
            points = _route_edge_path(rects, g.direction, e, lane_counter, self_loop_counter)
            if points is not None:
                edge_paths.append((e, points))
        for e, points in edge_paths:
            _draw_polyline(canvas, points, e.style)
            _draw_arrowheads(canvas, points, e)
        for e, points in edge_paths:
            if e.label:
                seg = _longest_segment(points)
                if seg is not None:
                    _draw_label_on_segment(canvas, *seg, e.label)
        return canvas.to_lines()
    except Exception:
        return []
