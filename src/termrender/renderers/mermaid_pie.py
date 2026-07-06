"""Native renderer for mermaid ``pie`` diagrams.

Mermaid pie grammar (subset)::

    pie [showData]
        title An Optional Title
        "Label A" : 40
        "Label B" : 60

A text pie chart is worse than a labeled bar chart at the same information
density, so pie diagrams are re-expressed as a horizontal bar chart (see the
ratified plan in ``mermaid-inline-rendering.md``), reusing ``charts.py``'s
``render_bar`` so the visual style matches the rest of termrender's charts.
"""

from __future__ import annotations

import re

from termrender.blocks import Block, BlockType
from termrender.renderers.charts import render_bar

_TITLE_RE = re.compile(r"^\s*title\s+(.*\S)\s*$", re.IGNORECASE)
_DATA_RE = re.compile(r'^\s*"([^"]*)"\s*:\s*(-?\d+(?:\.\d+)?)\s*$')
_HEADER_RE = re.compile(r"^\s*pie\b", re.IGNORECASE)


def parse_pie(source: str) -> tuple[str | None, list[dict]]:
    """Parse mermaid pie syntax into ``(title, items)``.

    ``items`` is a list of ``{"label": str, "value": float}`` dicts, in
    source order. Lines that match neither the header, ``title``, nor a
    ``"label" : value`` data line are silently skipped — pragmatic parsing
    per the "never crash" contract, not a full grammar.
    """
    title: str | None = None
    items: list[dict] = []
    for line in source.splitlines():
        if not line.strip():
            continue
        if _HEADER_RE.match(line):
            continue
        m = _TITLE_RE.match(line)
        if m:
            title = m.group(1)
            continue
        m = _DATA_RE.match(line)
        if m:
            items.append({"label": m.group(1), "value": float(m.group(2))})
    return title, items


def render(source: str, width: int) -> list[str]:
    """Render mermaid pie syntax as a labeled horizontal bar chart.

    Each bar's value is annotated with its percentage share of the total.
    Diagrams with no parseable data lines degrade to the raw source text.
    """
    title, items = parse_pie(source)
    if not items:
        return source.splitlines() or [""]

    total = sum(it["value"] for it in items) or 1.0
    bar_items = [
        {
            "label": it["label"],
            "value": it["value"],
            "unit": f" ({it['value'] / total * 100:.1f}%)",
        }
        for it in items
    ]

    block = Block(
        type=BlockType.BAR,
        attrs={"items": bar_items, "title": title, "color": "cyan"},
        width=width,
    )
    return render_bar(block, color=False)
