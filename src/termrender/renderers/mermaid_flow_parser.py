"""Parser for mermaid ``graph``/``flowchart`` sources.

Standalone module: exposes a single pure function, :func:`parse`, that turns
a mermaid flowchart source string into a :class:`~termrender.renderers.
mermaid_flow_model.FlowGraph`. This module has no dependency on the layout
engine (``mermaid_flow_layout.py``) or on ``Block``/the render pipeline —
both the parser and the engine depend only on ``mermaid_flow_model``.

Grammar covered
---------------
- Header: ``graph``/``flowchart`` followed by an optional direction token
  (``TD``/``TB``/``LR``/``RL``/``BT``); ``TD`` is normalized to
  :class:`Direction.TB`. Direction defaults to ``TB`` when omitted.
  Statements are ``;``-separated as well as newline-separated (mermaid
  allows ``graph TD; A-->B; A-->C`` on one line); each ``;``-part is
  processed as its own statement in order.
- Node shapes: ``[rect]``, ``(round)``, ``{diamond}``, ``([stadium])``,
  ``[(cylinder)]``, ``((circle))``, ``{{hexagon}}``, ``[[subroutine]]``,
  ``[/parallelogram/]``. ``id[Label]`` splits into graph-key ``id`` and
  drawn ``label``; a bare ``A`` (no shape delimiters at all) is both id and
  label. Re-declaring an id with a *bare* reference never downgrades an
  already-richer node; re-declaring with any shape delimiters (even ``[A]``
  repeating the same label) updates the label/shape in place — the last
  shaped declaration wins.
- Edges: ``-->``, ``---``, ``-.->``, ``-.-``, ``==>``, ``===``, and the
  bidirectional ``<-->``/``<-.->``/``<==>`` forms, in both the ``|label|``
  pipe form and the inline ``A -- text --> B`` / ``A -. text .-> B`` /
  ``A == text ==> B`` form. ``&`` fan-out (``A & B --> C & D``) expands to
  the full cartesian product of edges, each carrying the shared style/
  label/arrow flags; the ``&`` splitter is bracket-depth-aware so a literal
  ``&`` inside a node label (``A[Foo & Bar]``) is not mistaken for fan-out.
  Empty-string labels (``A -->|| B``) are stored as ``None``.
- ``subgraph <id>[ title] ... end``: ``id[title]`` splits into graph key and
  display title; a bare ``subgraph Sub1`` (no brackets) uses the token as
  both id and title. Nesting is a stack: a node declared while a subgraph is
  open is added to the *innermost* currently-open subgraph's ``node_ids``
  only (not its ancestors). An unterminated subgraph at end-of-input is
  auto-closed (attached to its parent, or promoted to a top-level result)
  rather than dropped.
- ``class``/``classDef``/``style``/``click``/``linkStyle`` lines and ``%%``
  comments are consumed and dropped — no trace in the model.

Known degradations (by design, not bugs)
-----------------------------------------
- Only the *first* non-blank line (after skipping mermaid's standard
  prelude — ``%%`` comments, ``%%{init: ...}%%`` directives, ``---``
  frontmatter — via :func:`~termrender.renderers.mermaid_prelude.
  strip_prelude_lines`) is checked for the ``graph``/``flowchart`` header;
  if it is missing, :func:`parse` raises :class:`FlowchartError`. Every
  other malformed line in the body (an edge with no recognizable endpoint,
  a shape with mismatched brackets, a stray ``end`` with nothing open) is
  silently dropped instead — best-effort, never raises.
- The inline dash-label form (``A -- text --> B``) requires the opening
  and closing delimiters to be the canonical 2-character tokens (``--``,
  ``-.``, ``==``) with at least one space around the label text. A literal
  run of ``--``/``-.``/`==`` *inside* an unbracketed label (not inside
  ``[...]``/``(...)``/``{...}``) can be mis-tokenized as a connector; this
  mirrors the inherent ambiguity of mermaid's own line-oriented grammar and
  is out of scope to fully resolve (real diagrams don't put bare dashes in
  unbracketed label text).
- Node/subgraph identifiers must start with an alphanumeric or ``_``
  character; the rest of the id token may also contain ``-``. IDs using
  other leading characters are not recognized (the line degrades silently).
"""

from __future__ import annotations

import re
from collections.abc import Iterator

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

__all__ = ["parse", "FlowchartError"]


class FlowchartError(Exception):
    """Raised when source cannot be parsed as a mermaid flowchart at all."""


# --------------------------------------------------------------------------
# Grammar
# --------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^(graph|flowchart)\b\s*(.*)$", re.IGNORECASE)
_DIRECTION_RE = re.compile(r"^(TB|TD|LR|RL|BT)\b", re.IGNORECASE)

