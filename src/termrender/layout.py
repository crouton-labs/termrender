"""Two-pass layout engine: resolve widths top-down, heights bottom-up."""

from __future__ import annotations

import subprocess

from termrender.blocks import Block, BlockType
from termrender.style import wrap_text


def _plain_text(spans: list) -> str:
    return "".join(s.text for s in spans)


def resolve_width(block: Block, available: int) -> None:
    block.width = available

    bt = block.type
    if bt in (BlockType.PANEL, BlockType.CALLOUT, BlockType.CODE, BlockType.QUOTE):
        inner = max(available - 4, 1)
        for child in block.children:
            resolve_width(child, inner)

    elif bt == BlockType.COLUMNS:
        n = len(block.children)
        if n == 0:
            return
        gaps = n - 1
        inner = available

        # Separate children into explicit-width and auto-width
        explicit: dict[int, int] = {}
        for i, col in enumerate(block.children):
            w = col.attrs.get("width")
            if w is not None:
                w_str = str(w)
                try:
                    if w_str.endswith("%"):
                        explicit[i] = max(int(inner * float(w_str[:-1]) / 100), 1)
                    else:
                        explicit[i] = max(int(w_str), 1)
                except ValueError:
                    pass

        used = sum(explicit.values()) + gaps
        remaining = max(inner - used, 0)
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
        code_lines = source.split("\n") if source else [""]
        block.height = len(code_lines) + 2

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
        rows = block.attrs.get("rows", [])
        block.height = len(rows) + 4  # top border + header + separator + data rows + bottom border

    elif bt == BlockType.MERMAID:
        source = block.attrs.get("source", "") or _plain_text(block.text)
        rendered = source  # fallback
        try:
            result = subprocess.run(
                ["mermaid-ascii", "-f", "-"],
                input=source,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            rendered = result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        block.attrs["_rendered"] = rendered
        block.height = len(rendered.split("\n")) if rendered else 1

    elif bt == BlockType.QUOTE:
        block.height = sum(c.height or 0 for c in block.children) + (1 if block.attrs.get("by") else 0)

    else:
        block.height = sum(c.height or 0 for c in block.children)


def layout(doc: Block, width: int) -> None:
    resolve_width(doc, width)
    resolve_height(doc)
