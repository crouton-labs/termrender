"""Native ASCII renderer for mermaid ``stateDiagram``/``stateDiagram-v2`` sources.

Standalone module: exposes a single pure function, ``render_state``. Not
wired into ``mermaid.py``'s dispatcher (a later, orchestrator-owned phase)
— nothing in this package imports it yet.

Layout model
------------
This module owns none of the layout math. A state diagram is translated
into the flowchart engine's own model (:class:`~termrender.renderers.
mermaid_flow_model.FlowGraph`/``FlowNode``/``FlowEdge``/``Subgraph``) and
handed straight to :func:`~termrender.renderers.mermaid_flow_layout.
layout_flowgraph` — the same grandalf-based Sugiyama layout, box
rasterizer, orthogonal edge router, and subgraph-frame drawer used by the
native flowchart renderer. States become boxes, transitions become edges,
composite ``state X { ... }`` blocks become subgraph frames — this module
is purely the state-diagram-to-flowchart-model adapter (parse + translate);
:func:`render_state` is ``parse -> layout_flowgraph -> lines``, wrapped in
a degradation guard, mirroring ``mermaid_flow.py``'s own public contract
and the same box-glyph-presence success signal the crouter attach viewer
depends on.

Grammar supported
------------------
Header: ``stateDiagram``/``stateDiagram-v2``. Transitions: ``A --> B`` and
``A --> B : event`` (the event becomes the edge label). ``[*]`` as a
pseudo-state: as a transition source it is the (per-scope) start marker,
rendered as a compact rounded box holding a single ``\u25cf`` (filled
circle) glyph; as a transition destination it is the (per-scope) end
marker, holding a single ``\u25c9`` (fisheye) glyph instead — same shape,
distinct glyph, so start and end read differently without a bespoke
border. Each lexical scope (the top level, or one per composite state) has
its own shared start/end marker, created lazily and reused across every
``[*]`` reference within that scope — mirrors mermaid's "one implicit
start/end per machine" semantics. ``state "Long name" as s1`` aliases a
plain state's display label; the same form immediately followed by ``{``
both aliases *and* opens a composite. ``state X { ... }`` (with or without
an alias) opens a composite state, translated to a
:class:`~termrender.renderers.mermaid_flow_model.Subgraph`: transitions and
sub-states declared inside become members of that subgraph (nesting via
``Subgraph.children``, exactly as deep as the source nests), and are drawn
inside the engine's enclosing frame. A composite id referenced directly by
a transition *outside* its own block (entering/exiting the composite as a
whole, rather than one of its substates) gets its own proxy
:class:`FlowNode` — the engine has no notion of an edge terminating on a
frame's border, so this proxy renders as an ordinary small box near (not
inside) the frame; a composite never referenced this way gets no such
box. ``state X <<choice>>`` marks ``X`` a choice pseudo-state (rendered as
the engine's existing compact diamond); ``<<fork>>``/``<<join>>`` degrade
to the engine's plain small rectangle (no bespoke bar glyph exists in the
underlying engine — "a small box" is the documented, explicit fallback for
these two). ``direction LR``/``TD``/``TB``/``RL``/``BT`` on its own line
sets the whole diagram's rank-flow direction (last one wins if repeated).
``note left of X : text`` and the multi-line ``note left of X`` / ...  /
``end note`` block form both attach: the note becomes its own small boxed
node holding the note text, joined to ``X`` by a plain undirected dotted
line (no arrowhead either end) — the engine has no "float this box beside
that one" primitive, so the left/right side isn't honored, but the text
itself is never dropped (see *Known degradations*). A lone ``--`` or
``---`` line inside a composite (mermaid's concurrent-region separator) is
consumed with no effect — the regions on either side flatten into one
shared sibling scope rather than rendering as visually distinct lanes.
``%%`` line comments are skipped anywhere, including inside a multi-line
``note ... / end note`` block (a comment line there is dropped, not folded
into the note text).

Known degradations (by design, not bugs)
-----------------------------------------
- Note position (``left of``/``right of``) has no engine-level lever (node
  placement comes from grandalf's layering, not manual coordinates) and is
  not honored; the note still renders, just wherever the graph places it,
  with its full text intact.
- A composite id referenced by an external transition before its own
  ``state X { ... }``/``state "..." as X { ... }`` declaration is seen
  (a forward reference) gets its proxy box labeled with the bare id rather
  than the composite's eventual display title — declaration-order
  dependency, matching the equivalent limitation already documented for
  the flowchart parser's node re-declaration policy.
- Fork/join pseudo-states render as the engine's plain small rectangle,
  not a bar — see *Grammar supported* above.
- Everything else the underlying flowchart engine already documents as a
  degradation (dense-graph crossings, CJK label wrapping, minimum-box-size
  cosmetics, a subgraph that isn't contiguous enough for a clean frame
  flattening instead) applies unchanged, since this module draws through
  that engine. See ``mermaid_flow_layout.py``'s and ``mermaid_flow.py``'s
  module docstrings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from termrender.renderers.mermaid_flow_layout import layout_flowgraph
from termrender.renderers.mermaid_flow_model import (
    Direction,
    EdgeStyle,
    FlowEdge,
    FlowGraph,
    FlowNode,
    NodeShape,
    Subgraph,
)
from termrender.renderers.mermaid_prelude import strip_prelude_lines

__all__ = ["render_state", "StateDiagramError"]


class StateDiagramError(Exception):
    """Raised when source cannot be parsed as a mermaid state diagram at all."""


# --------------------------------------------------------------------------
# Grammar
# --------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^stateDiagram(-v2)?\b", re.IGNORECASE)
_DIRECTION_RE = re.compile(r"^direction\s+(TB|TD|LR|RL|BT)\s*$", re.IGNORECASE)
_COMMENT_RE = re.compile(r"^%%")
_CONCURRENCY_SEP_RE = re.compile(r"^-{2,}\s*$")

_ALIAS_RE = re.compile(r'^state\s+"([^"]*)"\s+as\s+(\S+?)\s*(\{)?\s*$', re.IGNORECASE)
_COMPOSITE_START_RE = re.compile(r"^state\s+(\S+)\s*\{\s*$", re.IGNORECASE)
_COMPOSITE_END_RE = re.compile(r"^\}\s*$")
_ANNOTATION_RE = re.compile(
    r"^state\s+(\S+)\s*<<\s*(choice|fork|join)\s*>>\s*$", re.IGNORECASE
)
_BARE_STATE_RE = re.compile(r"^state\s+(\S+)\s*$", re.IGNORECASE)

_NOTE_INLINE_RE = re.compile(
    r"^note\s+(left|right)\s+of\s+(\S+)\s*:\s*(.*)$", re.IGNORECASE
)
_NOTE_BLOCK_START_RE = re.compile(
    r"^note\s+(left|right)\s+of\s+(\S+)\s*$", re.IGNORECASE
)
_NOTE_END_RE = re.compile(r"^end\s+note\s*$", re.IGNORECASE)

# Non-greedy src: a plain id never legitimately contains "-->", but the
# greedy alternative would still (via backtracking) find *a* match — lazy
# quantification just makes it find the intended (leftmost) one directly.
_TRANSITION_RE = re.compile(
    r"^(?P<src>\[\*\]|\S+?)\s*-->\s*(?P<dst>\[\*\]|\S+)\s*(?::\s*(?P<label>.*))?$"
)

_START_GLYPH = "\u25cf"  # ● filled circle — start pseudo-state marker
_END_GLYPH = "\u25c9"  # ◉ fisheye — end pseudo-state marker, distinct from start

_ANNOTATION_SHAPE: dict[str, NodeShape] = {
    "choice": NodeShape.DIAMOND,
    "fork": NodeShape.RECT,
    "join": NodeShape.RECT,
}


@dataclass
class _Scope:
    """One lexical scope's ``[*]`` bookkeeping: the root, or one composite
    state's body. ``key`` namespaces the synthetic start/end marker ids so
    nested composites each get their own start/end rather than sharing the
    root's."""

    key: str
    start_id: str | None = None
    end_id: str | None = None


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _norm_label(text: str | None) -> str | None:
    if text is None:
        return None
    stripped = text.strip()
    return stripped or None


