"""Native renderer for mermaid ``pie`` diagrams.

Mermaid pie grammar (subset)::

    pie [showData]
        title An Optional Title
        "Label A" : 40
        'Label B' : 60

A text pie chart is worse than a labeled bar chart at the same information
density, so pie diagrams are re-expressed as a horizontal bar chart (see the
ratified plan in ``mermaid-inline-rendering.md``), reusing ``charts.py``'s
``render_bar`` so the visual style matches the rest of termrender's charts.

Never-crash / never-lie contract: real Mermaid pie grammar only permits the
header, ``title``/``accTitle``/``accDescr``/``%%``-comment lines, and slice
declarations — everything else is a parse error. A line that doesn't match
one of those, or a negative slice value (Mermaid rejects negative pie
values), degrades the *whole* diagram to raw source rather than rendering a
plausible-but-wrong chart with the bad line silently dropped.
"""

from __future__ import annotations

import math
import re

from termrender.blocks import Block, BlockType
from termrender.renderers.charts import render_bar
from termrender.renderers.mermaid_text import decode_entities

_TITLE_RE = re.compile(r"^\s*title\s+(.*\S)\s*$", re.IGNORECASE)
_ACC_RE = re.compile(r"^\s*acc(?:Title|Descr)\b", re.IGNORECASE)
_COMMENT_RE = re.compile(r"^\s*%%")
_HEADER_RE = re.compile(r"^\s*pie\b(?:\s+showData\b)?\s*(.*)$", re.IGNORECASE)
# Group 1: double-quoted label body (escaped quotes allowed, unescaped below).
# Group 2: single-quoted label body.
_DATA_RE = re.compile(
    r'^\s*(?:"((?:[^"\\]|\\.)*)"|\'([^\']*)\')\s*:\s*(-?\d+(?:\.\d+)?)\s*$'
)


def _unescape_double_quoted(label: str) -> str:
    return decode_entities(label.replace('\\"', '"').replace("\\\\", "\\"))


def parse_pie(source: str) -> tuple[str | None, list[dict]]:
    """Parse mermaid pie syntax into ``(title, items)``.

    ``items`` is a list of ``{"label": str, "value": float}`` dicts, in
    source order. Blank lines, ``%%`` comments, and ``accTitle``/
    ``accDescr`` lines are legitimate Mermaid ignorables and are skipped.
    Any other line that isn't the header, a ``title``, or a
    ``"label" : value`` slice (double- or single-quoted, with escaped
    quotes supported in double-quoted labels) is invalid Mermaid grammar;
    a negative slice value is likewise invalid (Mermaid rejects negative
    pie values). Either case discards everything parsed so far and
    returns ``(None, [])`` so the caller falls back to raw source instead
    of rendering a partial, misleading chart.
    """
    title: str | None = None
    items: list[dict] = []
    for line in source.splitlines():
        if not line.strip():
            continue
        if _COMMENT_RE.match(line) or _ACC_RE.match(line):
            continue
        m = _HEADER_RE.match(line)
        if m:
            # Mermaid allows the title inline on the header line:
            # ``pie title X`` / ``pie showData title X``. Anything else
            # trailing the header is invalid grammar.
            tail = m.group(1)
            if tail:
                tm = _TITLE_RE.match(tail)
                if not tm:
                    return None, []
                title = tm.group(1)
            continue
        m = _TITLE_RE.match(line)
        if m:
            title = m.group(1)
            continue
        m = _DATA_RE.match(line)
        if m:
            if m.group(1) is not None:
                label = _unescape_double_quoted(m.group(1))
            else:
                label = decode_entities(m.group(2))
            value = float(m.group(3))
            if value < 0 or not math.isfinite(value):
                return None, []
            items.append({"label": label, "value": value})
            continue
        # Invalid grammar: not header, title, acc line, comment, or data.
        return None, []
    return title, items


def render(source: str, width: int) -> list[str]:
    """Render mermaid pie syntax as a labeled horizontal bar chart.

    Each bar's value is annotated with its percentage share of the total.
    Diagrams with no parseable data lines (including diagrams degraded by
    ``parse_pie`` due to invalid grammar or a negative value) degrade to
    the raw source text.
    """
    title, items = parse_pie(source)
    if not items:
        return source.splitlines() or [""]

    total = sum(it["value"] for it in items) or 1.0
    if not math.isfinite(total):
        return source.splitlines() or [""]
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
