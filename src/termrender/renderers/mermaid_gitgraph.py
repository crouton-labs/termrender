"""Native renderer for Mermaid ``gitGraph`` diagrams.

The renderer preserves Mermaid's command order and shows each branch as a
vertical lane. It supports ``commit``, ``branch``, ``checkout``, ``merge``,
and ``cherry-pick`` statements, including quoted IDs and tags.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from termrender.renderers.mermaid_degradation import raw_echo
from termrender.renderers.mermaid_prelude import strip_prelude_lines
from termrender.renderers.mermaid_text import decode_entities


_ATTRIBUTE = re.compile(
    r"(?P<key>id|tag|type|parent)\s*:\s*(?:\"(?P<quoted>(?:\\.|[^\"])*)\"|(?P<bare>[^\s]+))",
    re.IGNORECASE,
)


@dataclass
class _Event:
    kind: str
    branch: str
    lanes: tuple[str, ...]
    label: str = ""
    tags: tuple[str, ...] = ()
    merge_branch: str | None = None


def _attributes(text: str) -> dict[str, list[str]]:
    """Extract Mermaid's named statement attributes without splitting quotes."""
    attrs: dict[str, list[str]] = {}
    for match in _ATTRIBUTE.finditer(text):
        value = (
            match.group("quoted")
            if match.group("quoted") is not None
            else match.group("bare")
        )
        attrs.setdefault(match.group("key").lower(), []).append(
            decode_entities(value.replace('\\"', '"'))
        )
    return attrs


def _name_after(command: str, text: str) -> str | None:
    """Return the required unquoted branch name after a GitGraph command."""
    match = re.match(rf"{command}\s+([^\s]+)", text, re.IGNORECASE)
    return match.group(1) if match else None


def _parse(source: str) -> list[_Event] | None:
    """Parse the supported GitGraph command subset into ordered render events."""
    lines = strip_prelude_lines(source.splitlines())
    is_gitgraph = lines and re.fullmatch(
        r"\s*gitgraph(?:\s+(?:TB|BT|LR))?\s*", lines[0], re.IGNORECASE
    )
    if not is_gitgraph:
        return None

    current = "main"
    lanes = [current]
    events: list[_Event] = []
    generated_commit = 0

    for raw in lines[1:]:
        text = raw.strip()
        if not text or text.startswith("%%"):
            continue
        command = text.split(maxsplit=1)[0].lower()
        attrs = _attributes(text)

        if command == "commit":
            generated_commit += 1
            label = attrs.get("id", [f"commit {generated_commit}"])[0]
            events.append(
                _Event(
                    "commit", current, tuple(lanes), label, tuple(attrs.get("tag", []))
                )
            )
        elif command == "branch":
            branch = _name_after("branch", text)
            if branch is None or branch in lanes:
                return None
            lanes.append(branch)
            events.append(_Event("branch", current, tuple(lanes), branch))
        elif command == "checkout":
            branch = _name_after("checkout", text)
            if branch is None or branch not in lanes:
                return None
            current = branch
        elif command == "merge":
            branch = _name_after("merge", text)
            if branch is None or branch == current or branch not in lanes:
                return None
            label = attrs.get("id", [f"merge {branch}"])[0]
            events.append(
                _Event(
                    "merge",
                    current,
                    tuple(lanes),
                    label,
                    tuple(attrs.get("tag", [])),
                    branch,
                )
            )
        elif command == "cherry-pick":
            source_id = attrs.get("id", [None])[0]
            if source_id is None:
                return None
            events.append(
                _Event(
                    "commit",
                    current,
                    tuple(lanes),
                    f"cherry-pick {source_id}",
                    tuple(attrs.get("tag", [])),
                )
            )
        else:
            return None

    return events or None


def _lane_prefix(event: _Event) -> str:
    """Return the lane markers before one commit or branch declaration."""
    current_index = event.lanes.index(event.branch)
    if event.kind == "branch":
        markers = (
            "│" if index < current_index else "├"
            for index in range(current_index + 1)
        )
        return "  ".join(markers)

    markers = [
        "●" if index == current_index else "│" for index in range(len(event.lanes))
    ]
    if event.kind == "merge" and event.merge_branch is not None:
        merge_index = event.lanes.index(event.merge_branch)
        markers[merge_index] = "╱" if merge_index < current_index else "╲"
    return "  ".join(markers)


def render(source: str, width: int) -> list[str]:
    """Render Mermaid GitGraph source as a compact terminal commit graph."""
    events = _parse(source)
    if events is None:
        return raw_echo(source)

    lines: list[str] = []
    for index, event in enumerate(events):
        prefix = _lane_prefix(event)
        if event.kind == "branch":
            lines.append(f"{prefix}─ {event.label}")
            continue

        tags = " ".join(f"[{tag}]" for tag in event.tags)
        suffix = f"  {tags}" if tags else ""
        lines.append(f"{prefix}─ {event.label}{suffix}")
        if any(next_event.kind != "branch" for next_event in events[index + 1 :]):
            lines.append("  ".join("│" for _ in event.lanes))

    return lines
