"""Native renderer for mermaid ``classDiagram`` sources.

Wired into ``mermaid.py``'s dispatcher: exposes a single pure function,
:func:`render_class`. Own parser, own tests, no dependency on ``Block``
or the render pipeline, matching the shape of ``mermaid_sequence.py``
and ``mermaid_flow.py``.

This module does no layout or rasterization of its own. It parses mermaid
``classDiagram`` source into the *same* :class:`~termrender.renderers.
mermaid_flow_model.FlowGraph` the native flowchart engine consumes — each
UML class becomes a :class:`~termrender.renderers.mermaid_flow_model.
FlowNode` (a compartmented box when the class has a body/annotation, a
plain single-label box otherwise) and each UML relationship becomes a
:class:`~termrender.renderers.mermaid_flow_model.FlowEdge` (arrow-kind
glyphs picked per the UML relation vocabulary) — then hands the graph to
:func:`~termrender.renderers.mermaid_flow_layout.layout_flowgraph`, which
owns grandalf layout, box rasterization, and orthogonal edge routing. See
that module's docstring, and its "UML extension points" section
specifically, for how compartments and arrow kinds render.

Grammar supported
------------------
- Header: ``classDiagram`` / ``classDiagram-v2``. Optional ``direction
  TB``/``TD``/``LR``/``RL``/``BT`` statement (``TD`` normalizes to ``TB``);
  defaults to ``TB``.
- Class blocks: ``class Name { ... }``, either as a single line
  (``class Name { +field type; +method() }``, ``;``-separated members) or
  spanning multiple lines up to a standalone ``}``. A member line with a
  literal ``(`` is a method, otherwise a field — mermaid's own convention
  (``+String owner`` is a field, ``+deposit(amount) bool`` is a method).
  Visibility markers (``+ - # ~``) are kept verbatim as typed; no semantic
  meaning is attached to them beyond display. A ``<<Stereotype>>`` line
  inside the block is an annotation (rendered ``«Stereotype»`` above the
  class name), not a member.
- Member association: ``Name : +method()`` — appends one member to a class
  without an explicit block (same field/method classification as inside a
  block).
- Bare class declaration: ``class Name`` (no body) and standalone
  annotation: ``<<Interface>> Name``.
- Generics: ``List~T~`` (anywhere — class name or member text) renders as
  ``List<T>``.
- Relationships, both writing directions accepted (``<|--`` / ``--|>`` mean
  the same thing, marker on whichever side): inheritance (``<|--``/``--|>``,
  hollow triangle, solid line), realization (``<|..``/``..|>``, hollow
  triangle, dashed line), composition (``*--``/``--*``, filled diamond),
  aggregation (``o--``/``--o``, hollow diamond), association (``-->``/
  ``<--``, filled arrow), dependency (``..>``/``<..``, dashed filled
  arrow), plus the two headless forms (``--`` solid link, ``..`` dashed
  link). Optional quoted cardinalities on either side
  (``A "1" --> "many" B``) and a trailing ``: label`` combine into one
  edge label (``"1 label many"``, extra-empty parts dropped) — the engine
  centers this single combined label on the edge's longest straight run;
  the UML convention of a cardinality glyph pinned at each endpoint
  separately isn't supported (see *Known degradations*).
- ``%%`` comments and well-formed presentational directives (``classDef``/
  ``style``/``cssClass``/``accTitle``/``accDescr``) are dropped.

Never crashes: any unparseable input (missing header, or a parse/layout
exception) degrades to a **raw echo** of the source lines with no
box-drawing/geometric glyphs (same contract, same glyph ranges, as
``mermaid_flow.py`` — see that module's docstring for why this exact
degradation matters to the crouter attach viewer).

Known degradations (by design, not bugs)
-----------------------------------------
- Cardinalities and a relation label are combined into a single label
  string centered on the edge, not three independently-placed annotations
  (per-endpoint cardinality glyphs, common in dedicated UML tools) — the
  underlying engine places one label per edge.
- ``note`` statements, `<<...>>` generic constraints beyond the ``~T~``
  substitution, and class-diagram namespaces are not recognized; they
  raise ``ClassDiagramError`` and the public renderer raw-echoes instead
  of half-rendering the diagram.
- See ``mermaid_flow_layout.py``'s docstring for the inherited engine
  degradations (dense-graph crossings, CJK wrap width, minimum-box-size
  cosmetics) — this renderer's output goes through the same rasterizer and
  router as flowcharts.
"""

