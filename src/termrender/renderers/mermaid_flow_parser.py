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
  ``A -.text.-> B`` / ``A == text ==> B`` form. ``&`` fan-out (``A & B --> C & D``) expands to
  the full cartesian product of edges, each carrying the shared style/
  label/arrow flags. A statement may chain any number of connectors
  (``A-->B-->C``) — this is parsed as a sequence of node groups separated
  by connectors, emitting one edge per adjacent (group, connector, group)
  triple, with each connector's own style/label/arrows applied only to the
  edge it introduces. Connector scanning, ``&`` fan-out splitting, and
  ``;`` statement splitting are all bracket-depth-aware: a token that looks
  like a connector, ``&``, or ``;`` but sits inside ``[...]``/``(...)``/
  ``{...}`` (part of a node label, e.g. ``A[Go --> Fast]`` or
  ``A[Check; validate]``) is left untouched rather than mistaken for
  statement structure. Newlines and semicolons inside double-quoted labels
  remain label content instead of splitting statements. Empty-string labels
  (``A -->|| B``) are stored as ``None``. Labels are normalized: one pair of
  wrapping double quotes (mermaid's quoted-label form) is stripped, and
  ``<br/>`` (any case, optional slash/spaces) becomes a real newline in node
  labels but flattens to a space in edge labels and subgraph titles, which
  render single-line.
- ``subgraph <id>[ title] ... end``: ``id[title]`` splits into graph key and
  display title; a bare ``subgraph Sub1`` (no brackets) uses the token as
  both id and title. Nesting is a stack: a node declared while a subgraph is
  open is added to the *innermost* currently-open subgraph's ``node_ids``
  only (not its ancestors). An unterminated subgraph at end-of-input raises
  :class:`FlowchartError`.
- Well-formed ``class``/``classDef``/``style``/``click``/``linkStyle``/
  ``accTitle``/``accDescr`` lines and ``%%`` comments are consumed and
  dropped — no trace in the model. Malformed directive-looking lines are
  not special-cased and will raise.

Known degradations (by design, not bugs)
-----------------------------------------
- Only the *first* non-blank line (after skipping mermaid's standard
  prelude — ``%%`` comments, ``%%{init: ...}%%`` directives, ``---``
  frontmatter — via :func:`~termrender.renderers.mermaid_prelude.
  strip_prelude_lines`) is checked for the ``graph``/``flowchart`` header;
  if it is missing, :func:`parse` raises :class:`FlowchartError`. In the
  body, only well-formed presentational directives (``%%`` comments,
  ``classDef``, ``class``, ``style``, ``click``, ``linkStyle``,
  ``accTitle``, ``accDescr``) are ignored; malformed directive-looking
  lines, every other unrecognized line, dangling or partial connector,
  stray ``end``, or unterminated subgraph raises :class:`FlowchartError`.
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
  other leading characters are not recognized.
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
_SUBGRAPH_ID_TITLE_RE = re.compile(r"^(\S+)\s*\[(.*)\]$", re.DOTALL)
_END_RE = re.compile(r"^end$", re.IGNORECASE)
_CLASSDEF_RE = re.compile(r"^classDef\b\s+\S+\s+\S.*$", re.IGNORECASE)
_CLASS_RE = re.compile(r"^class\b(?:\s+\S+){2,}", re.IGNORECASE)
_STYLE_RE = re.compile(r"^style\b(?:\s+\S+){2,}", re.IGNORECASE)
_CLICK_RE = re.compile(r"^click\b(?:\s+\S+){2,}", re.IGNORECASE)
_LINKSTYLE_RE = re.compile(r"^linkStyle\b(?:\s+\S+){2,}", re.IGNORECASE)
_ACCTITLE_RE = re.compile(r"^accTitle\b\s*:?\s*\S.*$", re.IGNORECASE)
_ACCDESCR_RE = re.compile(r"^accDescr\b\s*:?\s*\S.*$", re.IGNORECASE)
_PRESENTATIONAL_RE = (
    _CLASSDEF_RE,
    _CLASS_RE,
    _STYLE_RE,
    _CLICK_RE,
    _LINKSTYLE_RE,
    _ACCTITLE_RE,
    _ACCDESCR_RE,
)
_DIRECTIVE_LIKE_RE = re.compile(
    r"^(?:classDef|class|style|click|linkStyle|accTitle|accDescr)(?:\s|$)",
    re.IGNORECASE,
)


def _is_presentational_directive(stmt: str) -> bool:
    return any(pattern.match(stmt) for pattern in _PRESENTATIONAL_RE)


def _is_malformed_presentational_directive(stmt: str) -> bool:
    return bool(_DIRECTIVE_LIKE_RE.match(stmt)) and not _is_presentational_directive(stmt)


_COMMENT_RE = re.compile(r"^%%")

_NODE_ID_RE = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_-]*)(.*)$", re.DOTALL)
_SHAPE_PATTERNS: list[tuple[NodeShape, re.Pattern[str]]] = [
    (NodeShape.STADIUM, re.compile(r"^\(\[(.*)\]\)$", re.DOTALL)),
    (NodeShape.CYLINDER, re.compile(r"^\[\((.*)\)\]$", re.DOTALL)),
    (NodeShape.CIRCLE, re.compile(r"^\(\((.*)\)\)$", re.DOTALL)),
    (NodeShape.HEXAGON, re.compile(r"^\{\{(.*)\}\}$", re.DOTALL)),
    (NodeShape.SUBROUTINE, re.compile(r"^\[\[(.*)\]\]$", re.DOTALL)),
    (NodeShape.PARALLELOGRAM, re.compile(r"^\[/(.*)/\]$", re.DOTALL)),
    (NodeShape.RECT, re.compile(r"^\[(.*)\]$", re.DOTALL)),
    (NodeShape.ROUND, re.compile(r"^\((.*)\)$", re.DOTALL)),
    (NodeShape.DIAMOND, re.compile(r"^\{(.*)\}$", re.DOTALL)),
]

