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
    # Calculate border character widths dynamically
    border_v = visual_len("│")  # 1 or 2 depending on ambiguous width
    dash_v = visual_len("─")
    corner_v = visual_len("┌")  # same as ┐, └, ┘

    # inner_w = space between the two vertical borders
    inner_w = width - 2 * border_v
    # content_w = space for actual content (inner minus 1-space padding each side)
    content_w = inner_w - 2

    # Build style kwargs for borders
    style_kw: dict = {"enabled": color}
    if border_color:
        style_kw["color"] = border_color
    if dim:
        style_kw["dim"] = True

    # Top border: ┌ + title/dashes + ┐, total visual_len = width
    if title:
        title_part = "─ " + title + " "
        title_visual = visual_len(title_part)
        remaining = inner_w - title_visual
        fill_count = max(0, remaining // dash_v)
        top_raw = "┌" + title_part + "─" * fill_count + "┐"
    else:
        fill_count = max(0, inner_w // dash_v)
        top_raw = "┌" + "─" * fill_count + "┐"
    top = style(top_raw, **style_kw)
    top = visual_ljust(top, width)

    # Bottom border
    fill_count = max(0, inner_w // dash_v)
    bot_raw = "└" + "─" * fill_count + "┘"
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
