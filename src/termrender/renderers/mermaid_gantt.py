"""Native renderer for mermaid ``gantt`` diagrams.

Mermaid gantt grammar (core subset)::

    gantt
        title A Gantt Diagram
        dateFormat YYYY-MM-DD
        section Section A
        Task1 :a1, 2024-01-01, 30d
        Task2 :after a1, 20d
        section Section B
        Task3 : 2024-02-01, 2024-02-10

Rendered as section-grouped rows with a horizontal time-span bar per task,
scaled to the overall date range — the gantt analogue of a timeline, per the
ratified plan in ``mermaid-inline-rendering.md``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from termrender.style import visual_len, visual_ljust

_HEADER_RE = re.compile(r"^\s*gantt\b", re.IGNORECASE)
_TITLE_RE = re.compile(r"^\s*title\s+(.*\S)\s*$", re.IGNORECASE)
_DATEFORMAT_RE = re.compile(r"^\s*dateFormat\s+(\S+)\s*$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^\s*section\s+(.*\S)\s*$", re.IGNORECASE)
_SKIP_RE = re.compile(
    r"^\s*(?:excludes|includes|axisFormat|todayMarker|weekend|tickInterval)\b",
    re.IGNORECASE,
)
_STATUS_TOKENS = {"done", "active", "crit", "milestone", "vert"}
_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(d|w|h|m|s)$", re.IGNORECASE)
_ID_RE = re.compile(r"^[A-Za-z_][\w-]*$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}

# Mermaid dateFormat tokens, longest-first so e.g. "YYYY" isn't partially
# consumed by a "YY" replacement first.
_DATE_TOKEN_MAP = [
    ("YYYY", "%Y"),
    ("YY", "%y"),
    ("MM", "%m"),
    ("DD", "%d"),
    ("HH", "%H"),
    ("mm", "%M"),
    ("ss", "%S"),
]


def _strptime_format(date_format: str) -> str:
    """Translate a mermaid ``dateFormat`` token string to a strptime pattern."""
    out = date_format
    for token, code in _DATE_TOKEN_MAP:
        out = out.replace(token, code)
    return out


def _parse_date(token: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(token, fmt)
    except ValueError:
        return None


def parse_gantt(source: str) -> dict:
    """Parse the core mermaid gantt grammar into a title + section/task tree.

    Handles ``dateFormat``, ``title``, ``section``, and task lines of the
    form ``name : [status,] [id,] [start-date|after id,] duration-or-end``.
    Lines that don't match a recognized shape (``excludes``, ``axisFormat``,
    a task with no resolvable start anchor, …) are skipped rather than
    raising — agents emit a wide variety of gantt dialects and an unparseable
    line must degrade, not crash.

    Returns ``{"title": str | None, "sections": [{"name": str | None,
    "tasks": [{"label": str, "start": datetime, "end": datetime}]}]}``.
    Sections with no successfully parsed tasks are dropped.
    """
    fmt = "%Y-%m-%d"
    title: str | None = None
    sections: list[dict] = [{"name": None, "tasks": []}]
    ids: dict[str, datetime] = {}
    last_end: datetime | None = None

    for line in source.splitlines():
        if not line.strip() or _HEADER_RE.match(line) or _SKIP_RE.match(line):
            continue

        m = _TITLE_RE.match(line)
        if m:
            title = m.group(1)
            continue

        m = _DATEFORMAT_RE.match(line)
        if m:
            fmt = _strptime_format(m.group(1))
            continue

        m = _SECTION_RE.match(line)
        if m:
            sections.append({"name": m.group(1), "tasks": []})
            continue

        if ":" not in line:
            continue
        label, _, spec = line.partition(":")
        label = label.strip()
        if not label:
            continue

        task_id: str | None = None
        start: datetime | None = None
        end: datetime | None = None
        duration: timedelta | None = None
        after_ids: list[str] = []

        for raw_tok in spec.split(","):
            tok = raw_tok.strip()
            if not tok:
                continue
            low = tok.lower()
            if low in _STATUS_TOKENS:
                continue
            if low.startswith("after "):
                after_ids.extend(tok[len("after "):].split())
                continue
            dm = _DURATION_RE.match(tok)
            if dm:
                amount, unit = float(dm.group(1)), dm.group(2).lower()
                duration = timedelta(seconds=amount * _UNIT_SECONDS[unit])
                continue
            dt = _parse_date(tok, fmt)
            if dt is not None:
                if start is None:
                    start = dt
                else:
                    end = dt
                continue
            if task_id is None and _ID_RE.match(tok):
                task_id = tok
                continue
            # Unrecognized token (e.g. an unmapped status keyword): ignore
            # and keep scanning the remaining tokens on this line.

        if start is None:
            if after_ids:
                resolved = [ids[i] for i in after_ids if i in ids]
                start = max(resolved) if resolved else last_end
            else:
                start = last_end

        if start is None:
            # No date, no "after" dependency, no prior task to anchor to —
            # this task can't be placed on the timeline. Skip it.
            continue

        if end is None:
            end = start + duration if duration is not None else start + timedelta(days=1)
        if end < start:
            end = start

        sections[-1]["tasks"].append({"label": label, "start": start, "end": end})
        last_end = end
        if task_id:
            ids[task_id] = end

    sections = [s for s in sections if s["tasks"]]
    return {"title": title, "sections": sections}


def _draw_span(width: int, start_ratio: float, end_ratio: float) -> str:
    """Draw a ``width``-wide track with a filled span from start to end ratio."""
    if width <= 0:
        return ""
    start_col = max(0, min(int(round(start_ratio * width)), width))
    end_col = max(start_col + 1, min(int(round(end_ratio * width)), width))
    return "░" * start_col + "█" * (end_col - start_col) + "░" * (width - end_col)


def _fmt_range(task: dict) -> str:
    start, end = task["start"], task["end"]
    if start.date() == end.date():
        return start.strftime("%Y-%m-%d")
    return f"{start:%Y-%m-%d}\u2192{end:%Y-%m-%d}"


def render(source: str, width: int) -> list[str]:
    """Render mermaid gantt syntax as section-grouped rows with time-span bars.

    Diagrams with no parseable tasks degrade to the raw source text.
    """
    parsed = parse_gantt(source)
    tasks = [t for s in parsed["sections"] for t in s["tasks"]]
    if not tasks:
        return source.splitlines() or [""]

    min_start = min(t["start"] for t in tasks)
    max_end = max(t["end"] for t in tasks)
    span = (max_end - min_start).total_seconds() or 1.0

    label_w = max(visual_len(t["label"]) for t in tasks)
    date_w = max(visual_len(_fmt_range(t)) for t in tasks)
    bar_w = max(width - label_w - date_w - 4, 5)

    lines: list[str] = []
    if parsed["title"]:
        lines.append(visual_ljust(parsed["title"], width))

    for section in parsed["sections"]:
        if section["name"]:
            lines.append(visual_ljust(section["name"], width))
        for t in section["tasks"]:
            start_ratio = (t["start"] - min_start).total_seconds() / span
            end_ratio = (t["end"] - min_start).total_seconds() / span
            bar = _draw_span(bar_w, start_ratio, end_ratio)
            label = visual_ljust(t["label"], label_w)
            date_str = _fmt_range(t).rjust(date_w)
            lines.append(visual_ljust(f"{label}  {bar}  {date_str}", width))

    return lines
