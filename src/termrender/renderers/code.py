"""Syntax-highlighted code block renderer for termrender."""

from __future__ import annotations

from typing import Callable

from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import TextLexer, get_lexer_by_name

from termrender.blocks import Block, Span
from termrender.renderers.borders import render_box
from termrender.style import grapheme_clusters, visual_len


def wrap_source_line(line: str, width: int) -> list[str]:
    """Hard-wrap one verbatim source line without folding its whitespace."""
    if not line:
        return [""]
    if width <= 0:
        return [line]

    lines: list[str] = []
    current = ""
    current_width = 0
    for cluster in grapheme_clusters(line):
        cluster_width = visual_len(cluster)
        if current and current_width + cluster_width > width:
            lines.append(current)
            current = ""
            current_width = 0
        current += cluster
        current_width += cluster_width
        if current_width >= width:
            lines.append(current)
            current = ""
            current_width = 0
    if current:
        lines.append(current)
    return lines or [""]


def render(
    block: Block, color: bool, render_child: Callable[[Block, bool], list[str]]
) -> list[str]:
    """Render a code block with syntax highlighting and box-drawing borders."""
    return render_with_spans(block, color, render_child)[0]


def render_with_spans(
    block: Block, color: bool, render_child: Callable[[Block, bool], list[str]],
    inherit: Span = None,
) -> tuple[list[str], list[Span]]:
    """Render like `render`, also returning a per-row leaf source span.

    Content rows map 1:1 to their source lines (wrapped continuations share
    the line); the box chrome maps to the whole block. Falls back to the
    whole-block span when the parser did not record the first content line."""
    source = block.attrs.get("source", "")
    lang = block.attrs.get("lang")
    title = block.attrs.get("title", lang)
    whole: Span = (
        (block.src_start, block.src_end)
        if block.src_start is not None and block.src_end is not None
        else inherit
    )
    content_start: int | None = block.attrs.get("src_content_start")

    # Wrap raw source lines to fit within the box before highlighting,
    # so render_box doesn't need to grow beyond the layout allocation.
    border_v = visual_len("│")
    content_w = max((block.width or 1) - 2 * border_v - 2, 1)
    raw_lines = source.split("\n") if source else [""]
    wrapped_lines = []
    line_spans: list[Span] = []
    for r, line in enumerate(raw_lines):
        segs = wrap_source_line(line, content_w)
        wrapped_lines.extend(segs)
        if content_start is not None:
            src_line = content_start + r
            if block.src_end is not None:
                src_line = min(src_line, block.src_end)
            line_spans.extend([(src_line, src_line)] * len(segs))
        else:
            line_spans.extend([whole] * len(segs))

    wrapped_source = "\n".join(wrapped_lines)

    # Syntax highlight (or plain text)
    if color and wrapped_source:
        try:
            lexer = get_lexer_by_name(lang) if lang else TextLexer()
        except Exception:
            lexer = TextLexer()
        highlighted = highlight(wrapped_source, lexer, TerminalFormatter())
        # Pygments adds a trailing newline — strip it
        highlighted = highlighted.rstrip("\n")
        code_lines = highlighted.split("\n")
    else:
        code_lines = wrapped_lines

    box_lines = render_box(
        code_lines,
        width=block.width,
        color=color,
        title=title,
        dim=True,
    )
    # Box shape: top border + content rows (one empty row when content is
    # empty) + bottom border. Highlighting preserves line count except that
    # pygments' trailing-newline rstrip swallows trailing blank lines — drop
    # their spans to match. Any other disagreement falls back to the
    # whole-block span rather than misattribute.
    if len(line_spans) > len(code_lines) and all(
        not seg for seg in wrapped_lines[len(code_lines):]
    ):
        line_spans = line_spans[: len(code_lines)]
    n_content = len(box_lines) - 2
    if n_content == len(code_lines) == len(line_spans):
        content_spans = line_spans
    else:
        content_spans = [whole] * n_content
    return box_lines, [whole] + content_spans + [whole]
