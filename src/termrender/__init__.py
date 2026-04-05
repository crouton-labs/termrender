"""termrender — render Markdown to ANSI terminal output."""

import os
import shutil
from termrender.parser import parse
from termrender.layout import layout
from termrender.emit import emit


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
    # REQ-011: Check terminal capability
    if os.environ.get("TERM") == "dumb":
        raise TerminalError("Terminal type 'dumb' does not support Unicode rendering")

    # Respect NO_COLOR convention (https://no-color.org/)
    if os.environ.get("NO_COLOR") is not None:
        color = False

    # Auto-detect width
    if width is None:
        width = shutil.get_terminal_size().columns

    # Pipeline: parse → layout → emit
    doc = parse(source)
    layout(doc, width)
    return emit(doc, color)