from __future__ import annotations

import re

from termrender.renderers.mermaid_degradation import raw_echo
from termrender.renderers.mermaid_flow_layout import layout_flowgraph
from termrender.renderers.mermaid_flow_model import (
    Direction,
    EdgeStyle,
    FlowEdge,
    FlowGraph,
    FlowNode,
    NodeShape,
)
from termrender.renderers.mermaid_prelude import strip_prelude_lines

__all__ = ["render_class", "ClassDiagramError"]


class ClassDiagramError(Exception):
    """Raised when source cannot be parsed as a mermaid class diagram at all."""


# --------------------------------------------------------------------------
# Grammar
# --------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^classDiagram(?:-v2)?\b", re.IGNORECASE)
_DIRECTION_RE = re.compile(r"^direction\s+(TB|TD|LR|RL|BT)\b", re.IGNORECASE)
_COMMENT_RE = re.compile(r"^%%")
_CLASSDEF_RE = re.compile(r"^classDef\b\s+\S+\s+\S.*$", re.IGNORECASE)
_STYLE_RE = re.compile(r"^style\b\s+\S+\s+\S.*$", re.IGNORECASE)
_CSSCLASS_RE = re.compile(
    r'^cssClass\b\s+(?:"[^"]+"|\S+)(?:\s*,\s*(?:"[^"]+"|\S+))*\s+\S+\s*$',
    re.IGNORECASE,
)
_ACCTITLE_RE = re.compile(r"^accTitle\b\s*:?\s+\S.*$", re.IGNORECASE)
_ACCDESCR_RE = re.compile(r"^accDescr\b\s*:?\s+\S.*$", re.IGNORECASE)
_CLASS_ASSIGN_RE = re.compile(
    r"^class\b\s+(?:\S+(?:\s*,\s*\S+)*)\s+(?!\{)\S+\s*$", re.IGNORECASE
)
_CLASS_SHORTHAND_RE = re.compile(r"^class\b\s+\S+:::\S+\s*$", re.IGNORECASE)
_BODY_DIRECTIVE_RE = re.compile(
    r"^(?:classDef|class|style|cssClass|accTitle|accDescr)\b", re.IGNORECASE
)

_CLASS_OPEN_RE = re.compile(r"^class\s+(\S+)\s*\{(.*)$")
_CLASS_BARE_RE = re.compile(r"^class\s+(\S+)\s*$")
_ANNOTATION_STANDALONE_RE = re.compile(r"^<<(.+?)>>\s+(\S+)\s*$")
_ANNOTATION_ONLY_RE = re.compile(r"^<<(.+?)>>\s*$")
_MEMBER_ASSOC_RE = re.compile(r'^(?P<id>[^\s"]+)\s*:\s*(?P<member>.+)$')

_GENERIC_RE = re.compile(r"~([^~]*)~")

# Relation operator: an optional left head marker, a >=2-run dash/dot core
# (dash = solid, dot = dashed), an optional right head marker. Searched
# against a quote-masked copy of the line (see _mask_quotes) so a quoted
# range cardinality like "0..1" is never mistaken for the operator itself.
_OP_RE = re.compile(r"(?P<lhead><\||\*|o|<)?(?P<core>-{2,}|\.{2,})(?P<rhead>\|>|\*|o|>)?")
_REL_LEFT_RE = re.compile(r'^\s*(?P<id>[^\s"]+)\s*(?:"(?P<card>[^"]*)")?\s*$')
_REL_RIGHT_RE = re.compile(
    r'^\s*(?:"(?P<card>[^"]*)")?\s*(?P<id>[^\s":]+)\s*(?::\s*(?P<label>.*))?$'
)


class _ClassDef:
    """Mutable parse-time record for one UML class — converted to a
    :class:`FlowNode` at the end of parsing (see :func:`_build_graph`)."""

    __slots__ = ("id", "display_name", "annotations", "fields", "methods", "has_block")

    def __init__(self, id_: str, display_name: str) -> None:
        self.id = id_
        self.display_name = display_name
        self.annotations: list[str] = []
        self.fields: list[str] = []
        self.methods: list[str] = []
        self.has_block = False


def _format_generics(text: str) -> str:
    """``List~T~`` -> ``List<T>`` (also handles multi-param ``Map~K, V~``)."""
    return _GENERIC_RE.sub(r"<\1>", text)


