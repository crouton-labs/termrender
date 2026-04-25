"""Timeline renderer for termrender — native ASCII vertical timeline."""

from __future__ import annotations

from termrender.blocks import Block
from termrender.style import style, visual_len, visual_ljust, wrap_text


def render(block: Block, color: bool, render_child=None) -> list[str]:
    """Render a vertical timeline with date markers and event text."""
    w = block.width or 60
    title = block.attrs.get("title")
    entries = block.attrs.get("entries", [])
    accent = block.attrs.get("color", "cyan")

    if not entries:
        if title:
            return [visual_ljust(style(title, bold=True, enabled=color), w)]
        return [visual_ljust("", w)]

    date_w = max(visual_len(e["date"]) for e in entries)

    lines: list[str] = []
    if title:
        lines.append(visual_ljust(style(title, bold=True, enabled=color), w))

    bullet = style("●", color=accent, bold=True, enabled=color)
    bar = style("│", color=accent, dim=True, enabled=color)

    event_w = max(w - date_w - 4, 5)  # date + space + bullet + space + event
    cont_indent = " " * (date_w + 1)

    for i, entry in enumerate(entries):
        date_text = entry["date"].rjust(date_w)
        date_styled = style(date_text, dim=True, enabled=color)
        wrapped = wrap_text(entry["event"], event_w) or [""]
        lines.append(visual_ljust(f"{date_styled} {bullet} {wrapped[0]}", w))
        for cont in wrapped[1:]:
            lines.append(visual_ljust(f"{cont_indent}{bar} {cont}", w))
        if i < len(entries) - 1:
            lines.append(visual_ljust(f"{cont_indent}{bar}", w))

    return lines
