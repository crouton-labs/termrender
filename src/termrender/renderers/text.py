"""Paragraph, heading, list, and list-item renderers for termrender."""

from __future__ import annotations

from termrender.blocks import Block, BlockType, InlineSpan
from termrender.style import style, visual_len, visual_ljust, wrap_text, render_spans


def _render_wrapped_spans(
    spans: list[InlineSpan],
    width: int,
    color: bool,
    first_prefix: str = "",
    cont_prefix: str = "",
    total_width: int | None = None,
) -> list[str]:
    """Wrap spans into styled lines with optional prefixes and padding."""
    if total_width is None:
        total_width = width

    plain = "".join(span.text for span in spans)
    wrapped = wrap_text(plain, max(width, 1))

    lines: list[str] = []
    char_offset = 0
    for i, raw_line in enumerate(wrapped):
        line_len = len(raw_line)
        styled = _render_span_slice(spans, char_offset, char_offset + line_len, color)
        prefix = first_prefix if i == 0 else cont_prefix
        lines.append(visual_ljust(prefix + styled, total_width))
        char_offset += line_len
        if char_offset < len(plain) and plain[char_offset] == " ":
            char_offset += 1

    return lines


def _render_paragraph(block: Block, color: bool) -> list[str]:
    if not block.text:
        return [visual_ljust("", block.width)]

    return _render_wrapped_spans(block.text, block.width, color)


def _render_span_slice(
    spans: list[InlineSpan], start: int, end: int, color: bool
) -> str:
    """Render the portion of spans covering character range [start, end)."""
    parts: list[str] = []
    offset = 0
    for span in spans:
        span_start = offset
        span_end = offset + len(span.text)
        # Find overlap with [start, end)
        overlap_start = max(span_start, start)
        overlap_end = min(span_end, end)
        if overlap_start < overlap_end:
            slice_text = span.text[overlap_start - span_start : overlap_end - span_start]
            if span.code:
                slice_text = style(slice_text, dim=True, enabled=color)
            elif span.bold or span.italic:
                slice_text = style(slice_text, bold=span.bold, italic=span.italic, enabled=color)
            parts.append(slice_text)
        offset = span_end
        if offset >= end:
            break
    return "".join(parts)


def _render_heading(block: Block, color: bool) -> list[str]:
    level = block.attrs.get("level", 1)
    text = render_spans(block.text, color=False)  # plain text first

    if level == 1:
        styled = style(text, color="blue", bold=True, enabled=color)
    elif level == 2:
        styled = style(text, bold=True, enabled=color)
    elif level == 3:
        styled = style(text, italic=True, enabled=color)
    else:
        styled = style(text, dim=True, enabled=color)

    return [visual_ljust(styled, block.width)]


def _render_list(block: Block, color: bool) -> list[str]:
    if not block.children:
        return [visual_ljust("", block.width)]

    ordered = block.attrs.get("ordered", False)
    lines: list[str] = []

    for i, child in enumerate(block.children):
        if child.type == BlockType.LIST_ITEM:
            prefix = f"{i + 1}. " if ordered else "• "
            item_lines = _render_list_item(child, prefix, color)
            lines.extend(item_lines)
        elif child.type == BlockType.LIST:
            # Nested list — indent by 2
            nested = Block(
                type=child.type,
                children=child.children,
                text=child.text,
                attrs=child.attrs,
                width=(child.width or block.width) - 2,
                height=child.height,
            )
            nested_lines = _render_list(nested, color)
            for nl in nested_lines:
                lines.append(visual_ljust("  " + nl.rstrip(), block.width))

    return lines if lines else [visual_ljust("", block.width)]


def _render_list_item(block: Block, prefix: str, color: bool) -> list[str]:
    w = block.width
    indent = " " * len(prefix)
    text_width = w - len(prefix)

    if not block.text:
        return [visual_ljust(prefix, w)]

    lines = _render_wrapped_spans(
        block.text, text_width, color,
        first_prefix=prefix, cont_prefix=indent, total_width=w,
    )

    # Render nested children (e.g., nested lists inside list items)
    for child in block.children:
        if child.type == BlockType.LIST:
            nested = Block(
                type=child.type,
                children=child.children,
                text=child.text,
                attrs=child.attrs,
                width=w - len(prefix),
                height=child.height,
            )
            nested_lines = _render_list(nested, color)
            for nl in nested_lines:
                lines.append(visual_ljust(indent + nl.rstrip(), w))

    return lines


def render(block: Block, color: bool) -> list[str]:
    """Render a text block (paragraph, heading, list, or list item)."""
    if block.type == BlockType.PARAGRAPH:
        return _render_paragraph(block, color)
    elif block.type == BlockType.HEADING:
        return _render_heading(block, color)
    elif block.type == BlockType.LIST:
        return _render_list(block, color)
    elif block.type == BlockType.LIST_ITEM:
        return _render_list_item(block, "• ", color)
    else:
        return [visual_ljust("", block.width or 0)]
