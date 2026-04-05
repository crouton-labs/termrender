"""Mermaid diagram renderer for termrender."""

from __future__ import annotations

import subprocess

from termrender.blocks import Block
from termrender.style import visual_ljust


def fix_mermaid_encoding(text: str) -> str:
    """Undo mermaid-ascii's double-encoding of UTF-8 characters.

    mermaid-ascii misinterprets UTF-8 input bytes as Latin-1 and re-encodes
    to UTF-8, corrupting multi-byte characters (e.g. → becomes â\\x86\\x92).
    Reversing the process: encode back to Latin-1 to recover the original
    UTF-8 bytes, then decode as UTF-8.
    """
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def render(block: Block, color: bool) -> list[str]:
    """Render a mermaid diagram from pre-rendered or on-the-fly ASCII output."""
    w = block.width
    rendered = block.attrs.get("_rendered")

    if rendered is None:
        source = block.attrs.get("source", "")
        try:
            result = subprocess.run(
                ["mermaid-ascii", "-f", "-"],
                input=source,
                capture_output=True,
                text=True,
                timeout=30,
            )
            rendered = fix_mermaid_encoding(result.stdout)
        except Exception:
            rendered = source

    lines: list[str] = []
    for raw_line in rendered.split("\n"):
        lines.append(visual_ljust(raw_line, w))

    return lines
