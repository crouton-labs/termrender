"""Native renderer for mermaid ``journey`` diagrams.

Mermaid journey grammar (subset)::

    journey
        title My working day
        section Go to work
          Make tea: 5: Me
          Go upstairs: 3: Me
          Do work: 1: Me, Cat
        section Go home
          Go downstairs: 5: Me

Each section is a group of tasks; each task is ``name: score: actors``
(``actors`` a comma-separated list, ``score`` a 1-5 satisfaction rating).
A journey is a two-level outline (section -> tasks) — the same shape
``tree.py`` renders — so sections become depth-0 tree labels and tasks
become their depth-1 children, reusing ``tree.py``'s guide-line rendering
via a synthetic ``Block`` rather than duplicating it (mirrors how
``mermaid_pie.py`` reuses ``charts.py``'s ``render_bar``).
"""

from __future__ import annotations

import re

from termrender.blocks import Block, BlockType
from termrender.renderers.tree import render as render_tree
from termrender.style import visual_ljust

_HEADER_RE = re.compile(r"^\s*journey\b", re.IGNORECASE)
_TITLE_RE = re.compile(r"^\s*title\s+(.*\S)\s*$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^\s*section\s+(.*\S)\s*$", re.IGNORECASE)


def parse_journey(source: str) -> dict:
    """Parse mermaid journey syntax into a title + section/task tree.

    Task lines with fewer than two ``:``-separated fields (no score) are
    still captured with ``score=None``; a non-numeric score is likewise
    tolerated (``score=None``) rather than raising. A task line before any
    ``section`` header lands in an unnamed leading section. Sections with
    no tasks are dropped. ``%%`` comment and directive lines are skipped
    wherever they appear in the body, not just in the leading prelude.

    Returns ``{"title": str | None, "sections": [{"name": str | None,
    "tasks": [{"name": str, "score": int | None, "actors": list[str]}]}]}``.
    """
    title: str | None = None
    sections: list[dict] = [{"name": None, "tasks": []}]

    for line in source.splitlines():
        if not line.strip() or _HEADER_RE.match(line):
            continue
        if line.strip().startswith("%%"):
            continue

        m = _TITLE_RE.match(line)
        if m:
            title = m.group(1)
            continue

        m = _SECTION_RE.match(line)
        if m:
            sections.append({"name": m.group(1), "tasks": []})
            continue

        if ":" not in line:
            continue
        parts = line.split(":", 2)
        name = parts[0].strip()
        if not name:
            continue
        score: int | None = None
        actors: list[str] = []
        if len(parts) >= 2:
            score_str = parts[1].strip()
            if score_str.lstrip("-").isdigit():
                score = int(score_str)
        if len(parts) >= 3:
            actors = [a.strip() for a in parts[2].split(",") if a.strip()]
        sections[-1]["tasks"].append({"name": name, "score": score, "actors": actors})

    sections = [s for s in sections if s["tasks"]]
    return {"title": title, "sections": sections}


def _format_task(task: dict) -> str:
    """Render one task as ``name  \u2605\u2605\u2605\u2606\u2606  (actor, actor)``."""
    label = task["name"]
    if task["score"] is not None:
        filled = max(0, min(5, task["score"]))
        stars = "\u2605" * filled + "\u2606" * (5 - filled)
        label = f"{label}  {stars}"
    if task["actors"]:
        label = f"{label}  ({', '.join(task['actors'])})"
    return label


def render(source: str, width: int) -> list[str]:
    """Render mermaid journey syntax as a section/task guide-line tree.

    A diagram with no parseable tasks degrades to the raw source text.
    """
    parsed = parse_journey(source)
    sections = parsed["sections"]
    if not sections:
        return source.splitlines() or [""]

    lines: list[str] = []
    if parsed["title"]:
        lines.append(visual_ljust(parsed["title"], width))

    tree_lines: list[str] = []
    for section in sections:
        if section["name"]:
            tree_lines.append(section["name"])
            tree_lines.extend(f"  {_format_task(t)}" for t in section["tasks"])
        else:
            tree_lines.extend(_format_task(t) for t in section["tasks"])

    block = Block(type=BlockType.TREE, attrs={"source": "\n".join(tree_lines)}, width=width)
    lines.extend(render_tree(block, color=False))
    return lines