def _strip_generics_id(token: str) -> str:
    """The graph-key id for a (possibly generic) class token: everything
    before the first ``~``, so ``Stack~T~`` and a later bare ``Stack``
    reference resolve to the same node."""
    return token.split("~", 1)[0]


def _mask_quotes(line: str) -> str:
    """Replace every quoted span with same-length filler so a quoted range
    cardinality (``"0..1"``) can never be mistaken for the relation
    operator when searching for it (see ``_OP_RE``); positions in the
    masked string stay valid indices into the original line."""
    return re.sub(r'"[^"]*"', lambda m: "Q" * len(m.group(0)), line)


def _get_or_create(classes: dict[str, _ClassDef], token: str) -> _ClassDef:
    cid = _strip_generics_id(token)
    cls = classes.get(cid)
    if cls is None:
        cls = _ClassDef(cid, _format_generics(token))
        classes[cid] = cls
    elif "~" in token:
        cls.display_name = _format_generics(token)
    return cls


def _is_presentational_line(line: str) -> bool:
    return any(
        regex.match(line)
        for regex in (
            _CLASSDEF_RE,
            _STYLE_RE,
            _CSSCLASS_RE,
            _ACCTITLE_RE,
            _ACCDESCR_RE,
            _CLASS_ASSIGN_RE,
            _CLASS_SHORTHAND_RE,
        )
    )


def _consume_block_text(cls: _ClassDef, text: str) -> None:
    for part in text.split(";"):
        part = part.strip()
        if part and _BODY_DIRECTIVE_RE.match(part):
            raise ClassDiagramError(
                f"unrecognized class diagram statement: {part!r}"
            )
    _consume_members(cls, text)


def _consume_members(cls: _ClassDef, text: str) -> None:
    """Split ``text`` (one physical line, or the inline body of a
    ``class Name { ... }`` opener/closer) on ``;`` into individual member/
    annotation statements and file each into ``cls``."""
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        am = _ANNOTATION_ONLY_RE.match(part)
        if am:
            cls.annotations.append(am.group(1).strip())
            continue
        formatted = _format_generics(part)
        if "(" in formatted:
            cls.methods.append(formatted)
        else:
            cls.fields.append(formatted)


_ARROW_KIND = {
    "<|": "triangle_hollow",
    "|>": "triangle_hollow",
    "*": "diamond_filled",
    "o": "diamond_hollow",
    "<": "default",
    ">": "default",
}


def _try_relation(
    line: str, classes: dict[str, _ClassDef], edges: list[FlowEdge]
) -> bool:
    masked = _mask_quotes(line)
    m = _OP_RE.search(masked)
    if not m or not (m.group("lhead") or m.group("rhead") or m.group("core")):
        return False

    left_text, right_text = line[: m.start()], line[m.end() :]
    lm = _REL_LEFT_RE.match(left_text)
    rm = _REL_RIGHT_RE.match(right_text)
    if not lm or not rm:
        return False

    src_token, dst_token = lm.group("id"), rm.group("id")
    src = _get_or_create(classes, src_token)
    dst = _get_or_create(classes, dst_token)

    style = EdgeStyle.DOTTED if m.group("core").startswith(".") else EdgeStyle.SOLID
    lhead, rhead = m.group("lhead"), m.group("rhead")
    src_arrow, dst_arrow = lhead is not None, rhead is not None
    src_kind = _ARROW_KIND.get(lhead, "default")
    dst_kind = _ARROW_KIND.get(rhead, "default")

    # Cardinalities read src-side then dst-side, with the relation label
    # (if any) sitting between them — combined into one string so a
    # labeled+cardinalitied edge reads "1 contains many", not
    # "1 many contains" (the underlying engine centers one label per edge).
    src_card, dst_card = lm.group("card"), rm.group("card")
    label_text = rm.group("label")
    ordered = [p for p in (src_card, label_text, dst_card) if p]
    label = " ".join(ordered) if ordered else None

    edges.append(
        FlowEdge(
            src=src.id,
            dst=dst.id,
            style=style,
            label=_format_generics(label) if label else None,
            dst_arrow=dst_arrow,
            src_arrow=src_arrow,
            dst_arrow_kind=dst_kind,
            src_arrow_kind=src_kind,
        )
    )
    return True


