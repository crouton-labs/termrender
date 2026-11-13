"""Native renderer for mermaid ``xychart`` / ``xychart-beta`` diagrams.

Mermaid xychart grammar (subset)::

    xychart-beta [horizontal|vertical]
        title "Optional title"
        x-axis "Optional title" [cat A, "cat B", cat C]
        x-axis "Optional title" 0 --> 100        (numeric x axis)
        y-axis "Optional title" 0 --> 5
        bar [4, 3, 1]
        line [2, 3, 4]

A terminal has rows, not pixels, so every chart is drawn as labelled
horizontal bars, one row per x category, whatever the declared orientation.
Each ``bar`` and ``line`` series becomes one group of rows. Bars are scaled
against the y-axis range when one is given (so ``3`` on a ``0 --> 5`` axis
fills 60% of the bar), else against ``0`` to the largest value.

Never-crash / never-lie contract: any line outside the grammar, a series
whose length differs from the category count, a non-finite value, or a chart
with no series degrades the whole diagram to a raw echo of the source.
"""

from __future__ import annotations

import math
import re

from termrender.renderers.charts import _draw_bar, _format_value
from termrender.renderers.mermaid_degradation import raw_echo
from termrender.renderers.mermaid_text import decode_entities
from termrender.style import visual_len, visual_ljust

_NUM = r"-?\d+(?:\.\d+)?"
_HEADER_RE = re.compile(r"^\s*xychart(?:-beta)?(?:\s+(horizontal|vertical))?\s*$", re.IGNORECASE)
_COMMENT_RE = re.compile(r"^\s*%%")
_ACC_RE = re.compile(r"^\s*acc(?:Title|Descr)\b", re.IGNORECASE)
_TITLE_RE = re.compile(r'^\s*title\s+(?:"([^"]*)"|(.*\S))\s*$', re.IGNORECASE)
_AXIS_RE = re.compile(r'^\s*([xy])-axis\b\s*(?:"([^"]*)"|([^\s\["]+))?\s*(.*?)\s*$', re.IGNORECASE)
_RANGE_RE = re.compile(rf"^({_NUM})\s*-->\s*({_NUM})$")
_SERIES_RE = re.compile(r'^\s*(bar|line)\b\s*(?:"([^"]*)"\s*)?\[(.*)\]\s*$', re.IGNORECASE)


class _Invalid(Exception):
    pass


def _split_list(body: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(r'\s*(?:"([^"]*)"|([^,]*?))\s*(?:,|$)', body):
        if m.end() == m.start():
            break
        val = m.group(1) if m.group(1) is not None else m.group(2)
        out.append(val)
    if out and out[-1] == "" and body.rstrip().endswith(","):
        raise _Invalid
    if out == [""]:
        return []
    return out


def parse_xychart(source: str) -> dict | None:
    """Parse xychart source; return ``None`` on any invalid grammar."""
    chart: dict = {"title": None, "categories": None, "x_title": None,
                   "x_range": None, "y_title": None, "y_range": None, "series": []}
    seen_header = False
    try:
        for line in source.splitlines():
            if not line.strip() or _COMMENT_RE.match(line) or _ACC_RE.match(line):
                continue
            if not seen_header:
                if not _HEADER_RE.match(line):
                    return None
                seen_header = True
                continue
            m = _TITLE_RE.match(line)
            if m:
                chart["title"] = decode_entities(m.group(1) if m.group(1) is not None else m.group(2))
                continue
            m = _SERIES_RE.match(line)
            if m:
                values = [float(v) for v in _split_list(m.group(3))]
                if not values or not all(math.isfinite(v) for v in values):
                    return None
                chart["series"].append({"kind": m.group(1).lower(), "name": m.group(2), "values": values})
                continue
            m = _AXIS_RE.match(line)
            if m:
                axis = m.group(1).lower()
                title = m.group(2) if m.group(2) is not None else m.group(3)
                rest = m.group(4)
                # An unquoted token that is really the range start belongs to rest.
                if m.group(3) is not None and _RANGE_RE.match(f"{m.group(3)} {rest}".strip()):
                    rest, title = f"{m.group(3)} {rest}".strip(), None
                if title is not None:
                    chart[f"{axis}_title"] = decode_entities(title)
                if not rest:
                    continue
                rm = _RANGE_RE.match(rest)
                if rm:
                    lo, hi = float(rm.group(1)), float(rm.group(2))
                    if hi <= lo:
                        return None
                    chart[f"{axis}_range"] = (lo, hi)
                    continue
                if axis == "x" and rest.startswith("[") and rest.endswith("]"):
                    chart["categories"] = [decode_entities(c) for c in _split_list(rest[1:-1])]
                    continue
                return None
            return None
    except (_Invalid, ValueError):
        return None
    if not seen_header or not chart["series"]:
        return None
    n = len(chart["series"][0]["values"])
    if any(len(s["values"]) != n for s in chart["series"]):
        return None
    if chart["categories"] is None:
        if chart["x_range"]:
            lo, hi = chart["x_range"]
            step = (hi - lo) / (n - 1) if n > 1 else 0
            chart["categories"] = [_format_value(round(lo + i * step, 2)) for i in range(n)]
        else:
            chart["categories"] = [str(i + 1) for i in range(n)]
    if len(chart["categories"]) != n:
        return None
    return chart


def render(source: str, width: int) -> list[str]:
    chart = parse_xychart(source)
    if chart is None:
        return raw_echo(source)

    all_values = [v for s in chart["series"] for v in s["values"]]
    lo, hi = chart["y_range"] or (min(0.0, min(all_values)), max(all_values))
    if hi <= lo:
        hi = lo + 1

    labels = chart["categories"]
    label_w = max(visual_len(l) for l in labels)
    value_strs = [[_format_value(v) for v in s["values"]] for s in chart["series"]]
    value_w = max(visual_len(v) for vs in value_strs for v in vs)
    bar_w = max(width - label_w - value_w - 4, 5)

    lines: list[str] = []
    if chart["title"]:
        lines.append(chart["title"])
    axis_note = []
    if chart["x_title"]:
        axis_note.append(chart["x_title"])
    if chart["y_title"] or chart["y_range"]:
        rng = f"{_format_value(lo)}–{_format_value(hi)}"
        axis_note.append(f"{chart['y_title']} ({rng})" if chart["y_title"] else rng)
    if axis_note:
        lines.append(" × ".join(axis_note))
    multi = len(chart["series"]) > 1
    for idx, (s, vs) in enumerate(zip(chart["series"], value_strs)):
        if multi:
            if idx:
                lines.append("")
            lines.append(s["name"] or f"{s['kind']} {idx + 1}")
        for label, v, vstr in zip(labels, s["values"], vs):
            ratio = (v - lo) / (hi - lo)
            lines.append(f"{visual_ljust(label, label_w)}  {_draw_bar(bar_w, ratio)}  {vstr.rjust(value_w)}")
    return lines
