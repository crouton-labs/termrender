"""Mermaid diagram renderer for termrender."""

from __future__ import annotations

import re

from termrender.blocks import Block
from termrender.renderers import (
    mermaid_class,
    mermaid_er,
    mermaid_flow,
    mermaid_gantt,
    mermaid_journey,
    mermaid_mindmap,
    mermaid_pie,
    mermaid_sequence,
    mermaid_state,
    mermaid_timeline,
)
from termrender.renderers.mermaid_prelude import strip_prelude_lines
from termrender.style import visual_ljust

# Same box-drawing/geometric glyph ranges the native renderers (mermaid_flow,
# mermaid_class, mermaid_state, mermaid_er) guard their own raw-echo paths
# with, and the same ranges the downstream crouter viewer keys on to detect
# render *success*. An exotic/unrecognized diagram type has no renderer at
# all, so its degradation lives here rather than in a shared renderer module;
# it must uphold the identical contract — no such glyph survives the echo,
# even one present verbatim in the source itself.
_GLYPH_RANGE_RE = re.compile("[\u2500-\u259f\u25a0-\u25ff]")


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


def _raw_echo(source: str) -> list[str]:
    """Degrade an exotic/unrecognized diagram type to its raw source lines.

    No renderer exists for these types (sankey, C4, gitgraph, block, packet,
    kanban, quadrantChart, …, and anything unrecognized): the source is
    echoed back verbatim, with box-drawing/geometric glyphs neutralized so
    the crouter viewer's "no glyphs survived" success check can't be fooled
    by one present in the raw source itself — the same guarantee every
    native renderer's own raw-echo path upholds.
    """
    return [
        _GLYPH_RANGE_RE.sub("?", line.rstrip()) for line in source.splitlines()
    ]


def render_mermaid_lines(source: str, width: int) -> list[str]:
    """Dispatch a mermaid source to its type's renderer and return raw lines.

    Every diagram type mermaid supports that termrender renders has a
    dedicated native Python renderer: ``pie``, ``gantt``, ``sequenceDiagram``,
    ``mindmap``, ``journey``, ``timeline``, ``graph``/``flowchart``,
    ``classDiagram``, ``stateDiagram``/``stateDiagram-v2``, and ``erDiagram``.
    Any other type (sankey, C4, gitgraph, block, packet, kanban, …, or
    anything unrecognized) degrades to a raw echo of the source with no
    box-drawing glyphs — see :func:`_raw_echo`. Lines are returned unpadded;
    callers apply width padding uniformly.
    """
    diagram_type = _first_line_type(source)
    if diagram_type.startswith("pie"):
        return mermaid_pie.render(source, width)
    if diagram_type.startswith("gantt"):
        return mermaid_gantt.render(source, width)
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
    return _raw_echo(source)


def render(block: Block, color: bool) -> list[str]:
    """Render a mermaid diagram from pre-rendered or on-the-fly ASCII output."""
    w = block.width
    rendered = block.attrs.get("_rendered")

    if rendered is None:
        source = block.attrs.get("source", "")
        raw_lines = render_mermaid_lines(source, w or 60)
    else:
        raw_lines = rendered.split("\n")

    return [visual_ljust(raw_line, w) for raw_line in raw_lines]
