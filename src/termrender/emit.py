"""AST walker that dispatches laid-out blocks to renderers."""

from __future__ import annotations

from termrender.blocks import Block, BlockType
from termrender.renderers import panel, columns, tree, code, text, divider, quote, mermaid, table


def emit_block(block: Block, color: bool) -> list[str]:
    """Render a single block and its children, returning output lines."""
    match block.type:
        case BlockType.DOCUMENT | BlockType.COL:
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

        case BlockType.TABLE:
            return table.render(block, color)

        case BlockType.DIVIDER:
            return divider.render(block, color)

        case _:
            return []


def emit(doc: Block, color: bool) -> str:
    """Walk the block tree and return the fully rendered string."""
    lines = emit_block(doc, color)
    return "\n".join(lines)
