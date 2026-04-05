"""Column layout renderer (DES-008)."""

from __future__ import annotations

from typing import Callable

from termrender.blocks import Block
from termrender.style import visual_ljust


def render(block: Block, color: bool, render_child: Callable[[Block, bool], list[str]]) -> list[str]:
    """Render a COLUMNS block by zipping child COL blocks horizontally."""
    col_outputs: list[tuple[int, list[str]]] = []
    max_height = 0

    for col in block.children:
        lines = render_child(col, color)
        col_outputs.append((col.width, lines))
        if len(lines) > max_height:
            max_height = len(lines)

    if not col_outputs:
        return [' ' * block.width] if block.width else ['']

    result: list[str] = []
    for row in range(max_height):
        parts: list[str] = []
        for col_width, lines in col_outputs:
            line = lines[row] if row < len(lines) else ''
            parts.append(visual_ljust(line, col_width))
        joined = ' '.join(parts)
        result.append(visual_ljust(joined, block.width))

    return result