def _pseudo_id(scope_key: str, kind: str) -> str:
    return f"__{kind}__" if not scope_key else f"__{kind}_{scope_key}__"


def _register(
    nodes: dict[str, FlowNode],
    stack: list[Subgraph],
    node_id: str,
    label: str | None = None,
    shape: NodeShape | None = None,
) -> None:
    """Register (or update) a state node — mirrors the flowchart parser's
    node re-declaration policy: an existing node's label/shape is updated
    in place when a richer declaration supplies one, never downgraded by a
    later bare reference. Adds ``node_id`` to the innermost currently-open
    composite's member list (once), if any composite is open."""
    existing = nodes.get(node_id)
    if existing is None:
        nodes[node_id] = FlowNode(
            id=node_id,
            label=label if label is not None else node_id,
            shape=shape if shape is not None else NodeShape.RECT,
        )
    else:
        if label is not None:
            existing.label = label
        if shape is not None:
            existing.shape = shape
    if stack and node_id not in stack[-1].node_ids:
        stack[-1].node_ids.append(node_id)


def _resolve_endpoint(
    token: str,
    kind: str,
    scope: _Scope,
    nodes: dict[str, FlowNode],
    stack: list[Subgraph],
    composites: dict[str, Subgraph],
) -> str:
    """Resolve one transition endpoint token to a graph node id: ``[*]``
    becomes the current scope's shared start (``kind == "start"``) or end
    (``kind == "end"``) marker, created lazily on first reference; any
    other token is registered as an ordinary state (using the composite's
    display title if the token happens to be a known composite id, so a
    transition that targets a composite directly gets a sensibly-labeled
    proxy box — see the module docstring)."""
    if token == "[*]":
        if kind == "start":
            if scope.start_id is None:
                scope.start_id = _pseudo_id(scope.key, "start")
                _register(
                    nodes, stack, scope.start_id, label=_START_GLYPH, shape=NodeShape.ROUND
                )
            return scope.start_id
        if scope.end_id is None:
            scope.end_id = _pseudo_id(scope.key, "end")
            _register(
                nodes, stack, scope.end_id, label=_END_GLYPH, shape=NodeShape.ROUND
            )
        return scope.end_id

    if token not in nodes:
        label = composites[token].title if token in composites else None
        _register(nodes, stack, token, label=label)
    return token