def _build_graph(source: str) -> FlowGraph:
    lines = source.splitlines()
    sniff_lines = strip_prelude_lines(lines)
    first = next((line.strip() for line in sniff_lines if line.strip()), "")
    if not _HEADER_RE.match(first):
        raise ClassDiagramError(
            "not a mermaid class diagram: source must start with 'classDiagram'"
        )

    direction = Direction.TB
    classes: dict[str, _ClassDef] = {}
    edges: list[FlowEdge] = []
    seen_header = False
    block_cls: _ClassDef | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        if block_cls is not None:
            if _COMMENT_RE.match(line):
                continue
            if line.endswith("}"):
                body = line[:-1].rstrip()
                if body:
                    _consume_block_text(block_cls, body)
                block_cls = None
            else:
                _consume_block_text(block_cls, line)
            continue

        if not seen_header:
            if _HEADER_RE.match(line):
                seen_header = True
            continue

        if _COMMENT_RE.match(line) or _is_presentational_line(line):
            continue

        dm = _DIRECTION_RE.match(line)
        if dm:
            token = dm.group(1).upper()
            direction = Direction.TB if token == "TD" else Direction(token)
            continue

        om = _CLASS_OPEN_RE.match(line)
        if om:
            name_token, inline_body = om.group(1), om.group(2)
            cls = _get_or_create(classes, name_token)
            cls.has_block = True
            body = inline_body.rstrip()
            if body.endswith("}"):
                _consume_block_text(cls, body[:-1])
            else:
                _consume_block_text(cls, body)
                block_cls = cls
            continue

        bm = _CLASS_BARE_RE.match(line)
        if bm:
            _get_or_create(classes, bm.group(1))
            continue

        am = _ANNOTATION_STANDALONE_RE.match(line)
        if am:
            cls = _get_or_create(classes, am.group(2))
            cls.annotations.append(am.group(1).strip())
            continue

        if _try_relation(line, classes, edges):
            continue

        mm = _MEMBER_ASSOC_RE.match(line)
        if mm:
            cls = _get_or_create(classes, mm.group("id"))
            cls.has_block = True
            _consume_members(cls, mm.group("member"))
            continue

        if _CLASS_ASSIGN_RE.match(line) or _CLASS_SHORTHAND_RE.match(line):
            continue

        raise ClassDiagramError(f"unrecognized class diagram statement: {line!r}")

    if block_cls is not None:
        raise ClassDiagramError("unterminated class body")

    if not seen_header:
        raise ClassDiagramError(
            "not a mermaid class diagram: source must start with 'classDiagram'"
        )

    nodes: list[FlowNode] = []
    for cls in classes.values():
        name_lines = [f"\u00ab{a}\u00bb" for a in cls.annotations] + [cls.display_name]
        if cls.has_block:
            compartments = [name_lines, cls.fields or [""], cls.methods or [""]]
        elif cls.annotations:
            compartments = [name_lines]
        else:
            compartments = None
        nodes.append(
            FlowNode(
                id=cls.id,
                label=cls.display_name,
                shape=NodeShape.RECT,
                compartments=compartments,
            )
        )

    return FlowGraph(direction=direction, nodes=nodes, edges=edges, subgraphs=[])


def render_class(source: str, width: int) -> list[str]:
    """Render a mermaid ``classDiagram`` source to unicode lines.

    Pure and total: never raises. Degrades to a raw echo of ``source``
    (see the module docstring's "Never crashes" note) when the source
    isn't a class diagram at all, parses to zero classes, or an
    unexpected exception escapes layout.

    Args:
        source: The mermaid fence body (with or without surrounding fence
            markers — only the text between them).
        width: Terminal width budget in cells. It reaches the flowchart
            engine's label-narrowing width fit, which only affects the
            plain single-label boxes (a class with no members and no
            annotation); a compartmented class's lines are pre-formatted
            here and size to content, so a diagram of those may overflow.

    Returns:
        Rendered lines on success (guaranteed to contain box-drawing
        glyphs), or a raw echo of ``source`` on any degradation path.
    """
    try:
        graph = _build_graph(source)
    except ClassDiagramError:
        return raw_echo(source)

    if not graph.nodes:
        return raw_echo(source)

    try:
        lines = layout_flowgraph(graph, width)
    except Exception:
        return raw_echo(source)

    if not lines:
        return raw_echo(source)

    return lines
