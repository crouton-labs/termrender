"""Mermaid diagram renderer for termrender."""

from __future__ import annotations

import subprocess

from termrender.blocks import Block
from termrender.style import visual_ljust


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
            rendered = result.stdout
        except Exception:
            rendered = source

    lines: list[str] = []
    for raw_line in rendered.split("\n"):
        lines.append(visual_ljust(raw_line, w))

    return lines