_SUBGRAPH_RE = re.compile(r"^subgraph\b\s*(.*)$", re.IGNORECASE)
_SUBGRAPH_ID_TITLE_RE = re.compile(r"^(\S+)\s*\[(.*)\]$")
_END_RE = re.compile(r"^end$", re.IGNORECASE)
_IGNORED_RE = re.compile(r"^(classDef|class|click|linkStyle|style)\b", re.IGNORECASE)
_COMMENT_RE = re.compile(r"^%%")

_NODE_ID_RE = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_-]*)(.*)$")
_SHAPE_PATTERNS: list[tuple[NodeShape, re.Pattern[str]]] = [
    (NodeShape.STADIUM, re.compile(r"^\(\[(.*)\]\)$")),
    (NodeShape.CYLINDER, re.compile(r"^\[\((.*)\)\]$")),
    (NodeShape.CIRCLE, re.compile(r"^\(\((.*)\)\)$")),
    (NodeShape.HEXAGON, re.compile(r"^\{\{(.*)\}\}$")),
    (NodeShape.SUBROUTINE, re.compile(r"^\[\[(.*)\]\]$")),
    (NodeShape.PARALLELOGRAM, re.compile(r"^\[/(.*)/\]$")),
    (NodeShape.RECT, re.compile(r"^\[(.*)\]$")),
    (NodeShape.ROUND, re.compile(r"^\((.*)\)$")),
    (NodeShape.DIAMOND, re.compile(r"^\{(.*)\}$")),
]

# One statement is `left <connector> right`, where <connector> is either the
# inline dash-label form (odelim ... label ... cdelim) or a bare/pipe-label
# connector token. `left` is non-greedy so the connector alternation is tried
# at the earliest position that yields an overall match.
_EDGE_RE = re.compile(
    r"^(?P<left>.+?)\s*"
    r"(?:"
    r"(?P<lhead1><)?(?P<odelim>--|-\.|==)\s+(?P<label>.+?)\s+"
    r"(?P<cdelim>-->|---|\.->|\.-|==>|===)"
    r"|"
    r"(?P<lhead2><)?(?P<conn>-\.+->|-\.+-|={2,}>|={3,}|-{2,}>|-{2,})"
    r"(?:\s*\|(?P<plabel>[^|]*)\|)?"
    r")"
    r"\s*(?P<right>.+)$"
)

_OPENERS = set("([{")
_CLOSERS = {")", "]", "}"}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _norm_label(text: str | None) -> str | None:
    if text is None:
        return None
    stripped = text.strip()
    return stripped or None