def _attach_note(
    nodes: dict[str, FlowNode],
    edges: list[FlowEdge],
    stack: list[Subgraph],
    composites: dict[str, Subgraph],
    target: str | None,
    text: str,
    counters: dict[str, int],
) -> None:
    """Attach a note as its own small boxed node, joined to ``target`` by a
    plain (headless) dotted line. Never drops non-empty note text (see the
    module docstring's degradation notes on *why* the box floats wherever
    the graph places it rather than strictly left/right of ``target``)."""
    stripped = text.strip()
    if not target or not stripped:
        return
    if target not in nodes:
        label = composites[target].title if target in composites else None
        _register(nodes, stack, target, label=label)
    counters["note"] += 1
    note_id = f"__note_{counters['note']}__"
    _register(nodes, stack, note_id, label=stripped, shape=NodeShape.RECT)
    edges.append(
        FlowEdge(
            src=target,
            dst=note_id,
            style=EdgeStyle.DOTTED,
            label=None,
            dst_arrow=False,
            src_arrow=False,
        )
    )


def _close_composite(stack: list[Subgraph], roots: list[Subgraph]) -> None:
    done = stack.pop()
    if stack:
        stack[-1].children.append(done)
    else:
        roots.append(done)


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def parse(source: str) -> FlowGraph:
    """Parse a mermaid ``stateDiagram``/``stateDiagram-v2`` source into a
    :class:`~termrender.renderers.mermaid_flow_model.FlowGraph` — the
    flowchart engine's own model, so :func:`~termrender.renderers.
    mermaid_flow_layout.layout_flowgraph` can render it directly.

    Args:
        source: The mermaid fence body; its first non-blank line (after
            skipping the standard mermaid prelude) must start with
            ``stateDiagram``.

    Returns:
        A populated :class:`FlowGraph`. A structurally-empty but headed
        diagram (blank/comment-only body) returns a graph with no nodes.

    Raises:
        StateDiagramError: If ``source`` is not a mermaid state diagram at
            all (missing the ``stateDiagram`` header).
    """
    lines = source.splitlines()
    sniff_lines = strip_prelude_lines(lines)
    first = next((line.strip() for line in sniff_lines if line.strip()), "")
    if not _HEADER_RE.match(first):
        raise StateDiagramError(
            "not a mermaid state diagram: source must start with 'stateDiagram'"
        )

    direction = Direction.TB
    nodes: dict[str, FlowNode] = {}
    edges: list[FlowEdge] = []
    composites: dict[str, Subgraph] = {}
    roots: list[Subgraph] = []
    stack: list[Subgraph] = []
    scopes: list[_Scope] = [_Scope(key="")]
    counters = {"note": 0}
    seen_header = False
    note_target: str | None = None
    note_lines: list[str] | None = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if note_lines is not None:
            if _NOTE_END_RE.match(line):
                _attach_note(
                    nodes, edges, stack, composites, note_target,
                    " ".join(note_lines), counters,
                )
                note_target = None
                note_lines = None
            elif not _COMMENT_RE.match(line):
                note_lines.append(line)
            continue

        if not seen_header:
            if _HEADER_RE.match(line):
                seen_header = True
            continue

        if _COMMENT_RE.match(line):
            continue

        if _CONCURRENCY_SEP_RE.match(line):
            continue

        m = _DIRECTION_RE.match(line)
        if m:
            token = m.group(1).upper()
            direction = Direction.TB if token == "TD" else Direction(token)
            continue

        m = _NOTE_INLINE_RE.match(line)
        if m:
            _attach_note(
                nodes, edges, stack, composites, m.group(2), m.group(3), counters
            )
            continue

        m = _NOTE_BLOCK_START_RE.match(line)
        if m:
            note_target = m.group(2)
            note_lines = []
            continue

        m = _ALIAS_RE.match(line)
        if m:
            title, node_id, opens_brace = m.groups()
            display = title.strip() or node_id
            if opens_brace:
                sub = Subgraph(id=node_id, title=display)
                composites[node_id] = sub
                stack.append(sub)
                scopes.append(_Scope(key=node_id))
            else:
                _register(nodes, stack, node_id, label=display)
            continue

        m = _COMPOSITE_START_RE.match(line)
        if m:
            node_id = m.group(1)
            sub = Subgraph(id=node_id, title=node_id)
            composites[node_id] = sub
            stack.append(sub)
            scopes.append(_Scope(key=node_id))
            continue

        if _COMPOSITE_END_RE.match(line):
            if stack:
                _close_composite(stack, roots)
                if len(scopes) > 1:
                    scopes.pop()
            continue

        m = _ANNOTATION_RE.match(line)
        if m:
            node_id, kind = m.groups()
            _register(nodes, stack, node_id, shape=_ANNOTATION_SHAPE[kind.lower()])
            continue

        m = _TRANSITION_RE.match(line)
        if m:
            scope = scopes[-1]
            src_id = _resolve_endpoint(
                m.group("src"), "start", scope, nodes, stack, composites
            )
            dst_id = _resolve_endpoint(
                m.group("dst"), "end", scope, nodes, stack, composites
            )
            edges.append(
                FlowEdge(
                    src=src_id,
                    dst=dst_id,
                    style=EdgeStyle.SOLID,
                    label=_norm_label(m.group("label")),
                    dst_arrow=True,
                    src_arrow=False,
                )
            )
            continue

        m = _BARE_STATE_RE.match(line)
        if m:
            _register(nodes, stack, m.group(1))
            continue

        # Unrecognized body line: consumed silently, best-effort.

    if note_lines is not None:
        _attach_note(
            nodes, edges, stack, composites, note_target,
            " ".join(note_lines), counters,
        )

    while stack:
        _close_composite(stack, roots)

    return FlowGraph(
        direction=direction,
        nodes=list(nodes.values()),
        edges=edges,
        subgraphs=roots,
    )


