"""Native renderer for mermaid ``erDiagram`` sources.

Standalone module: exposes a single pure function, :func:`render_er`.
Wired into ``mermaid.py``'s dispatcher alongside the other native mermaid
renderers. Own parser, own tests, no dependency on ``Block`` or the render
pipeline, matching the shape of ``mermaid_class.py`` and
``mermaid_flow.py``.

This module does no layout or rasterization of its own. It parses mermaid
``erDiagram`` source into the *same* :class:`~termrender.renderers.
mermaid_flow_model.FlowGraph` the native flowchart engine consumes — each
ER entity becomes a :class:`~termrender.renderers.mermaid_flow_model.
FlowNode` (a compartmented box when the entity has an attribute block, a
plain single-label box otherwise) and each ER relationship becomes a
:class:`~termrender.renderers.mermaid_flow_model.FlowEdge` (a plain,
headless line — ER cardinality is drawn as edge-label text, not an
arrowhead glyph family) — then hands the graph to
:func:`~termrender.renderers.mermaid_flow_layout.layout_flowgraph`, which
owns grandalf layout, box rasterization, and orthogonal edge routing. See
that module's docstring for how compartments render.

Grammar supported
------------------
- Header: ``erDiagram``. Diagram direction is always top-to-bottom
  (mermaid's erDiagram has no ``direction`` statement of its own, unlike
  flowcharts/class diagrams).
- Entity blocks: ``ENTITY { ... }``, either as a single line
  (``CUSTOMER { string name PK }``) or spanning multiple lines up to a
  standalone ``}``. Each attribute line is ``type name [PK|FK|UK[, ...]]
  ["comment"]`` — type and name are required, the key marker(s) and the
  trailing quoted comment are both optional. The comment is parsed (so it
  doesn't corrupt the match) but dropped from the rendered row — see
  *Known degradations*.
- Bare entity declarations: ``ENTITY`` on its own line, and entities
  referenced only from a relationship line (never given a block) — both
  render as a plain single-label box (no compartments), matching
  ``mermaid_class.py``'s bare-class handling.
- Entity/attribute aliases: ``p[Person]`` (id ``p``, displayed as
  ``Person``) and quoted names/ids containing spaces or punctuation
  (``"driver's license"``, ``"Order Item"[OI]``) are recognized wherever
  an entity token or an attribute name appears; the quotes are stripped
  for display, the unquoted text is the graph key.
- Relationships: ``ENTITY1 <left-card><line><right-card> ENTITY2 :
  label``. ``<line>`` is ``--`` (identifying) or ``..`` (non-identifying);
  identifying relationships render as a solid line, non-identifying as a
  dashed line (:class:`EdgeStyle.DOTTED`, same glyphs the class-diagram
  renderer uses for realization/dependency). ``<left-card>``/
  ``<right-card>`` are mermaid's crow's-foot pairs read next to their
  adjacent entity — ``||`` exactly one, ``o|``/``|o`` zero-or-one,
  ``}|``/``|{`` one-or-more, ``}o``/``o{`` zero-or-more (both writing
  directions accepted, per mermaid's own grammar) — translated to text
  markers ``1``, ``0..1``, ``1..*``, ``0..*`` and combined with the
  optional ``: label`` into one string (``"1 places 0..*"``), centered on
  the edge by the engine. Relationship lines never draw an arrowhead
  (``dst_arrow``/``src_arrow`` both ``False``) — ER cardinality is
  conveyed entirely by the label text, not by a glyph family, since crow's
  foot notation has no equivalent among the engine's existing arrow-kind
  glyphs (see *Known degradations*).
- ``%%`` comments are dropped.

Never crashes: any unparseable input (missing header, or a parse/layout
exception) degrades to a **raw echo** of the source lines with no
box-drawing/geometric glyphs (same contract, same glyph ranges, as
``mermaid_flow.py`` and ``mermaid_class.py`` — see those modules'
docstrings for why this exact degradation matters to the crouter attach
viewer).

Known degradations (by design, not bugs)
-----------------------------------------
- Cardinality and the relation label are combined into a single string
  centered on the edge (``"1 places 0..*"``), not three independently
  placed annotations (one marker pinned at each endpoint plus a centered
  label, the dedicated-ER-tool convention) — the underlying engine places
  one label per edge, same limitation ``mermaid_class.py`` documents for
  UML cardinalities.
- No crow's-foot glyphs are drawn at the endpoints; cardinality is text
  only. The engine's arrow-kind extension point supports UML triangle/
  diamond families, not a crow's-foot family, and adding one is out of
  scope for this renderer (an engine change, not a parser change).
- Attribute comments (the trailing quoted string in an attribute line)
  are parsed — so they don't break the match or leak into the name/key
  columns — but dropped entirely from the rendered row rather than
  wrapped or truncated onto a second line.
- An entity declared with an empty block (``ENTITY { }``) still gets a
  two-compartment box (title + a single blank attribute row) rather than
  collapsing to a plain box — mirrors ``mermaid_class.py``'s
  always-show-the-band-if-a-block-was-declared behavior for classes with
  an empty fields/methods section.
- See ``mermaid_flow_layout.py``'s docstring for the inherited engine
  degradations (dense-graph crossings, CJK wrap width, minimum-box-size
  cosmetics) — this renderer's output goes through the same rasterizer
  and router as flowcharts and class diagrams.
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

__all__ = ["render_er", "ERDiagramError"]


class ERDiagramError(Exception):
    """Raised when source cannot be parsed as a mermaid ER diagram at all."""


# --------------------------------------------------------------------------
# Grammar
# --------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^erDiagram\b", re.IGNORECASE)
_COMMENT_RE = re.compile(r"^%%")
_ACC_RE = re.compile(r"^acc(?:Title|Descr)\b", re.IGNORECASE)

# An entity token: a quoted name (optionally aliased, `"Order Item"[OI]`),
# or a bare run of non-space/non-brace characters (`CUSTOMER`, `p[Person]`,
# `LINE-ITEM`). Used for bare declarations, block openers, and relationship
# endpoints alike (see `_parse_entity_token`). Bare runs exclude `}` so a
# stray block closer can never be mistaken for an entity.
_ENTITY_TOKEN = r'"[^"]*"(?:\[[^\]]*\])?|[^\s{}]+'

_ENTITY_TOKEN_RE = re.compile(r'^(?P<id>"[^"]*"|[^\[\s]+)(?:\[(?P<alias>[^\]]*)\])?$')
_BLOCK_OPEN_RE = re.compile(rf"^(?P<idtok>{_ENTITY_TOKEN})\s*\{{(?P<inline>.*)$")
_BARE_ENTITY_RE = re.compile(rf"^(?P<idtok>{_ENTITY_TOKEN})\s*$")

# Attribute line: `type name [PK|FK|UK[, ...]] ["comment"]`. The comment is
# matched (so it can't corrupt the name/keys columns) but never rendered.
_ATTR_RE = re.compile(
    r'^(?P<type>\S+)\s+(?P<name>"[^"]*"|\S+)'
    r"(?:\s+(?P<keys>(?:PK|FK|UK)(?:\s*,\s*(?:PK|FK|UK))*))?"
    r'(?:\s+"[^"]*")?\s*$',
    re.IGNORECASE,
)

# Relationship operator: a left crow's-foot pair, a >=2-run dash/dot core
# (dash = identifying/solid, dot = non-identifying/dashed), a right
# crow's-foot pair. Searched against a quote-masked copy of the line (see
# `_mask_quotes`) so a quoted entity/attribute name can never be mistaken
# for the operator.
_LEFT_CARD = r"\|o|\|\||\}o|\}\|"
_RIGHT_CARD = r"o\||\|\||o\{|\|\{"
_REL_OP_RE = re.compile(rf"(?P<left>{_LEFT_CARD})(?P<mid>--|\.\.)(?P<right>{_RIGHT_CARD})")
_REL_LEFT_RE = re.compile(rf"^\s*(?P<idtok>{_ENTITY_TOKEN})\s*$")
_REL_RIGHT_RE = re.compile(rf"^\s*(?P<idtok>{_ENTITY_TOKEN})\s*(?::\s*(?P<label>.*))?$")

# Crow's-foot pair -> cardinality text, read from mermaid's own vocabulary
# (both writing directions map to the same text on the side they sit next
# to).
_CARD_LEFT = {"|o": "0..1", "||": "1", "}o": "0..*", "}|": "1..*"}
_CARD_RIGHT = {"o|": "0..1", "||": "1", "o{": "0..*", "|{": "1..*"}


class _Entity:
    """Mutable parse-time record for one ER entity — converted to a
    :class:`FlowNode` at the end of parsing (see :func:`_build_graph`)."""

    __slots__ = ("id", "display_name", "attrs", "has_block")

    def __init__(self, id_: str, display_name: str) -> None:
        self.id = id_
        self.display_name = display_name
        self.attrs: list[str] = []
        self.has_block = False


def _unquote(s: str) -> str:
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _mask_quotes(line: str) -> str:
    """Replace every quoted span with same-length filler so a quoted entity
    or attribute name can never be mistaken for the relation operator when
    searching for it (see `_REL_OP_RE`); positions in the masked string
    stay valid indices into the original line."""
    return re.sub(r'"[^"]*"', lambda m: "Q" * len(m.group(0)), line)


def _parse_entity_token(token: str) -> tuple[str, str | None]:
    """Split an entity token into its graph-key id and optional display
    alias: ``CUSTOMER`` -> (``CUSTOMER``, None); ``p[Person]`` -> (``p``,
    ``Person``); ``"Order Item"[OI]`` -> (``Order Item``, ``OI``)."""
    m = _ENTITY_TOKEN_RE.match(token.strip())
    if not m:
        return _unquote(token.strip()), None
    alias = m.group("alias")
    return _unquote(m.group("id")), (alias.strip() if alias else None)


def _get_or_create(entities: dict[str, _Entity], token: str) -> _Entity:
    eid, alias = _parse_entity_token(token)
    ent = entities.get(eid)
    if ent is None:
        ent = _Entity(eid, alias or eid)
        entities[eid] = ent
    elif alias:
        ent.display_name = alias
    return ent


def _format_attr_row(m: re.Match[str]) -> str:
    row = f"{m.group('type')} {_unquote(m.group('name'))}"
    keys = m.group("keys")
    if keys:
        norm = re.sub(r"\s*,\s*", ", ", keys.strip()).upper()
        row += f" {norm}"
    return row


def _consume_attrs(entity: _Entity, text: str) -> None:
    """Split ``text`` (one physical line, or the inline body of an
    ``ENTITY { ... }`` opener/closer) on ``;`` into individual attribute
    statements and file each into ``entity``. Any non-empty part that does
    not match the ``type name [keys] [comment]`` grammar raises."""
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        m = _ATTR_RE.match(part)
        if m:
            entity.attrs.append(_format_attr_row(m))
        else:
            raise ERDiagramError(f"unrecognized ER entity attribute: {part!r}")


def _try_relation(
    line: str, entities: dict[str, _Entity], edges: list[FlowEdge]
) -> bool:
    masked = _mask_quotes(line)
    m = _REL_OP_RE.search(masked)
    if not m:
        return False

    left_text, right_text = line[: m.start()], line[m.end() :]
    lm = _REL_LEFT_RE.match(left_text)
    rm = _REL_RIGHT_RE.match(right_text)
    if not lm or not rm:
        return False

    src = _get_or_create(entities, lm.group("idtok"))
    dst = _get_or_create(entities, rm.group("idtok"))

    style = EdgeStyle.DOTTED if m.group("mid") == ".." else EdgeStyle.SOLID
    src_card = _CARD_LEFT.get(m.group("left"))
    dst_card = _CARD_RIGHT.get(m.group("right"))
    label_text = rm.group("label")
    parts = [p for p in (src_card, label_text, dst_card) if p]
    label = " ".join(parts) if parts else None

    edges.append(
        FlowEdge(
            src=src.id,
            dst=dst.id,
            style=style,
            label=label,
            dst_arrow=False,
            src_arrow=False,
        )
    )
    return True


def _build_graph(source: str) -> FlowGraph:
    lines = source.splitlines()
    sniff_lines = strip_prelude_lines(lines)
    first = ""
    for sniff_line in sniff_lines:
        stripped = sniff_line.strip()
        if not stripped or _COMMENT_RE.match(stripped) or _ACC_RE.match(stripped):
            continue
        first = stripped
        break
    if not _HEADER_RE.match(first):
        raise ERDiagramError(
            "not a mermaid ER diagram: source must start with 'erDiagram'"
        )

    entities: dict[str, _Entity] = {}
    edges: list[FlowEdge] = []
    seen_header = False
    block_entity: _Entity | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        if _COMMENT_RE.match(line) or _ACC_RE.match(line):
            continue

        if block_entity is not None:
            if line.endswith("}"):
                _consume_attrs(block_entity, line[:-1])
                block_entity = None
            else:
                _consume_attrs(block_entity, line)
            continue

        if not seen_header:
            if _HEADER_RE.match(line):
                seen_header = True
                continue
            raise ERDiagramError(f"unrecognized ER diagram statement: {line!r}")

        om = _BLOCK_OPEN_RE.match(line)
        if om:
            ent = _get_or_create(entities, om.group("idtok"))
            ent.has_block = True
            body = om.group("inline").rstrip()
            if body.endswith("}"):
                _consume_attrs(ent, body[:-1])
            else:
                _consume_attrs(ent, body)
                block_entity = ent
            continue

        if _try_relation(line, entities, edges):
            continue

        bm = _BARE_ENTITY_RE.match(line)
        if bm:
            _get_or_create(entities, bm.group("idtok"))
            continue

        raise ERDiagramError(f"unrecognized ER diagram statement: {line!r}")

    if block_entity is not None:
        raise ERDiagramError("unterminated entity block")

    if not seen_header:
        raise ERDiagramError(
            "not a mermaid ER diagram: source must start with 'erDiagram'"
        )

    nodes: list[FlowNode] = []
    for ent in entities.values():
        compartments = [[ent.display_name], ent.attrs or [""]] if ent.has_block else None
        nodes.append(
            FlowNode(
                id=ent.id,
                label=ent.display_name,
                shape=NodeShape.RECT,
                compartments=compartments,
            )
        )

    return FlowGraph(direction=Direction.TB, nodes=nodes, edges=edges, subgraphs=[])


def render_er(source: str, width: int) -> list[str]:
    """Render a mermaid ``erDiagram`` source to unicode lines.

    Pure and total: never raises. Degrades to a raw echo of ``source``
    (see the module docstring's "Never crashes" note) when the source
    isn't an ER diagram at all, parses to zero entities, or an unexpected
    exception escapes layout.

    Args:
        source: The mermaid fence body (with or without surrounding fence
            markers — only the text between them).
        width: Terminal width budget in cells. It reaches the flowchart
            engine's label-narrowing width fit, which only affects
            attribute-less entities (those render as plain single-label
            boxes); a compartmented entity's lines are pre-formatted here
            and size to content, so a diagram of those may overflow.

    Returns:
        Rendered lines on success (guaranteed to contain box-drawing
        glyphs), or a raw echo of ``source`` on any degradation path.
    """
    try:
        graph = _build_graph(source)
    except ERDiagramError:
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