def _split_amp(text: str) -> list[str]:
    """Split on top-level ``&`` only — a ``&`` nested inside ``[...]``/
    ``(...)``/``{...}`` (part of a node label) is left untouched."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch in _OPENERS:
            depth += 1
            buf.append(ch)
        elif ch in _CLOSERS:
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "&" and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _iter_statements(lines: list[str]) -> Iterator[str]:
    """Flatten source lines into ``;``-and-newline-separated statements."""
    for raw in lines:
        for part in raw.split(";"):
            part = part.strip()
            if part:
                yield part


def _extract_direction(rest: str) -> Direction:
    m = _DIRECTION_RE.match(rest.strip())
    if not m:
        return Direction.TB
    token = m.group(1).upper()
    if token == "TD":
        token = "TB"
    return Direction(token)


def _parse_subgraph_header(rest: str) -> tuple[str, str]:
    rest = rest.strip()
    if not rest:
        return "", ""
    m = _SUBGRAPH_ID_TITLE_RE.match(rest)
    if m:
        sub_id = m.group(1).strip()
        title = m.group(2).strip()
        return sub_id, (title or sub_id)
    bare = rest.strip('"')
    return bare, bare


def _parse_node_spec(text: str) -> tuple[str, str, NodeShape, bool] | None:
    """Split one node reference into ``(id, label, shape, is_bare)``.

    Returns ``None`` when ``text`` doesn't start with a valid id token, or
    carries trailing content that doesn't match any recognized shape
    delimiter (malformed shape — dropped silently by the caller)."""
    m = _NODE_ID_RE.match(text)
    if not m:
        return None
    node_id = m.group(1)
    rest = text[m.end(1) :].strip()
    if not rest:
        return node_id, node_id, NodeShape.RECT, True
    for shape, pattern in _SHAPE_PATTERNS:
        sm = pattern.match(rest)
        if sm:
            label = sm.group(1).strip()
            return node_id, (label if label else node_id), shape, False
    return None


# --------------------------------------------------------------------------
# Parse state mutation
# --------------------------------------------------------------------------


def _register(
    nodes: dict[str, FlowNode],
    stack: list[Subgraph],
    node_id: str,
    label: str,
    shape: NodeShape,
    is_bare: bool,
) -> None:
    existing = nodes.get(node_id)
    if existing is None:
        nodes[node_id] = FlowNode(id=node_id, label=label, shape=shape)
    elif not is_bare:
        existing.label = label
        existing.shape = shape
    if stack and node_id not in stack[-1].node_ids:
        stack[-1].node_ids.append(node_id)


def _resolve_nodes(
    text: str, nodes: dict[str, FlowNode], stack: list[Subgraph]
) -> list[str]:
    ids: list[str] = []
    for part in _split_amp(text.strip()):
        parsed = _parse_node_spec(part)
        if parsed is None:
            continue
        node_id, label, shape, is_bare = parsed
        _register(nodes, stack, node_id, label, shape, is_bare)
        ids.append(node_id)
    return ids


def _try_edge(
    stmt: str,
    nodes: dict[str, FlowNode],
    edges: list[FlowEdge],
    stack: list[Subgraph],
) -> bool:
    m = _EDGE_RE.match(stmt)
    if not m:
        return False
    gd = m.groupdict()

    if gd.get("odelim") is not None:
        style = {
            "--": EdgeStyle.SOLID,
            "-.": EdgeStyle.DOTTED,
            "==": EdgeStyle.THICK,
        }[gd["odelim"]]
        dst_arrow = gd["cdelim"].endswith(">")
        src_arrow = gd.get("lhead1") is not None
        label = _norm_label(gd.get("label"))
    else:
        conn = gd["conn"] or ""
        if "." in conn:
            style = EdgeStyle.DOTTED
        elif conn.startswith("="):
            style = EdgeStyle.THICK
        else:
            style = EdgeStyle.SOLID
        dst_arrow = conn.endswith(">")
        src_arrow = gd.get("lhead2") is not None
        label = _norm_label(gd.get("plabel"))

    left_ids = _resolve_nodes(gd["left"], nodes, stack)
    right_ids = _resolve_nodes(gd["right"], nodes, stack)
    for src in left_ids:
        for dst in right_ids:
            edges.append(
                FlowEdge(
                    src=src,
                    dst=dst,
                    style=style,
                    label=label,
                    dst_arrow=dst_arrow,
                    src_arrow=src_arrow,
                )
            )
    return True


def _try_node_decl(
    stmt: str, nodes: dict[str, FlowNode], stack: list[Subgraph]
) -> bool:
    parsed = _parse_node_spec(stmt.strip())
    if parsed is None:
        return False
    node_id, label, shape, is_bare = parsed
    _register(nodes, stack, node_id, label, shape, is_bare)
    return True


def _close_subgraph(stack: list[Subgraph], roots: list[Subgraph]) -> None:
    done = stack.pop()
    if stack:
        stack[-1].children.append(done)
    else:
        roots.append(done)


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def parse(source: str) -> FlowGraph:
    """Parse a mermaid ``graph``/``flowchart`` source into a :class:`FlowGraph`.

    Args:
        source: The mermaid fence body; its first non-blank line (after
            skipping the standard mermaid prelude) must start with
            ``graph`` or ``flowchart``.

    Returns:
        A populated :class:`FlowGraph`. A structurally-empty but headed
        diagram (blank/comment-only body) returns a graph with no nodes.

    Raises:
        FlowchartError: If ``source`` is not a mermaid flowchart at all
            (missing the ``graph``/``flowchart`` header).
    """
    lines = source.splitlines()
    sniff_lines = strip_prelude_lines(lines)
    first = next((line.strip() for line in sniff_lines if line.strip()), "")
    if not _HEADER_RE.match(first):
        raise FlowchartError(
            "not a mermaid flowchart: source must start with 'graph' or 'flowchart'"
        )

    direction = Direction.TB
    nodes: dict[str, FlowNode] = {}
    edges: list[FlowEdge] = []
    roots: list[Subgraph] = []
    stack: list[Subgraph] = []
    seen_header = False

    for stmt in _iter_statements(lines):
        if not seen_header:
            m = _HEADER_RE.match(stmt)
            if m:
                direction = _extract_direction(m.group(2))
                seen_header = True
            continue

        if _COMMENT_RE.match(stmt):
            continue

        m = _SUBGRAPH_RE.match(stmt)
        if m:
            sub_id, title = _parse_subgraph_header(m.group(1))
            stack.append(Subgraph(id=sub_id, title=title))
            continue

        if _END_RE.match(stmt):
            if stack:
                _close_subgraph(stack, roots)
            continue

        if _IGNORED_RE.match(stmt):
            continue

        if _try_edge(stmt, nodes, edges, stack):
            continue

        if _try_node_decl(stmt, nodes, stack):
            continue

        # Unrecognized body line: consumed silently, best-effort.

    # Auto-close any subgraphs left open at end-of-input.
    while stack:
        _close_subgraph(stack, roots)

    return FlowGraph(
        direction=direction,
        nodes=list(nodes.values()),
        edges=edges,
        subgraphs=roots,
    )
