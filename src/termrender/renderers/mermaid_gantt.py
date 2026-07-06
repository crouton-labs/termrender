"""Native renderer for mermaid ``gantt`` diagrams.

Mermaid gantt grammar (core subset)::

    gantt
        title A Gantt Diagram
        dateFormat YYYY-MM-DD
        excludes weekends
        section Section A
        Task1 :a1, 2024-01-01, 30d
        Task2 :after a1, 20d
        Task3 :milestone, m1, 2024-02-15, 0d
        Task4 :until a1

Rendered as section-grouped rows with a horizontal time-span bar per task,
scaled to the overall date range — the gantt analogue of a timeline, per the
ratified plan in ``mermaid-inline-rendering.md``. Milestones render as a
single point marker instead of a span.

Never-crash contract: a diagram that uses a construct we don't implement
(an invalid ``dateFormat``, a numeric overflow, an ``until`` reference to an
unknown task id, an unsupported ``excludes``/``includes`` form, ...)
degrades the *entire* diagram to raw source rather than guessing — see
``_Unsupported`` below.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from termrender.style import visual_len, visual_ljust

_HEADER_RE = re.compile(r"^\s*gantt\b", re.IGNORECASE)
_TITLE_RE = re.compile(r"^\s*title\s+(.*\S)\s*$", re.IGNORECASE)
_DATEFORMAT_RE = re.compile(r"^\s*dateFormat\s+(\S+)\s*$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^\s*section\s+(.*\S)\s*$", re.IGNORECASE)
_EXCLUDES_RE = re.compile(r"^\s*excludes\s+(.*\S)\s*$", re.IGNORECASE)
_INCLUDES_RE = re.compile(r"^\s*includes\s+(.*\S)\s*$", re.IGNORECASE)
_SKIP_RE = re.compile(
    r"^\s*(?:axisFormat|todayMarker|weekend|tickInterval)\b",
    re.IGNORECASE,
)
_COMMENT_RE = re.compile(r"%%.*$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
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


class _Unsupported(Exception):
    """Internal signal: the diagram uses a construct we can't safely
    render (invalid dateFormat, numeric overflow, an unresolvable
    ``until`` reference, an unimplemented ``excludes``/``includes`` form,
    ...). Caught by ``parse_gantt``, which degrades the whole diagram to
    raw source rather than rendering a guess.
    """


def _strptime_format(date_format: str) -> str:
    """Translate a mermaid ``dateFormat`` token string to a strptime pattern."""
    out = date_format
    for token, code in _DATE_TOKEN_MAP:
        out = out.replace(token, code)
    return out


def _valid_strptime_format(fmt: str) -> bool:
    """Best-effort validation that ``fmt`` is usable as a strptime pattern.

    A malformed ``dateFormat`` such as ``YYYY-YYYY`` translates to
    ``%Y-%Y``, which has a duplicate named capture group; that only
    surfaces as ``re.error`` when strptime actually compiles the pattern
    to parse a value, not at translation time. Round-tripping a sample
    date through ``strftime``/``strptime`` exercises that compile step.
    """
    sample = datetime(2024, 3, 4, 5, 6, 7)
    try:
        datetime.strptime(sample.strftime(fmt), fmt)
    except (ValueError, re.error):
        return False
    return True


def _parse_date(token: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(token, fmt)
    except (ValueError, re.error):
        return None


def _parse_excludes_tokens(spec: str) -> tuple[bool, set[date]]:
    """Parse the token list of an ``excludes`` directive.

    Supports the common cases: the ``weekends`` keyword and explicit
    ``YYYY-MM-DD`` dates. Any other form (e.g. day names like ``friday``)
    isn't implemented, so it raises ``_Unsupported`` to degrade the whole
    diagram rather than silently ignoring a calendar rule that changes the
    schedule.
    """
    weekends = False
    dates: set[date] = set()
    for tok in re.split(r"[,\s]+", spec.strip()):
        if not tok:
            continue
        if tok.lower() == "weekends":
            weekends = True
            continue
        if _ISO_DATE_RE.match(tok):
            dt = _parse_date(tok, "%Y-%m-%d")
            if dt is None:
                raise _Unsupported(f"unparseable excludes date {tok!r}")
            dates.add(dt.date())
            continue
        raise _Unsupported(f"unsupported excludes token {tok!r}")
    return weekends, dates


def _parse_includes_tokens(spec: str) -> set[date]:
    """Parse the token list of an ``includes`` directive.

    Only explicit ``YYYY-MM-DD`` dates are implemented (re-including a
    specific day that ``excludes`` would otherwise skip). ``weekends``
    isn't a supported ``includes`` token — there's no "re-include every
    weekend" semantics implemented — so it raises ``_Unsupported`` to
    degrade the whole diagram rather than silently no-op-ing a directive
    that looks like it should cancel an ``excludes weekends`` rule.
    """
    dates: set[date] = set()
    for tok in re.split(r"[,\s]+", spec.strip()):
        if not tok:
            continue
        if _ISO_DATE_RE.match(tok):
            dt = _parse_date(tok, "%Y-%m-%d")
            if dt is None:
                raise _Unsupported(f"unparseable includes date {tok!r}")
            dates.add(dt.date())
            continue
        raise _Unsupported(f"unsupported includes token {tok!r}")
    return dates


def _is_excluded(
    d: date, exclude_weekends: bool, exclude_dates: set[date], include_dates: set[date]
) -> bool:
    if d in include_dates:
        return False
    if exclude_weekends and d.weekday() >= 5:
        return True
    return d in exclude_dates


def _skip_excluded(
    start: datetime,
    exclude_weekends: bool,
    exclude_dates: set[date],
    include_dates: set[date],
) -> datetime:
    """If an auto-resolved ``start`` falls on an excluded day, advance to
    the next working day."""
    if not exclude_weekends and not exclude_dates:
        return start
    while _is_excluded(start.date(), exclude_weekends, exclude_dates, include_dates):
        start = start + timedelta(days=1)
    return start


def _advance_working_days(
    start: datetime,
    days: float,
    exclude_weekends: bool,
    exclude_dates: set[date],
    include_dates: set[date],
) -> datetime:
    """Advance ``start`` by ``days`` working days, skipping excluded days
    (which extend the span but don't count toward the duration).

    Raises ``OverflowError`` (propagated to the caller as ``_Unsupported``)
    for magnitudes ``datetime`` can't represent, both to never crash on
    huge durations and to bound the day-by-day walk below.
    """
    start + timedelta(days=days)  # bounds-check before the exclusion walk
    if not exclude_weekends and not exclude_dates:
        return start + timedelta(days=days)
    whole = int(days)
    frac = days - whole
    cur = start
    remaining = whole
    while remaining > 0:
        cur = cur + timedelta(days=1)
        if _is_excluded(cur.date(), exclude_weekends, exclude_dates, include_dates):
            continue
        remaining -= 1
    if frac:
        cur = cur + timedelta(days=frac)
    return cur


def parse_gantt(source: str) -> dict:
    """Parse the core mermaid gantt grammar into a title + section/task tree.

    Handles ``dateFormat``, ``title``, ``section``, ``excludes``
    (``weekends`` and explicit dates), ``includes`` (explicit dates only),
    ``%%`` comments, ``milestone`` tasks, ``until <taskId>``, and task
    lines of the form ``name : [status,] [id,] [start-date|after id,]
    duration-or-end``. Lines that don't match a recognized shape (a task
    with no resolvable start anchor, an unrecognized status keyword, ...)
    are skipped rather than raising — agents emit a wide variety of
    gantt dialects and an unparseable line must degrade, not crash.

    A construct we can't safely resolve (an invalid ``dateFormat``, a
    numeric or date-arithmetic overflow, an ``until`` reference to an
    unknown task id, or an ``excludes``/``includes`` form beyond
    ``weekends``/explicit dates) degrades the *whole* diagram: this
    returns ``{"title": None, "sections": []}``, which the renderer
    falls back to raw source for.

    Returns ``{"title": str | None, "sections": [{"name": str | None,
    "tasks": [{"label": str, "start": datetime, "end": datetime,
    "milestone": bool}]}]}``. Sections with no successfully parsed tasks
    are dropped.
    """
    try:
        return _parse_gantt(source)
    except _Unsupported:
        return {"title": None, "sections": []}


def _parse_gantt(source: str) -> dict:
    fmt = "%Y-%m-%d"
    title: str | None = None
    sections: list[dict] = [{"name": None, "tasks": []}]
    task_ends: dict[str, datetime] = {}
    task_starts: dict[str, datetime] = {}
    last_end: datetime | None = None
    exclude_weekends = False
    exclude_dates: set[date] = set()
    include_dates: set[date] = set()

    for raw_line in source.splitlines():
        line = _COMMENT_RE.sub("", raw_line)
        if not line.strip() or _HEADER_RE.match(line) or _SKIP_RE.match(line):
            continue

        m = _TITLE_RE.match(line)
        if m:
            title = m.group(1)
            continue

        m = _DATEFORMAT_RE.match(line)
        if m:
            candidate = _strptime_format(m.group(1))
            if not _valid_strptime_format(candidate):
                raise _Unsupported(f"invalid dateFormat {m.group(1)!r}")
            fmt = candidate
            continue

        m = _SECTION_RE.match(line)
        if m:
            sections.append({"name": m.group(1), "tasks": []})
            continue

        m = _EXCLUDES_RE.match(line)
        if m:
            w, d = _parse_excludes_tokens(m.group(1))
            exclude_weekends = exclude_weekends or w
            exclude_dates |= d
            continue

        m = _INCLUDES_RE.match(line)
        if m:
            include_dates |= _parse_includes_tokens(m.group(1))
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
        duration_amount: float | None = None
        duration_unit: str | None = None
        until_id: str | None = None
        is_milestone = False
        after_ids: list[str] = []

        for raw_tok in spec.split(","):
            tok = raw_tok.strip()
            if not tok:
                continue
            low = tok.lower()
            if low in _STATUS_TOKENS:
                if low == "milestone":
                    is_milestone = True
                continue
            if low.startswith("after "):
                after_ids.extend(tok[len("after "):].split())
                continue
            if low.startswith("until "):
                until_id = tok[len("until "):].strip()
                continue
            dm = _DURATION_RE.match(tok)
            if dm:
                duration_amount, duration_unit = float(dm.group(1)), dm.group(2).lower()
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
                resolved = [task_ends[i] for i in after_ids if i in task_ends]
                start = max(resolved) if resolved else last_end
            else:
                start = last_end
            if start is not None:
                try:
                    start = _skip_excluded(
                        start, exclude_weekends, exclude_dates, include_dates
                    )
                except OverflowError:
                    raise _Unsupported("date overflow skipping excluded days") from None

        if start is None:
            # No date, no "after" dependency, no prior task to anchor to —
            # this task can't be placed on the timeline. Skip it.
            continue

        if is_milestone:
            end = start
        elif end is None:
            if until_id is not None:
                if until_id not in task_starts:
                    raise _Unsupported(f"until references unknown task {until_id!r}")
                end = task_starts[until_id]
            elif duration_amount is not None:
                try:
                    if duration_unit in ("d", "w"):
                        days = duration_amount * (7 if duration_unit == "w" else 1)
                        end = _advance_working_days(
                            start, days, exclude_weekends, exclude_dates, include_dates
                        )
                    else:
                        end = start + timedelta(
                            seconds=duration_amount * _UNIT_SECONDS[duration_unit]
                        )
                except OverflowError:
                    raise _Unsupported("duration overflow") from None
            else:
                try:
                    end = start + timedelta(days=1)
                except OverflowError:
                    raise _Unsupported("date overflow computing default end") from None
        if end < start:
            end = start

        sections[-1]["tasks"].append(
            {"label": label, "start": start, "end": end, "milestone": is_milestone}
        )
        last_end = end
        if task_id:
            task_ends[task_id] = end
            task_starts[task_id] = start

    sections = [s for s in sections if s["tasks"]]
    return {"title": title, "sections": sections}


def _draw_span(width: int, start_ratio: float, end_ratio: float) -> str:
    """Draw a ``width``-wide track with a filled span from start to end ratio."""
    if width <= 0:
        return ""
    start_col = max(0, min(int(round(start_ratio * width)), width))
    end_col = max(start_col + 1, min(int(round(end_ratio * width)), width))
    return "░" * start_col + "█" * (end_col - start_col) + "░" * (width - end_col)


def _draw_milestone(width: int, ratio: float) -> str:
    """Draw a ``width``-wide track with a single point marker (a milestone
    is an instant, not a span)."""
    if width <= 0:
        return ""
    col = max(0, min(int(round(ratio * width)), width - 1))
    return "░" * col + "◆" + "░" * (width - col - 1)


def _fmt_range(task: dict) -> str:
    start, end = task["start"], task["end"]
    if start.date() == end.date():
        return start.strftime("%Y-%m-%d")
    return f"{start:%Y-%m-%d}\u2192{end:%Y-%m-%d}"


def render(source: str, width: int) -> list[str]:
    """Render mermaid gantt syntax as section-grouped rows with time-span bars.

    Milestone tasks render as a single point marker rather than a span.
    Diagrams with no parseable tasks (including diagrams degraded by
    ``parse_gantt`` due to an unsupported construct) fall back to the raw
    source text.
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
            if t["milestone"]:
                bar = _draw_milestone(bar_w, start_ratio)
            else:
                end_ratio = (t["end"] - min_start).total_seconds() / span
                bar = _draw_span(bar_w, start_ratio, end_ratio)
            label = visual_ljust(t["label"], label_w)
            date_str = _fmt_range(t).rjust(date_w)
            lines.append(visual_ljust(f"{label}  {bar}  {date_str}", width))

    return lines