# Same ranges the downstream attach viewer uses to detect render *success*
# (see mermaid_flow.py's identical guard). The raw-echo path must never
# contain one of these, even when malformed/degenerate source itself
# happens to contain a literal box-drawing or geometric glyph.
_GLYPH_RANGE_RE = re.compile("[\u2500-\u259f\u25a0-\u25ff]")


def render_state(source: str, width: int) -> list[str]:
    """Render a mermaid ``stateDiagram``/``stateDiagram-v2`` source to
    unicode lines.

    Pure and total: never raises. Degrades to a raw echo of ``source``
    (each line ``\\n``-split and ``.rstrip()``-ed, containing no
    box-drawing glyphs) exactly when:

    1. The source isn't a state diagram at all (no ``stateDiagram`` header
       on its first non-blank, post-prelude line) — :func:`parse` raises
       :class:`StateDiagramError`.
    2. Parsing succeeds but yields zero states (an empty or comment-only
       diagram body) — nothing to draw.
    3. Any unexpected exception escapes :func:`~termrender.renderers.
       mermaid_flow_layout.layout_flowgraph` — a defensive catch-all; this
       should never happen for well-typed input, but the guarantee is
       "never crash, degrade" regardless.

    Otherwise, returns the rendered diagram: guaranteed to contain unicode
    box-drawing glyphs (every state is a bordered box), never ANSI escapes.

    Args:
        source: The mermaid fence body (with or without the surrounding
            fence markers — only the text between them).
        width: Advisory terminal width; sized to content, may overflow
            (see the module docstring's "Known degradations", inherited
            from the underlying flowchart engine).

    Returns:
        Rendered lines on success, or a raw-echo of ``source`` on any of
        the three degradation conditions above.
    """
    try:
        graph = parse(source)
    except StateDiagramError:
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
    return [_GLYPH_RANGE_RE.sub("?", line.rstrip()) for line in source.splitlines()]
