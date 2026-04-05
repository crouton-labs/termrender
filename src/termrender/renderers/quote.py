"""Blockquote renderer for termrender."""

from __future__ import annotations

from typing import Callable

from termrender.blocks import Block
from termrender.style import style, visual_ljust, visual_len


def render(
    block: Block, color: bool, render_child: Callable[[Block, bool], list[str]]
) -> list[str]:
    """Render a blockquote with a left border bar and optional attribution."""
    w = block.width
    bar = style("│ ", color="gray", enabled=color)
    bar_width = visual_len("│") + 1  # "│" + space
    inner_w = w - bar_width

    lines: list[str] = []
    for child in block.children:
        for cl in render_child(child, color):
            padded = visual_ljust(cl, inner_w)
            lines.append(visual_ljust(bar + padded, w))

    by = block.attrs.get("author") or block.attrs.get("by")
    if by:
        attr_text = style(f"— {by}", dim=True, enabled=color)
        attr_line = visual_ljust(bar + visual_ljust(attr_text, inner_w), w)
        lines.append(attr_line)

    return lines