# A single connector token: either the inline dash-label form
# (odelim ... label ... cdelim) or a bare/pipe-label connector. This is
# matched repeatedly (via `_scan_connectors`) against a whole statement to
# find every TOP-LEVEL occurrence — an edge statement is a sequence of node
# groups separated by these connectors, so `A-->B-->C` yields two matches
# and three groups (`A`, `B`, `C`), not one match with a malformed right
# side.
_CONNECTOR_RE = re.compile(
    r"(?P<lhead0><)?(?P<dotodelim>-\.)(?P<dotlabel>.+?)(?P<dotcdelim>\.->|\.-)"
    r"|"
    r"(?P<lhead1><)?(?P<odelim>--|-\.|==)\s+(?P<label>.+?)\s+"
    r"(?P<cdelim>-->|---|\.->|\.-|==>|===)"
    r"|"
    r"(?P<lhead2><)?(?P<conn>-\.+->|-\.+-|={2,}>|={3,}|-{2,}>|-{2,})"
    r'(?:\s*\|(?P<plabel>"[^"]*"|[^|]*)\|)?',
    re.DOTALL,
)

_OPENERS = set("([{")
_CLOSERS = {")", "]", "}"}

_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _strip_quotes(text: str) -> str:
    """Drop one pair of wrapping double quotes (mermaid's quoted-label
    form, e.g. ``A["text"]`` / ``-->|"text"|``) — the quotes delimit, they
    are not part of the displayed label."""
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1].strip()
    return text


def _norm_label(text: str | None) -> str | None:
    """Normalize an *edge* label: strip wrapping quotes and flatten
    ``<br/>`` to a space — edge labels render on a single line along the
    path, so a hard break has nowhere to go."""
    if text is None:
        return None
    stripped = _BR_RE.sub(" ", _strip_quotes(text.strip()))
    stripped = re.sub(r"\s*\n\s*", " ", stripped).strip()
    return stripped or None


def _norm_node_label(text: str) -> str:
    """Normalize a *node* label: strip wrapping quotes and turn ``<br/>``
    into a real newline — node labels are drawn via ``wrap_text``, which
    honors ``\\n``, for both box sizing and label placement."""
    return _BR_RE.sub("\n", _strip_quotes(text)).strip()


def _bracket_depths(text: str) -> list[int]:
    """``depths[i]`` = bracket depth immediately before ``text[i]``
    (``depths[len(text)]`` = depth at end of string). Shared by every
    top-level scanner below (connector matching, ``&`` splitting, ``;``
    splitting) to decide whether a candidate token sits inside a node
    label's ``[...]``/``(...)``/``{...}`` delimiters and should therefore
    be ignored rather than treated as statement structure."""
    depths = [0] * (len(text) + 1)
    depth = 0
    for i, ch in enumerate(text):
        depths[i] = depth
        if ch in _OPENERS:
            depth += 1
        elif ch in _CLOSERS:
            depth = max(0, depth - 1)
    depths[len(text)] = depth
    return depths


