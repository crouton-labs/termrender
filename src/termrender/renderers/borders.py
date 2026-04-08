"""Shared box-drawing border helper for termrender renderers."""

from __future__ import annotations

from termrender.style import style, visual_len, visual_ljust


def render_box(
    content_lines: list[str],
    width: int,
    color: bool,
    title: str | None = None,
    border_color: str | None = None,
    title_color: str | None = None,
    dim: bool = False,
) -> list[str]:
    """Render content lines inside a box-drawing border.

    Args:
        content_lines: Pre-rendered content to wrap in a box.
        width: Total width of the box including borders.
        color: Whether ANSI styling is enabled.
        title: Optional title to display in the top border.
        border_color: Color name for the border (used by panels).
        title_color: Color for the title text (defaults to border_color).
        dim: Whether to dim the border (used by code blocks).
    """
    # Calculate border character widths dynamically
    border_v = visual_len("│")  # 1 or 2 depending on ambiguous width
    dash_v = visual_len("─")
    corner_v = visual_len("┌")  # same as ┐, └, ┘

    # Grow the box if any content line (or the title) won't fit at the
    # requested width. mermaid-ascii's --maxWidth is non-strict, so a child
    # mermaid block can return lines wider than its allocated content area.
    # Truncating would corrupt the diagram; growing keeps the box's top,
    # bottom, and side borders aligned at the same column even if it
    # overflows the parent's allocation.
    content_max = visual_len("")
    for cl in content_lines:
        cl_w = visual_len(cl)
        if cl_w > content_max:
            content_max = cl_w
    required_for_content = content_max + 2 + 2 * border_v  # pads + walls
    required_for_title = 0
    if title:
        title_part_w = dash_v + 2 + visual_len(title)  # "─ TITLE "
        # Reserve at least one trailing dash so the corner has chrome.
        required_for_title = title_part_w + dash_v + 2 * border_v
    width = max(width, required_for_content, required_for_title)

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
        if title_color and color:
            # Style title text separately from border chrome
            styled_title = style(title, color=title_color, bold=True)
            border_prefix = style("┌─ ", **style_kw)
            border_suffix = style(" " + "─" * fill_count + "┐", **style_kw)
            top = border_prefix + styled_title + border_suffix
        else:
            top_raw = "┌" + title_part + "─" * fill_count + "┐"
            top = style(top_raw, **style_kw)
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
