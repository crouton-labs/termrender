"""Table renderer for termrender."""

from __future__ import annotations

from termrender.blocks import Block, InlineSpan, Span
from termrender.style import style, visual_len, visual_ljust, visual_center, render_spans, wrap_text


def _align_cell(text: str, width: int, align: str | None) -> str:
    if align == "center":
        return visual_center(text, width)
    elif align == "right":
        vl = visual_len(text)
        if vl < width:
            return " " * (width - vl) + text
        return text
    else:
        return visual_ljust(text, width)


def _render_span_slice(
    spans: list[InlineSpan], start: int, end: int, color: bool
) -> str:
    """Render the portion of spans covering character range [start, end)."""
    parts: list[str] = []
    offset = 0
    for span in spans:
        span_start = offset
        span_end = offset + len(span.text)
        overlap_start = max(span_start, start)
        overlap_end = min(span_end, end)
        if overlap_start < overlap_end:
            slice_text = span.text[overlap_start - span_start : overlap_end - span_start]
            if span.code:
                slice_text = style(slice_text, color="cyan", enabled=color)
            elif span.fg or span.bg:
                slice_text = style(
                    slice_text,
                    color=span.fg, bg=span.bg,
                    bold=span.bold, italic=span.italic,
                    enabled=color,
                )
            elif span.bold or span.italic:
                slice_text = style(slice_text, bold=span.bold, italic=span.italic, enabled=color)
            parts.append(slice_text)
        offset = span_end
        if offset >= end:
            break
    return "".join(parts)


def _wrap_cell_colored(
    spans: list[InlineSpan], width: int, color: bool
) -> list[str]:
    """Wrap cell content to width, preserving inline styling."""
    plain = render_spans(spans, False)
    wrapped = wrap_text(plain, max(width, 1))
    if not color:
        return wrapped

    lines: list[str] = []
    offset = 0
    for raw_line in wrapped:
        line_len = len(raw_line)
        styled = _render_span_slice(spans, offset, offset + line_len, color)
        lines.append(styled)
        offset += line_len
        if offset < len(plain) and plain[offset] == " ":
            offset += 1
    return lines


def render(block: Block, color: bool) -> list[str]:
    return render_with_spans(block, color)[0]


def render_with_spans(block: Block, color: bool, inherit: Span = None) -> tuple[list[str], list[Span]]:
    """Render like `render`, also returning a per-row leaf source span.

    Each source table row (header included) is its own leaf: a row's rendered
    lines plus the chrome directly above it (top border, header separator,
    inter-row separator) map to that row's source line; the bottom border maps
    to the last row. Falls back to the whole-block span when the parser did
    not record per-row source lines (non-GFM shapes)."""
    headers: list[list] = block.attrs.get("headers", [])
    rows: list[list[list]] = block.attrs.get("rows", [])
    aligns: list[str | None] = block.attrs.get("aligns", [])
    w = block.width or 80

    # Default theme: blue borders, yellow headers on dim_blue bg (gloam-inspired)
    border_color = block.attrs.get("border_color", "blue")
    header_fg = block.attrs.get("header_color", "yellow")
    header_bg = block.attrs.get("header_bg", "dim_blue")

    def border(text: str) -> str:
        """Style border characters."""
        return style(text, color=border_color, dim=True, enabled=color)

    n_cols = max(len(headers), max((len(r) for r in rows), default=0))
    if n_cols == 0:
        return [], []

    # Render all cells to plain text for width calculation
    rendered_headers = [render_spans(headers[i], False) if i < len(headers) else "" for i in range(n_cols)]
    rendered_rows = [
        [render_spans(row[i], False) if i < len(row) else "" for i in range(n_cols)]
        for row in rows
    ]

    # Calculate natural column widths (minimum 3)
    col_widths = [
        max(3, visual_len(rendered_headers[i]), *(visual_len(r[i]) for r in rendered_rows))
        for i in range(n_cols)
    ]

    # Total width: borders + padding (each cell has 1 space padding on each side)
    # Layout: │ cell │ cell │  => n_cols + 1 borders + n_cols * 2 padding
    total = sum(col_widths) + n_cols * 2 + (n_cols + 1)

    # Distribute proportionally if overflow
    if total > w:
        available = w - n_cols * 2 - (n_cols + 1)
        available = max(available, n_cols * 3)
        total_natural = sum(col_widths)
        if total_natural > 0:
            col_widths = [
                max(3, round(cw / total_natural * available))
                for cw in col_widths
            ]

    # Wrap cell content to column widths with inline styling
    header_spans = [headers[i] if i < len(headers) else [] for i in range(n_cols)]
    wrapped_headers = [_wrap_cell_colored(header_spans[i], col_widths[i], color) for i in range(n_cols)]

    row_spans = [
        [row[i] if i < len(row) else [] for i in range(n_cols)]
        for row in rows
    ]
    wrapped_rows = [
        [_wrap_cell_colored(rs[i], col_widths[i], color) for i in range(n_cols)]
        for rs in row_spans
    ]

    def render_multiline_row(wrapped_cells: list[list[str]], is_header: bool) -> list[str]:
        row_height = max((len(c) for c in wrapped_cells), default=1)
        out: list[str] = []
        for line_idx in range(row_height):
            parts: list[str] = []
            for i, cell_lines in enumerate(wrapped_cells):
                text = cell_lines[line_idx] if line_idx < len(cell_lines) else ""
                align = aligns[i] if i < len(aligns) else None
                padded = _align_cell(text, col_widths[i], align)
                if is_header and color:
                    padded = style(" " + padded + " ", bold=True, color=header_fg, bg=header_bg)
                else:
                    padded = " " + padded + " "
                parts.append(padded)
            line = border("│") + border("│").join(parts) + border("│")
            out.append(visual_ljust(line, w))
        return out

    def separator(left: str, mid: str, right: str) -> str:
        segs = ["─" * (col_widths[i] + 2) for i in range(n_cols)]
        raw = left + mid.join(segs) + right
        line = style(raw, color=border_color, dim=True, enabled=color)
        return visual_ljust(line, w)

    whole: Span = (
        (block.src_start, block.src_end)
        if block.src_start is not None and block.src_end is not None
        else inherit
    )
    header_line: int | None = block.attrs.get("src_header_line")
    row_lines: list[int] = block.attrs.get("src_row_lines", [])
    header_span: Span = (header_line, header_line) if header_line is not None else whole

    def row_span(idx: int) -> Span:
        return (row_lines[idx], row_lines[idx]) if idx < len(row_lines) else whole

    lines: list[str] = []
    spans: list[Span] = []

    def add(line_batch: list[str], span: Span) -> None:
        lines.extend(line_batch)
        spans.extend([span] * len(line_batch))

    add([separator("┌", "┬", "┐")], header_span)
    add(render_multiline_row(wrapped_headers, is_header=True), header_span)
    add([separator("├", "┼", "┤")], header_span)
    for idx, wr in enumerate(wrapped_rows):
        if idx > 0:
            add([separator("├", "┼", "┤")], row_span(idx))
        add(render_multiline_row(wr, is_header=False), row_span(idx))
    add([separator("└", "┴", "┘")], row_span(len(wrapped_rows) - 1) if wrapped_rows else header_span)

    return lines, spans
