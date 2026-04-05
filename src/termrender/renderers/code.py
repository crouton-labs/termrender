"""Syntax-highlighted code block renderer for termrender."""

from __future__ import annotations

from typing import Callable

from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import TextLexer, get_lexer_by_name

from termrender.blocks import Block
from termrender.renderers.borders import render_box


def render(
    block: Block, color: bool, render_child: Callable[[Block, bool], list[str]]
) -> list[str]:
    """Render a code block with syntax highlighting and box-drawing borders."""
    source = block.attrs.get("source", "")
    lang = block.attrs.get("lang")

    # Syntax highlight (or plain text)
    if color and source:
        try:
            lexer = get_lexer_by_name(lang) if lang else TextLexer()
        except Exception:
            lexer = TextLexer()
        highlighted = highlight(source, lexer, TerminalFormatter())
        # Pygments adds a trailing newline — strip it
        highlighted = highlighted.rstrip("\n")
        code_lines = highlighted.split("\n")
    else:
        code_lines = source.split("\n") if source else [""]

    return render_box(
        code_lines,
        width=block.width,
        color=color,
        title=lang,
        dim=True,
    )
