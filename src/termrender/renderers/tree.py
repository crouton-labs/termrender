"""Tree rendering with Unicode guide lines (DES-010)."""

from __future__ import annotations

import re

from termrender.blocks import Block, InlineSpan
from termrender.style import style, visual_ljust, render_spans, visual_len

# Unicode box-drawing guide characters
BRANCH = "├── "
LAST_BRANCH = "└── "
CONTINUATION = "│   "
BLANK = "    "

# Status marker patterns
STATUS_MARKERS = {
    "[x]": ("✔", "green"),
    "[!]": ("⚠", "yellow"),
}


def _detect_indent(lines: list[str]) -> int:
    """Auto-detect indent level (2 or 4 spaces) from source lines."""
    for line in lines:
        if not line or not line[0] == " ":
            continue
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if indent > 0:
            return 2 if indent <= 2 else (indent if indent <= 4 else 4)
    return 2


def _parse_tree(lines: list[str], indent_size: int) -> list[tuple[int, str]]:
    """Parse indented lines into (depth, label) pairs."""
    result: list[tuple[int, str]] = []
    for line in lines:
        if not line.strip():
            continue
        stripped = line.lstrip(" ")
        spaces = len(line) - len(stripped)
        depth = spaces // indent_size
        result.append((depth, stripped))
    return result


def _apply_status_markers(label: str, color: bool) -> str:
    """Replace status markers like [x] and [!] with styled symbols."""
    for marker, (symbol, clr) in STATUS_MARKERS.items():
        if marker in label:
            styled_symbol = style(symbol, color=clr, enabled=color)
            label = label.replace(marker, styled_symbol)
    return label


_INLINE_RE = re.compile(
    r'(\*\*(.+?)\*\*)'   # **bold**
    r'|(\*(.+?)\*)'      # *italic*
)


def _label_to_spans(label: str) -> list[InlineSpan]:
    """Convert a label string with markdown inline formatting to InlineSpans."""
    spans: list[InlineSpan] = []
    last_end = 0
    for m in _INLINE_RE.finditer(label):
        # Add any plain text before this match
        if m.start() > last_end:
            spans.append(InlineSpan(text=label[last_end:m.start()]))
        if m.group(2) is not None:
            # **bold**
            spans.append(InlineSpan(text=m.group(2), bold=True))
        elif m.group(4) is not None:
            # *italic*
            spans.append(InlineSpan(text=m.group(4), italic=True))
        last_end = m.end()
    # Trailing plain text
    if last_end < len(label):
        spans.append(InlineSpan(text=label[last_end:]))
    return spans if spans else [InlineSpan(text=label)]


def _guide_chars() -> tuple[str, str, str, str]:
    """Get guide characters padded to consistent visual width.

    All prefixes must have the same visual width for alignment.
    When eaw=A=2, "├── " and "│   " have different visual widths, so we normalize.
    """
    target = visual_len("├── ")  # this is the reference width
    branch = visual_ljust("├── ", target)
    last_branch = visual_ljust("└── ", target)
    continuation = visual_ljust("│   ", target)
    blank = " " * target
    return branch, last_branch, continuation, blank


def _style_guide(text: str, guide_color: str | None, color: bool) -> str:
    """Style a guide line character with the tree's color attribute."""
    if guide_color and color:
        return style(text, color=guide_color, enabled=True)
    return text


def render(block: Block, color: bool) -> list[str]:
    """Render a tree block with Unicode guide lines."""
    source = block.attrs.get("source", "")
    guide_color = block.attrs.get("color")
    raw_lines = source.split("\n")
    indent_size = _detect_indent(raw_lines)
    nodes = _parse_tree(raw_lines, indent_size)
    width = block.width or 80

    if not nodes:
        return [visual_ljust("", width)]

    # Get dynamically-padded guide characters for the current ambiguous width setting
    _branch, _last_branch, _continuation, _blank = _guide_chars()

    # For each node, determine its guide prefix based on depth and siblings
    output: list[str] = []

    # Build sibling relationships: for each node, is it the last among its siblings?
    is_last: list[bool] = []
    for i, (depth, _label) in enumerate(nodes):
        # Look ahead to find if there's another node at the same depth
        # under the same parent
        last = True
        for j in range(i + 1, len(nodes)):
            jdepth, _ = nodes[j]
            if jdepth == depth:
                last = False
                break
            if jdepth < depth:
                # We've gone back up past our parent, so we are last
                break
        is_last.append(last)

    # Track which depth levels have continuing lines
    # active_levels[d] = True means depth d still has children coming
    for i, (depth, label) in enumerate(nodes):
        # Apply status markers
        label = _apply_status_markers(label, color)

        # Build the prefix for this line
        if depth == 0:
            # Root-level items get no guide prefix
            styled_label = render_spans(_label_to_spans(label), color)
            line = styled_label
        else:
            # Build prefix from depth 1 to depth-1 (continuation/blank)
            # then the branch character for current depth
            prefix_parts: list[str] = []
            for d in range(1, depth):
                # Check if depth d has more siblings coming after this point
                has_more = False
                for j in range(i + 1, len(nodes)):
                    jdepth, _ = nodes[j]
                    if jdepth == d:
                        has_more = True
                        break
                    if jdepth < d:
                        break
                if has_more:
                    prefix_parts.append(_style_guide(_continuation, guide_color, color))
                else:
                    prefix_parts.append(_blank)

            # Current depth connector
            if is_last[i]:
                prefix_parts.append(_style_guide(_last_branch, guide_color, color))
            else:
                prefix_parts.append(_style_guide(_branch, guide_color, color))

            prefix = "".join(prefix_parts)
            styled_label = render_spans(_label_to_spans(label), color)
            line = prefix + styled_label

        output.append(visual_ljust(line, width))

    return output
