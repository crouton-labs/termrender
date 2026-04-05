"""Horizontal divider renderer for termrender."""

from __future__ import annotations

from termrender.blocks import Block
from termrender.style import style, visual_center, visual_ljust


def render(block: Block, color: bool) -> list[str]:
    """Render a horizontal divider, optionally with a centered label."""
    w = block.width
    label = block.attrs.get("label")

    if label:
        # Center label with surrounding dashes: ──── Label ────
        inner = f" {label} "
        line = visual_center(inner, w, "─")
    else:
        line = "─" * w

    line = style(line, dim=True, enabled=color)
    line = visual_ljust(line, w)
    return [line]
