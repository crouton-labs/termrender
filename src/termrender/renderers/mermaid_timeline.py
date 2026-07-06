"""Native renderer for mermaid ``timeline`` diagrams.

Mermaid timeline grammar (subset)::

    timeline
        title History of Social Media Platform
        2002 : LinkedIn
        2004 : Facebook : Google
        section 2007 - 2010
            2007 : Baidu Tieba
            2008 : Facebook Wall

A bare ``: event`` continuation line (no period before the colon) attaches
another event to the *previous* period; multiple ``: event`` segments on
one line do the same inline. This is exactly termrender's existing
``timeline.py`` primitive's shape (a period/date plus one or more events
under it), so each mermaid ``section`` becomes its own sub-timeline
rendered via a synthetic ``Block``, reusing ``timeline.py``'s bullet/
connector rendering rather than duplicating it (mirrors how
``mermaid_pie.py`` reuses ``charts.py``'s ``render_bar``).
"""

from __future__ import annotations

import re

from termrender.blocks import Block, BlockType
from termrender.renderers.timeline import render as render_timeline
from termrender.style import visual_ljust

_HEADER_RE = re.compile(r"^\s*timeline\b", re.IGNORECASE)
_TITLE_RE = re.compile(r"^\s*title\s+(.*\S)\s*$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^\s*section\s+(.*\S)\s*$", re.IGNORECASE)


def parse_timeline(source: str) -> dict:
    """Parse mermaid timeline syntax into a title + section/entry tree.

    A period-less (blank-before-``:``) line continues the most recently
    seen period in the current section; a continuation with nothing yet
    to continue (no period ever seen) is skipped rather than guessing.
    Multiple ``:``-separated events on one line each become their own
    entry, with the period label shown only on the first.

    Returns ``{"title": str | None, "sections": [{"name": str | None,
    "entries": [{"date": str, "event": str}]}]}``. Sections with no
    entries are dropped.
    """
    title: str | None = None
    sections: list[dict] = [{"name": None, "entries": []}]
    last_period: str | None = None

    for line in source.splitlines():
        if not line.strip() or _HEADER_RE.match(line):
            continue

        m = _TITLE_RE.match(line)
        if m:
            title = m.group(1)
            continue

        m = _SECTION_RE.match(line)
        if m:
            sections.append({"name": m.group(1), "entries": []})
            continue

        if ":" not in line:
            continue
        period_raw, _, rest = line.partition(":")
        period = period_raw.strip()
        events = [e.strip() for e in rest.split(":") if e.strip()]
        if not events:
            continue
        if period:
            last_period = period
            shows_date = True
        else:
            if last_period is None:
                continue  # nothing established yet to continue
            # A period-less line continues the previous row visually; its
            # own date column stays blank even for its first event (the
            # period was already printed on the row it first appeared).
            shows_date = False
        for i, event in enumerate(events):
            date = last_period if (i == 0 and shows_date) else ""
            sections[-1]["entries"].append({"date": date, "event": event})

    sections = [s for s in sections if s["entries"]]
    return {"title": title, "sections": sections}


def render(source: str, width: int) -> list[str]:
    """Render mermaid timeline syntax as section-grouped vertical timelines.

    A diagram with no parseable entries degrades to the raw source text.
    """
    parsed = parse_timeline(source)
    sections = parsed["sections"]
    if not sections:
        return source.splitlines() or [""]

    lines: list[str] = []
    if parsed["title"]:
        lines.append(visual_ljust(parsed["title"], width))

    for i, section in enumerate(sections):
        if section["name"]:
            lines.append(visual_ljust(section["name"], width))
        block = Block(
            type=BlockType.TIMELINE,
            attrs={"entries": section["entries"], "color": "cyan"},
            width=width,
        )
        lines.extend(render_timeline(block, color=False))
        if i < len(sections) - 1:
            lines.append(visual_ljust("", width))

    return lines
