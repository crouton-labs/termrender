"""Two-pass layout engine: resolve widths top-down, heights bottom-up."""

from __future__ import annotations

import subprocess

from termrender.blocks import Block, BlockType
from termrender.renderers.mermaid import fix_mermaid_encoding, preprocess_mermaid_for_ascii
from termrender.style import wrap_text, visual_len


def _plain_text(spans: list) -> str:
    return "".join(s.text for s in spans)


def resolve_width(block: Block, available: int) -> None:
    block.width = available

    bt = block.type
    if bt in (BlockType.PANEL, BlockType.CALLOUT, BlockType.CODE, BlockType.STAT):
        border_overhead = visual_len("│") * 2 + 2  # left border + left pad + right pad + right border
        inner = max(available - border_overhead, 1)
        for child in block.children:
            resolve_width(child, inner)
    elif bt == BlockType.QUOTE:
        bar_overhead = visual_len("│") + 1  # "│ " prefix
        inner = max(available - bar_overhead, 1)
        for child in block.children:
            resolve_width(child, inner)

    elif bt == BlockType.COLUMNS:
        n = len(block.children)
        if n == 0:
            return
        gaps = n - 1
        # Reserve space for inter-column gaps before distributing widths
        distributable = max(available - gaps, n)

        # Separate children into explicit-width and auto-width
        explicit: dict[int, int] = {}
        for i, col in enumerate(block.children):
            w = col.attrs.get("width")
            if w is not None:
                w_str = str(w)
                try:
                    if w_str.endswith("%"):
                        explicit[i] = max(int(distributable * float(w_str[:-1]) / 100), 1)
                    else:
                        explicit[i] = max(int(w_str), 1)
                except ValueError:
                    pass

        used = sum(explicit.values())
        remaining = max(distributable - used, 0)
        auto_count = n - len(explicit)

        for i, col in enumerate(block.children):
            if i in explicit:
                col_w = explicit[i]
            elif auto_count > 0:
                col_w = max(remaining // auto_count, 1)
            else:
                col_w = 1
            resolve_width(col, col_w)

    else:
        for child in block.children:
            resolve_width(child, available)


def resolve_height(block: Block) -> None:
    # Recurse children first (bottom-up)
    for child in block.children:
        resolve_height(child)

    bt = block.type
    width = block.width or 1

    if bt == BlockType.PARAGRAPH:
        text = _plain_text(block.text)
        lines = wrap_text(text, width)
        block.height = len(lines)

    elif bt == BlockType.HEADING:
        block.height = 1

    elif bt == BlockType.DIVIDER:
        block.height = 1

    elif bt in (BlockType.PANEL, BlockType.CALLOUT):
        block.height = sum(c.height or 0 for c in block.children) + 2

    elif bt == BlockType.CODE:
        source = block.attrs.get("source") or _plain_text(block.text)
        raw_lines = source.split("\n") if source else [""]
        border_v = visual_len("│")
        content_w = max(width - 2 * border_v - 2, 1)
        total_lines = sum(len(wrap_text(line, content_w)) for line in raw_lines)
        block.height = total_lines + 2

    elif bt == BlockType.COLUMNS:
        block.height = max((c.height or 0 for c in block.children), default=0)

    elif bt in (BlockType.COL, BlockType.DOCUMENT, BlockType.LIST):
        block.height = sum(c.height or 0 for c in block.children)

    elif bt == BlockType.LIST_ITEM:
        text_height = 0
        if block.text:
            text_lines = wrap_text(_plain_text(block.text), max(width - 2, 1))
            text_height = len(text_lines)
        block.height = text_height + sum(c.height or 0 for c in block.children)

    elif bt == BlockType.TREE:
        source = block.attrs.get("source", "")
        block.height = len(source.split("\n")) if source else 1

    elif bt == BlockType.TABLE:
        headers = block.attrs.get("headers", [])
        rows = block.attrs.get("rows", [])
        n_cols = max(len(headers), max((len(r) for r in rows), default=0))
        if n_cols == 0:
            block.height = 0
        else:
            rh = [_plain_text(headers[i]) if i < len(headers) else "" for i in range(n_cols)]
            rr = [[_plain_text(row[i]) if i < len(row) else "" for i in range(n_cols)] for row in rows]
            col_widths = [
                max(3, visual_len(rh[i]), *(visual_len(r[i]) for r in rr))
                for i in range(n_cols)
            ]
            total = sum(col_widths) + n_cols * 2 + (n_cols + 1)
            if total > width:
                avail = max(width - n_cols * 2 - (n_cols + 1), n_cols * 3)
                total_natural = sum(col_widths)
                if total_natural > 0:
                    col_widths = [max(3, round(cw / total_natural * avail)) for cw in col_widths]
            header_h = max(len(wrap_text(rh[i], col_widths[i])) for i in range(n_cols))
            data_h = sum(
                max(len(wrap_text(r[i], col_widths[i])) for i in range(n_cols))
                for r in rr
            ) if rr else 0
            row_seps = max(len(rr) - 1, 0)  # horizontal lines between data rows
            block.height = header_h + data_h + 3 + row_seps  # top border + header sep + bottom border + row seps

    elif bt == BlockType.MERMAID:
        source = block.attrs.get("source", "") or _plain_text(block.text)
        rendered = source  # fallback
        try:
            result = subprocess.run(
                ["mermaid-ascii", "-f", "-", "-w", str(block.width or 80), "-y", "1"],
                input=preprocess_mermaid_for_ascii(source),
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            rendered = fix_mermaid_encoding(result.stdout)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        block.attrs["_rendered"] = rendered
        block.height = len(rendered.split("\n")) if rendered else 1

    elif bt == BlockType.QUOTE:
        block.height = sum(c.height or 0 for c in block.children) + (1 if block.attrs.get("author") or block.attrs.get("by") else 0)

    elif bt == BlockType.DIFF:
        source = block.attrs.get("source", "")
        lines = source.split("\n") if source else [""]
        # Drop pure-blank trailing line that comes from terminating newline
        if lines and lines[-1] == "":
            lines = lines[:-1]
        block.height = max(len(lines), 1) + 2  # top/bottom border

    elif bt == BlockType.BAR:
        items = block.attrs.get("items", [])
        title_h = 1 if block.attrs.get("title") else 0
        block.height = max(len(items), 1) + title_h

    elif bt == BlockType.PROGRESS:
        block.height = 1

    elif bt == BlockType.GAUGE:
        # label line + bar line + value line
        block.height = 3

    elif bt == BlockType.STAT:
        # top border + label + value + delta + caption lines + bottom border
        caption_h = sum(c.height or 0 for c in block.children)
        delta_h = 1 if block.attrs.get("delta") else 0
        block.height = 2 + 1 + 1 + delta_h + caption_h  # borders + label + value + delta + caption

    elif bt == BlockType.TIMELINE:
        entries = block.attrs.get("entries", [])
        title_h = 1 if block.attrs.get("title") else 0
        # Each entry takes 1 line + 1 connector line between entries (none after last)
        if entries:
            block.height = title_h + len(entries) * 2 - 1
        else:
            block.height = max(title_h, 1)

    else:
        block.height = sum(c.height or 0 for c in block.children)


def layout(doc: Block, width: int) -> None:
    resolve_width(doc, width)
    resolve_height(doc)