def _split_top_level(text: str, sep: str) -> list[str]:
    """Split ``text`` on top-level occurrences of the single-character
    ``sep`` only — a ``sep`` nested inside a node shape or double-quoted
    label is left untouched."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_quote = False
    escaped = False
    for ch in text:
        if ch == '"' and not escaped:
            in_quote = not in_quote
            buf.append(ch)
        elif not in_quote and ch in _OPENERS:
            depth += 1
            buf.append(ch)
        elif not in_quote and ch in _CLOSERS:
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == sep and depth == 0 and not in_quote:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        escaped = ch == "\\" and not escaped
        if ch != "\\":
            escaped = False
    parts.append("".join(buf))
    return parts


def _split_amp(text: str) -> list[str]:
    """Split on top-level ``&`` only — a ``&`` nested inside ``[...]``/
    ``(...)``/``{...}`` (part of a node label) is left untouched."""
    return [p.strip() for p in _split_top_level(text, "&") if p.strip()]


def _scan_connectors(text: str) -> list[re.Match[str]]:
    """Find every top-level (bracket-depth-0) connector match in ``text``,
    left to right. A candidate match that starts inside ``[...]``/
    ``(...)``/``{...}`` (i.e. part of a node label such as
    ``A[Go --> Fast]``) is skipped rather than accepted, and the scan
    resumes one character past the skipped match's start so a real
    top-level connector later in the same text is still found."""
    depths = _bracket_depths(text)
    matches: list[re.Match[str]] = []
    pos = 0
    while pos <= len(text):
        m = _CONNECTOR_RE.search(text, pos)
        if not m:
            break
        if depths[m.start()] == 0:
            matches.append(m)
            pos = m.end()
        else:
            pos = m.start() + 1
    return matches


def _iter_statements(lines: list[str]) -> Iterator[str]:
    """Flatten source into Mermaid statements.

    A physical newline ends a statement except while a double-quoted label
    remains open. Mermaid permits literal newlines in quoted node and edge
    labels, so those lines are joined with the newline preserved. Top-level
    semicolons delimit statements; semicolons inside shapes or quotes do not.
    """
    logical: list[str] = []
    in_quote = False
    escaped = False

    for raw in lines:
        # Comments are standalone statements; quote characters in prose do
        # not participate in Mermaid's quoted-label grammar.
        if not logical and _COMMENT_RE.match(raw.strip()):
            yield raw.strip()
            continue

        logical.append(raw)
        for ch in raw:
            if ch == '"' and not escaped:
                in_quote = not in_quote
            escaped = ch == "\\" and not escaped
            if ch != "\\":
                escaped = False

        if in_quote:
            continue

        joined = "\n".join(logical)
        logical = []
        for part in _split_top_level(joined, ";"):
            part = part.strip()
            if part:
                yield part

    if logical:
        # Preserve malformed unterminated input for the normal parser error
        # path rather than silently dropping its final statement.
        joined = "\n".join(logical).strip()
        if joined:
            yield joined


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
        # Subgraph titles render on a single header line, so <br/> flattens
        # to a space (same as edge labels).
        title = _BR_RE.sub(" ", _strip_quotes(m.group(2).strip())).strip()
        return sub_id, (title or sub_id)
    bare = _BR_RE.sub(" ", rest.strip().strip('"')).strip()
    return bare, bare


def _parse_node_spec(text: str) -> tuple[str, str, NodeShape, bool] | None:
    """Split one node reference into ``(id, label, shape, is_bare)``.

    Returns ``None`` when ``text`` doesn't start with a valid id token, or
    carries trailing content that doesn't match any recognized shape
    delimiter (malformed shape — treated as no match by the caller)."""
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
            label = _norm_node_label(sm.group(1).strip())
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


def _parse_node_group(text: str) -> list[tuple[str, str, NodeShape, bool]]:
    parsed: list[tuple[str, str, NodeShape, bool]] = []
    for part in _split_amp(text.strip()):
        node = _parse_node_spec(part)
        if node is None:
            return []
        parsed.append(node)
    return parsed


def _try_edge(
    stmt: str,
    nodes: dict[str, FlowNode],
    edges: list[FlowEdge],
    stack: list[Subgraph],
) -> bool:
    """Parse ``stmt`` as an edge statement: a sequence of node groups
    separated by top-level connectors (one group for a plain edge, three
    or more for a chain like ``A-->B-->C``). Emits one (fan-out-expanded)
    edge per adjacent (group, connector, group) triple, each carrying its
    own connector's style/label/arrows."""
    connectors = _scan_connectors(stmt)
    if not connectors:
        return False

    groups: list[str] = []
    prev_end = 0
    for m in connectors:
        groups.append(stmt[prev_end : m.start()])
        prev_end = m.end()
    groups.append(stmt[prev_end:])

    parsed_groups = [_parse_node_group(group) for group in groups]
    if any(not group for group in parsed_groups):
        raise FlowchartError(f"malformed flowchart edge statement: {stmt!r}")

    resolved: list[list[str]] = []
    for group in parsed_groups:
        ids: list[str] = []
        for node_id, label, shape, is_bare in group:
            _register(nodes, stack, node_id, label, shape, is_bare)
            ids.append(node_id)
        resolved.append(ids)

    for i, m in enumerate(connectors):
        gd = m.groupdict()
        if gd.get("dotodelim") is not None:
            style = EdgeStyle.DOTTED
            dst_arrow = gd["dotcdelim"].endswith(">")
            src_arrow = gd.get("lhead0") is not None
            label = _norm_label(gd.get("dotlabel"))
        elif gd.get("odelim") is not None:
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

        for src in resolved[i]:
            for dst in resolved[i + 1]:
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
            else:
                raise FlowchartError("stray 'end' with nothing open")
            continue

        if _is_presentational_directive(stmt):
            continue

        if _is_malformed_presentational_directive(stmt):
            raise FlowchartError(f"unrecognized flowchart statement: {stmt!r}")

        if _try_edge(stmt, nodes, edges, stack):
            continue

        if _try_node_decl(stmt, nodes, stack):
            continue

        raise FlowchartError(f"unrecognized flowchart statement: {stmt!r}")

    if stack:
        raise FlowchartError("unterminated subgraph")

    return FlowGraph(
        direction=direction,
        nodes=list(nodes.values()),
        edges=edges,
        subgraphs=roots,
    )
