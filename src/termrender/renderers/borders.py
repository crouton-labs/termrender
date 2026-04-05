"""Shared box-drawing border helper for termrender renderers."""

from __future__ import annotations

from termrender.style import style, visual_len, visual_ljust


def render_box(
    content_lines: list[str],
    width: int,
    color: bool,
    title: str | None = None,
    border_color: str | None = None,
    dim: bool = False,
) -> list[str]:
    """Render content lines inside a box-drawing border.

    Args:
        content_lines: Pre-rendered content to wrap in a box.
        width: Total width of the box including borders.
        color: Whether ANSI styling is enabled.
        title: Optional title to display in the top border.
        border_color: Color name for the border (used by panels).
        dim: Whether to dim the border (used by code blocks).
    """
    inner_w = width - 2  # border chars on each side
    content_w = inner_w - 2  # 1-char padding on each side

    # Build style kwargs for borders
    style_kw: dict = {"enabled": color}
    if border_color:
        style_kw["color"] = border_color
    if dim:
        style_kw["dim"] = True

    # Top border
    if title:
        title_part = f"─ {title} "
        fill_count = max(0, inner_w - visual_len(title_part))
        top_raw = "┌" + title_part + "─" * fill_count + "┐"
    else:
        top_raw = "┌" + "─" * inner_w + "┐"
    top = style(top_raw, **style_kw)
    top = visual_ljust(top, width)

    # Bottom border
    bot_raw = "└" + "─" * inner_w + "┘"
    bot = style(bot_raw, **style_kw)
    bot = visual_ljust(bot, width)

    # Side borders
    left = style("│", **style_kw)
    right = style("│", **style_kw)

    # Build output lines
    lines = [top]
    for cl in content_lines:
        padded = visual_ljust(cl, content_w)
        line = left + " " + padded + " " + right
        line = visual_ljust(line, width)
        lines.append(line)

    # If no content, add one empty line
    if not content_lines:
        empty = left + " " + " " * content_w + " " + right
        empty = visual_ljust(empty, width)
        lines.append(empty)

    lines.append(bot)
    return lines
