"""Panel and callout renderers for termrender."""

from __future__ import annotations

from typing import Callable

from termrender.blocks import Block, BlockType
from termrender.renderers.borders import render_box


def render(
    block: Block, color: bool, render_child: Callable[[Block, bool], list[str]]
) -> list[str]:
    """Render a panel block with box-drawing borders."""
    border_color = block.attrs.get("color")
    title = block.attrs.get("title")

    # Render children content
    content_lines: list[str] = []
    for child in block.children:
        content_lines.extend(render_child(child, color))

    return render_box(
        content_lines,
        width=block.width,
        color=color,
        title=title,
        border_color=border_color,
    )


# Callout type -> (color, icon)
_CALLOUT_MAP = {
    "info": ("blue", "ℹ"),
    "warning": ("yellow", "⚠"),
    "error": ("red", "✖"),
    "success": ("green", "✔"),
}


def render_callout(
    block: Block, color: bool, render_child: Callable[[Block, bool], list[str]]
) -> list[str]:
    """Render a callout block by delegating to panel rendering."""
    callout_type = block.attrs.get("type", "info")
    callout_color, icon = _CALLOUT_MAP.get(callout_type, ("blue", "ℹ"))

    title = f"{icon} {callout_type.capitalize()}"

    # Create a copy of attrs with title and color set
    patched_attrs = dict(block.attrs)
    patched_attrs["title"] = title
    patched_attrs["color"] = callout_color

    # Build a proxy block with the patched attrs
    proxy = Block(
        type=BlockType.PANEL,
        children=block.children,
        text=block.text,
        attrs=patched_attrs,
        width=block.width,
        height=block.height,
    )
    return render(proxy, color, render_child)
