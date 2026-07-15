"""Render a terse Unicode-arrow process chain with the flowchart layout engine.

A single text line such as ``Core → edge token → guest authorization`` is a
common agent output: the order is the whole structure, but Mermaid identifiers
and node declarations obscure it. This module recognizes only that narrow,
unambiguous form and turns it into a left-to-right ``FlowGraph``.
"""

from __future__ import annotations

import re

from termrender.blocks import Block
from termrender.renderers.mermaid_degradation import raw_echo
from termrender.renderers.mermaid_flow_layout import layout_flowgraph
from termrender.renderers.mermaid_flow_model import Direction, FlowEdge, FlowGraph, FlowNode
from termrender.style import visual_ljust

__all__ = ["parse_arrow_chain", "render_arrow_chain", "render"]


_ARROW_SPLIT = re.compile(r"\s*(?:→|⟶|⇒|⟹)\s*")
_CODE_PUNCTUATION = re.compile(r"[=;{}\[\]`]")


def parse_arrow_chain(source: str) -> list[str] | None:
    """Return the ordered stages of one Unicode-arrow chain, if ``source`` is one.

    The strict one-line, three-stage form keeps ordinary fenced code verbatim.
    Each stage must contain visible text without code punctuation.
    """
    line = source.strip()
    if not line or "\n" in line:
        return None
    stages = _ARROW_SPLIT.split(line)
    if len(stages) < 3:
        return None
    if any(not stage.strip() or _CODE_PUNCTUATION.search(stage) for stage in stages):
        return None
    if not _ARROW_SPLIT.search(line):
        return None
    return [stage.strip() for stage in stages]


def render_arrow_chain(source: str, width: int) -> list[str]:
    """Render a valid arrow chain as a left-to-right graph, never raising."""
    stages = parse_arrow_chain(source)
    if stages is None:
        return raw_echo(source)

    nodes = [FlowNode(id=f"stage_{i}", label=stage) for i, stage in enumerate(stages)]
    edges = [FlowEdge(src=nodes[i].id, dst=nodes[i + 1].id) for i in range(len(nodes) - 1)]
    graph = FlowGraph(direction=Direction.LR, nodes=nodes, edges=edges)

    try:
        lines = layout_flowgraph(graph, width)
    except Exception:
        return raw_echo(source)
    return lines or raw_echo(source)


def render(block: Block, color: bool) -> list[str]:
    """Emit a parsed arrow-chain block, reusing its layout-pass result."""
    source = block.attrs.get("source", "")
    rendered = block.attrs.get("_rendered")
    lines = rendered.split("\n") if rendered is not None else render_arrow_chain(source, block.width or 1)
    return [visual_ljust(line, block.width or 1) for line in lines]
