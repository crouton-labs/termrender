"""termrender — render Markdown to ANSI terminal output."""

import os
import shutil
from typing import Any

from termrender.parser import parse, DirectiveError
from termrender.layout import layout
from termrender.emit import emit, emit_with_map
from termrender.style import set_ambiguous_width


class TerminalError(Exception):
    """Raised when the terminal does not support required capabilities."""


def render(source: str, width: int | None = None, color: bool = True) -> str:
    """Render directive-flavored markdown to ANSI terminal output.

    Args:
        source: Markdown string with optional directives
        width: Terminal width in columns (auto-detected if None)
        color: Enable ANSI color codes (respects NO_COLOR env var)

    Returns:
        Rendered string with ANSI escape sequences

    Raises:
        TerminalError: If terminal is unsupported (TERM=dumb)
    """
    doc, color = _prepare(source, width, color)
    return emit(doc, color)


def render_with_map(
    source: str, width: int | None = None, color: bool = True,
) -> dict[str, Any]:
    """Render like `render`, additionally returning the row→source line map.

    Returns a dict:
        lines   list[str] — rendered ANSI rows (identical to `render` output split on newlines)
        rows    list[int|None] — per-row index into `blocks`, None for separator rows
        blocks  list[dict] — per top-level block: {type, start, end} where
                start/end are 1-indexed inclusive source-line bounds (None when unmapped)
    """
    doc, color = _prepare(source, width, color)
    lines, rows = emit_with_map(doc, color)
    blocks = [
        {"type": child.type.value, "start": child.src_start, "end": child.src_end}
        for child in doc.children
    ]
    return {"lines": lines, "rows": rows, "blocks": blocks}


def _prepare(source: str, width: int | None, color: bool):
    """Shared env checks + parse/layout pipeline for both render entry points."""
    # Check for ambiguous width setting
    if os.environ.get("TERMRENDER_CJK"):
        set_ambiguous_width(2)

    # REQ-011: Check terminal capability
    if os.environ.get("TERM") == "dumb":
        raise TerminalError("Terminal type 'dumb' does not support Unicode rendering")

    # Respect NO_COLOR convention (https://no-color.org/)
    if os.environ.get("NO_COLOR") is not None:
        color = False

    # Auto-detect width
    if width is None:
        width = shutil.get_terminal_size().columns

    doc = parse(source)
    layout(doc, width)
    return doc, color
