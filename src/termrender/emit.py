"""AST walker that dispatches laid-out blocks to renderers."""

from __future__ import annotations

from termrender.blocks import Block, BlockType, Span
from termrender.renderers import (
    panel, columns, tree, code, text, divider, quote, mermaid, arrow_chain, table,
    diff, charts, stat, timeline,
)
from termrender.style import visual_ljust


def emit_block(block: Block, color: bool) -> list[str]:
    """Render a single block and its children, returning output lines."""
    match block.type:
        case BlockType.DOCUMENT:
            # Insert a blank padded line between top-level siblings so
            # paragraphs, headings, and blocks don't visually run together.
            lines: list[str] = []
            sep = visual_ljust("", block.width or 0)
            for i, child in enumerate(block.children):
                if i > 0:
                    lines.append(sep)
                lines.extend(emit_block(child, color))
            return lines

        case BlockType.COL:
            lines: list[str] = []
            for child in block.children:
                lines.extend(emit_block(child, color))
            return lines

        case BlockType.PANEL:
            return panel.render(block, color, render_child=emit_block)

        case BlockType.CALLOUT:
            return panel.render_callout(block, color, render_child=emit_block)

        case BlockType.COLUMNS:
            return columns.render(block, color, render_child=emit_block)

        case BlockType.QUOTE:
            return quote.render(block, color, render_child=emit_block)

        case BlockType.CODE:
            return code.render(block, color, render_child=emit_block)

        case BlockType.PARAGRAPH | BlockType.HEADING | BlockType.LIST | BlockType.LIST_ITEM:
            return text.render(block, color)

        case BlockType.TREE:
            return tree.render(block, color)

        case BlockType.MERMAID:
            return mermaid.render(block, color)

        case BlockType.ARROW_CHAIN:
            return arrow_chain.render(block, color)

        case BlockType.TABLE:
            return table.render(block, color)

        case BlockType.DIVIDER:
            return divider.render(block, color)

        case BlockType.DIFF:
            return diff.render(block, color)

        case BlockType.BAR:
            return charts.render_bar(block, color)

        case BlockType.PROGRESS:
            return charts.render_progress(block, color)

        case BlockType.GAUGE:
            return charts.render_gauge(block, color)

        case BlockType.STAT:
            return stat.render(block, color, render_child=emit_block)

        case BlockType.TIMELINE:
            return timeline.render(block, color)

        case _:
            return []


def emit(doc: Block, color: bool) -> str:
    """Walk the block tree and return the fully rendered string."""
    lines = emit_block(doc, color)
    return "\n".join(lines)


def _emit_block_with_spans(block: Block, color: bool) -> tuple[list[str], list[Span]]:
    """Render one top-level block, also returning per-row leaf source spans.

    Lists, tables, and code blocks resolve rows to their finest known source
    unit (item / table row / content line); every other type resolves to the
    block's own range. The span-aware renderers share the plain render code
    path, so lines stay byte-identical to emit_block.
    """
    own: Span = (
        (block.src_start, block.src_end)
        if block.src_start is not None and block.src_end is not None
        else None
    )
    match block.type:
        case BlockType.LIST | BlockType.LIST_ITEM:
            return text.render_with_spans(block, color, own)
        case BlockType.TABLE:
            return table.render_with_spans(block, color, own)
        case BlockType.CODE:
            return code.render_with_spans(block, color, emit_block, own)
        case _:
            lines = emit_block(block, color)
            return lines, [own] * len(lines)


def emit_with_map(doc: Block, color: bool) -> tuple[list[str], list[int | None], list[Span]]:
    """Render a DOCUMENT block, also returning per-row block and span maps.

    Returns (lines, row_map, spans): row_map[i] is the index into doc.children
    of the top-level block that produced lines[i] (None for the separator rows
    between siblings); spans[i] is that row's finest known 1-indexed inclusive
    source range (None for separators and unmapped blocks). Must mirror
    emit_block's DOCUMENT case exactly so the mapped output is byte-identical
    to the unmapped render.
    """
    lines: list[str] = []
    row_map: list[int | None] = []
    spans: list[Span] = []
    sep = visual_ljust("", doc.width or 0)
    for i, child in enumerate(doc.children):
        if i > 0:
            lines.append(sep)
            row_map.append(None)
            spans.append(None)
        child_lines, child_spans = _emit_block_with_spans(child, color)
        lines.extend(child_lines)
        row_map.extend([i] * len(child_lines))
        spans.extend(child_spans)
    return lines, row_map, spans
