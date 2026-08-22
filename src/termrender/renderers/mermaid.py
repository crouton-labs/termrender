"""Mermaid diagram renderer for termrender."""

from __future__ import annotations

from termrender.blocks import Block
from termrender.renderers import (
    mermaid_class,
    mermaid_er,
    mermaid_flow,
    mermaid_gantt,
    mermaid_gitgraph,
    mermaid_journey,
    mermaid_mindmap,
    mermaid_pie,
    mermaid_sequence,
    mermaid_state,
    mermaid_timeline,
)
from termrender.renderers.mermaid_degradation import raw_echo
from termrender.renderers.mermaid_prelude import strip_prelude_lines
from termrender.style import ANSI_RE, visual_ljust


def _first_line_type(source: str) -> str:
    """Return the lowercased first real line's leading keyword.

    This is the dispatch key: mermaid identifies a diagram's type from its
    first line (``graph``/``flowchart``, ``pie``, ``gantt``, ``sequenceDiagram``,
    ``classDiagram``, ``stateDiagram``, ``erDiagram``, …), after skipping any
    prelude (blank lines, ``%%`` comments/directives, ``---`` YAML
    frontmatter — see ``mermaid_prelude.py``). Returns ``""`` for a source
    with no real content past its prelude.
    """
    lines = strip_prelude_lines(source.splitlines())
    first = next((l.strip() for l in lines if l.strip()), "")
    return first.lower()


def _stripped(source: str) -> str:
    """Return ``source`` with its leading prelude (comments/directives/
    frontmatter) removed, for native renderers that don't otherwise skip it.
    """
    return "\n".join(strip_prelude_lines(source.splitlines()))


def render_mermaid_lines(source: str, width: int) -> list[str]:
    """Dispatch a mermaid source to its type's renderer and return raw lines.

    Every diagram type mermaid supports that termrender renders has a
    dedicated native Python renderer: ``pie``, ``gantt``, ``gitGraph``,
    ``sequenceDiagram``, ``mindmap``, ``journey``, ``timeline``,
    ``graph``/``flowchart``, ``classDiagram``, ``stateDiagram``/``stateDiagram-v2``,
    and ``erDiagram``. Any other type (sankey, C4, block, packet, kanban, …,
    or anything unrecognized) degrades to a raw echo of the source with no
    box-drawing glyphs — see :func:`~termrender.renderers.mermaid_degradation.
    raw_echo`. Lines are returned unpadded; callers apply width padding
    uniformly.
    """
    diagram_type = _first_line_type(source)
    if diagram_type.startswith("pie"):
        return mermaid_pie.render(source, width)
    if diagram_type.startswith("gantt"):
        return mermaid_gantt.render(source, width)
    if diagram_type.startswith("gitgraph"):
        return mermaid_gitgraph.render(source, width)
    if diagram_type.startswith("sequencediagram"):
        return mermaid_sequence.render_sequence(source, width)
    if diagram_type.startswith("mindmap"):
        return mermaid_mindmap.render(_stripped(source), width)
    if diagram_type.startswith("journey"):
        return mermaid_journey.render(_stripped(source), width)
    if diagram_type.startswith("timeline"):
        return mermaid_timeline.render(_stripped(source), width)
    if diagram_type.startswith(("graph", "flowchart")):
        return mermaid_flow.render_flowchart(source, width)
    if diagram_type.startswith("classdiagram"):
        return mermaid_class.render_class(source, width)
    if diagram_type.startswith("statediagram"):
        return mermaid_state.render_state(source, width)
    if diagram_type.startswith("erdiagram"):
        return mermaid_er.render_er(source, width)
    return raw_echo(source)


def render(block: Block, color: bool) -> list[str]:
    """Render a mermaid diagram from pre-rendered or on-the-fly ASCII output.

    ``color`` gates styling but never geometry. The diagram is always laid
    out styled — a label's emphasis runs are ANSI escapes, which cost no
    display columns — so the boxes, borders and line routing are identical
    either way, and turning color off is exactly dropping the escapes. That
    keeps the width pass color-blind, which is the only way ``--color on``
    and ``--color off`` can be guaranteed to produce the same layout.
    """
    w = block.width
    rendered = block.attrs.get("_rendered")

    if rendered is None:
        source = block.attrs.get("source", "")
        raw_lines = render_mermaid_lines(source, w or 60)
    else:
        raw_lines = rendered.split("\n")

    if not color:
        raw_lines = [ANSI_RE.sub("", raw_line) for raw_line in raw_lines]

    return [visual_ljust(raw_line, w) for raw_line in raw_lines]
