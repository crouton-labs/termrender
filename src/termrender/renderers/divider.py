"""Horizontal divider renderer for termrender."""

from __future__ import annotations

from termrender.blocks import Block
from termrender.style import style, visual_center, visual_ljust, visual_len


def render(block: Block, color: bool) -> list[str]:
    """Render a horizontal divider, optionally with a centered label."""
    w = block.width
    label = block.attrs.get("label")

    dash_v = visual_len("─")
    fill_count = max(0, w // dash_v)

    if label:
        # Center label with surrounding dashes: ──── Label ────
        inner = f" {label} "
        line = visual_center(inner, w, "─")
    else:
        line = "─" * fill_count

    line = style(line, dim=True, enabled=color)
    line = visual_ljust(line, w)
    return [line]
