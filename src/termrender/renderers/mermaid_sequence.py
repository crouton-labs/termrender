"""Native ASCII renderer for mermaid ``sequenceDiagram`` sources.

Standalone module: exposes a single pure function, ``render_sequence``,
wired into ``mermaid.py``'s dispatcher for any source whose first
non-blank (post-prelude) line starts with ``sequenceDiagram``. This
module has no dependency on ``Block`` or the rest of the renderer
pipeline beyond the shared prelude-skipping helper.

Layout model
------------
Participants become columns (a lifeline ``│`` per column, boxed labels
at top and bottom). Messages render in declaration order, top to bottom,
as horizontal arrows between two columns; a message from/to the same
column becomes a small loop drawn to the right of its lifeline. Column
spacing is computed once, bottom-up from participant label widths and
the messages that cross each gap (a message spanning two adjacent
columns needs a wide-enough gap; a message spanning several columns
distributes the requirement across the gaps it crosses) — this is a 1D
constraint pass, not a 2D layout search: message order already fixes
the vertical axis, and declaration order fixes the column axis.

Grammar supported
------------------
``participant``/``actor`` (with ``as`` aliases) and implicit participants
introduced by first use in a message or note; all eight core arrow forms
(``->``, ``-->``, ``->>``, ``-->>``, ``-x``, ``--x``, ``-)``, ``--)``);
``Note over/left of/right of``; ``autonumber`` (with optional start/step);
``activate``/``deactivate`` (including the ``+``/``-`` arrow-decoration
shorthand) and ``<br/>`` are tolerated and flattened (no visual effect).
``loop``/``alt``/``opt``/``par``/``critical``/``break``/``rect``/``box``
open a horizontal separator band (with ``else``/``and``/``option`` as a
mid-band separator inside one); a stray separator/``end`` with no open
block, or any other unrecognized line, degrades to a plain text line
rather than raising.

Known degradations (by design, not bugs)
-----------------------------------------
- A ``Note left of`` the first participant, or block/plain labels wider
  than the diagram, may overflow the canvas to the left/right; overflow
  is acceptable (matching the existing flowchart renderer's contract),
  never corruption or a crash.
- ``Note over``/``left of``/``right of`` with more than one participant
  listed uses the first-and-last (or first, for left/right of) named
  participant only — mirrors the simplification already used by the
  Go-backed renderer's ``Note`` preprocessing.
- Participants are never created/destroyed mid-diagram; every lifeline
  spans the full height of the diagram.
- Column/row placement is character-index-based, not visual-width-based
  (``_Row`` indexes by ``len()``, not ``visual_len()``); wide (CJK/full-width)
  participant labels or message text will misalign columns. This mirrors
  the pre-existing ``wrap_text()`` CJK limitation elsewhere in termrender
  (see the root CLAUDE.md); fixing it here requires the same visual-width
  rework, out of scope for this renderer alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from termrender.renderers.mermaid_prelude import strip_prelude_lines
from termrender.renderers.mermaid_text import BREAK_RE, decode_entities
from termrender.style import visual_center, visual_len

__all__ = ["render_sequence", "SequenceDiagramError"]


class SequenceDiagramError(Exception):
    """Raised when source cannot be parsed as a mermaid sequence diagram."""


# --------------------------------------------------------------------------
# Parsed event model
# --------------------------------------------------------------------------


@dataclass
class Participant:
    id: str
    label: str


@dataclass
class Arrow:
    source: str
    target: str
    dashed: bool
    head_kind: str  # "filled" | "open" | "lost" | "async"
    text: str
    number: int | None = None


@dataclass
class NoteEvent:
    participants: list[str]
    position: str  # "over" | "left" | "right"
    text: str


@dataclass
class BlockBoundary:
    kind: str  # "start" | "sep" | "end"
    label: str


@dataclass
class PlainLabel:
    text: str


Event = Arrow | NoteEvent | BlockBoundary | PlainLabel


# --------------------------------------------------------------------------
# Grammar
# --------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"^%%")
_BR_RE = BREAK_RE
_AUTONUMBER_RE = re.compile(r"^autonumber(?:\s+(\d+))?(?:\s+(\d+))?\s*$", re.IGNORECASE)
_ACTIVATE_RE = re.compile(r"^(?:activate|deactivate)\s+\S+\s*$", re.IGNORECASE)
_PARTICIPANT_RE = re.compile(
    r"^(?:participant|actor)\s+(\S+)(?:\s+as\s+(.+))?\s*$", re.IGNORECASE
)
_NOTE_RE = re.compile(
    r"^[Nn]ote\s+(over|left\s+of|right\s+of)\s+([^:]+?)\s*:\s*(.*)$"
)
_BLOCK_START_RE = re.compile(
    r"^(loop|alt|opt|par|critical|break|rect|box)\b\s*(.*)$", re.IGNORECASE
)
_BLOCK_SEP_RE = re.compile(r"^(else|and|option)\b\s*(.*)$", re.IGNORECASE)
_BLOCK_END_RE = re.compile(r"^end\s*$", re.IGNORECASE)
# Arrow forms: "-{1,2}" dash count marks solid vs dashed; the marker after it
# picks the arrowhead. Handles all 8 combinations: ->, -->, ->>, -->>, -x,
# --x, -), --). An optional +/- right after the arrow (activate/deactivate
# shorthand) is captured and discarded.
#
# Identifiers deliberately exclude '-' (and ':', '+', whitespace): dash is
# reserved for the arrow itself, so an id token is the maximal run up to the
# first dash. Without this exclusion, non-mermaid dash punctuation next to a
# real arrow char (e.g. "A-.->B", a flowchart-only dotted arrow with no
# sequence-diagram equivalent) gets silently absorbed into the id instead of
# failing to match and degrading to a plain line.
_ID = r"[^\s:+-]+"
_ARROW_RE = re.compile(
    rf"^({_ID})\s*(-{{1,2}})(>>|>|x|\))\s*([+-]?)({_ID})\s*:\s*(.*)$"
)

_HEAD_KIND = {">>": "filled", ">": "open", "x": "lost", ")": "async"}
_HEAD_GLYPH = {
    "filled": {"right": "▶", "left": "◀"},
    "open": {"right": "\u203a", "left": "\u2039"},  # › ‹
    "lost": {"right": "\u2717", "left": "\u2717"},  # ✗
    "async": {"right": ")", "left": "("},
}
_LINE_CHAR = {False: "\u2500", True: "\u254c"}  # solid ─ / dashed ╌

_MIN_ARROW_GAP = 6
_MIN_SELF_GAP = 6
_BOX_PAD = 3


def _flatten(text: str) -> str:
    return decode_entities(_BR_RE.sub(" / ", text)) if text else ""


def _format_label(ev: Arrow) -> str:
    text = _flatten(ev.text)
    if ev.number is not None:
        return f"{ev.number}: {text}" if text else f"{ev.number}:"
    return text


def _note_position(raw: str) -> str:
    low = raw.lower()
    if low == "over":
        return "over"
    return "left" if "left" in low else "right"


def _parse(lines: list[str]) -> tuple[list[Participant], list[Event]]:
    participants: dict[str, Participant] = {}
    events: list[Event] = []
    stack: list[str] = []
    seen_header = False
    autonumber_active = False
    autonumber_next = 1
    autonumber_step = 1

    def register(pid: str) -> None:
        if pid not in participants:
            participants[pid] = Participant(id=pid, label=pid)

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if not seen_header:
            if line.lower().startswith("sequencediagram"):
                seen_header = True
            continue
        if _COMMENT_RE.match(line):
            continue

        m = _AUTONUMBER_RE.match(line)
        if m:
            autonumber_active = True
            if m.group(1):
                autonumber_next = int(m.group(1))
            if m.group(2):
                autonumber_step = int(m.group(2))
            continue

        if _ACTIVATE_RE.match(line):
            continue

        m = _PARTICIPANT_RE.match(line)
        if m:
            pid, alias = m.group(1), m.group(2)
            label = decode_entities(alias.strip()) if alias else pid
            if pid in participants:
                if alias:
                    participants[pid].label = label
            else:
                participants[pid] = Participant(id=pid, label=label)
            continue

        m = _NOTE_RE.match(line)
        if m:
            position_raw, who, text = m.group(1), m.group(2), m.group(3)
            who_ids = [w.strip() for w in who.split(",") if w.strip()]
            for w in who_ids:
                register(w)
            events.append(
                NoteEvent(
                    participants=who_ids,
                    position=_note_position(position_raw),
                    text=_flatten(text),
                )
            )
            continue

        m = _BLOCK_START_RE.match(line)
        if m:
            keyword, rest = m.group(1), m.group(2).strip()
            label = f"{keyword} {rest}".strip() if rest else keyword
            stack.append(label)
            events.append(BlockBoundary(kind="start", label=label))
            continue

        m = _BLOCK_SEP_RE.match(line)
        if m:
            keyword, rest = m.group(1), m.group(2).strip()
            label = f"{keyword} {rest}".strip() if rest else keyword
            if stack:
                events.append(BlockBoundary(kind="sep", label=label))
            else:
                events.append(PlainLabel(text=_flatten(line)))
            continue

        if _BLOCK_END_RE.match(line):
            if stack:
                stack.pop()
                events.append(BlockBoundary(kind="end", label=""))
            continue

        m = _ARROW_RE.match(line)
        if m:
            source, dashes, marker, _decor, target, text = m.groups()
            register(source)
            register(target)
            number = None
            if autonumber_active:
                number = autonumber_next
                autonumber_next += autonumber_step
            events.append(
                Arrow(
                    source=source,
                    target=target,
                    dashed=len(dashes) == 2,
                    head_kind=_HEAD_KIND[marker],
                    text=text.strip(),
                    number=number,
                )
            )
            continue

        events.append(PlainLabel(text=_flatten(line)))

    return list(participants.values()), events


# --------------------------------------------------------------------------
# Column layout
# --------------------------------------------------------------------------


def _layout_columns(
    participants: list[Participant], events: list[Event]
) -> tuple[list[int], list[int]]:
    n = len(participants)
    if n == 0:
        return [], []

    id_index = {p.id: i for i, p in enumerate(participants)}
    box_widths = [visual_len(p.label) + 4 for p in participants]
    gaps = [
        box_widths[i] // 2 + box_widths[i + 1] // 2 + _BOX_PAD for i in range(n - 1)
    ]

    for ev in events:
        if not isinstance(ev, Arrow):
            continue
        if ev.source not in id_index or ev.target not in id_index:
            continue
        si, ti = id_index[ev.source], id_index[ev.target]
        label_text = _format_label(ev)
        if si == ti:
            if si < n - 1:
                required = max(visual_len(label_text) + 4, _MIN_SELF_GAP)
                gaps[si] = max(gaps[si], required)
            continue

        lo, hi = (si, ti) if si < ti else (ti, si)
        required = max(visual_len(label_text) + 2, _MIN_ARROW_GAP)
        if hi == lo + 1:
            gaps[lo] = max(gaps[lo], required)
        else:
            span = range(lo, hi)
            count = hi - lo
            current = sum(gaps[i] for i in span)
            if current < required:
                deficit = required - current
                share, rem = divmod(deficit, count)
                for j, i in enumerate(span):
                    gaps[i] += share + (1 if j < rem else 0)

    centers = [0] * n
    centers[0] = box_widths[0] // 2
    for i in range(1, n):
        centers[i] = centers[i - 1] + gaps[i - 1]
    return centers, box_widths


# --------------------------------------------------------------------------
# Row rendering
# --------------------------------------------------------------------------


class _Row:
    """A growable line of characters, addressed by absolute column."""

    __slots__ = ("chars",)

    def __init__(self, width: int) -> None:
        self.chars: list[str] = [" "] * max(width, 0)

    def set(self, x: int, s: str) -> None:
        if x < 0 or not s:
            return
        end = x + len(s)
        if end > len(self.chars):
            self.chars.extend([" "] * (end - len(self.chars)))
        for i, ch in enumerate(s):
            self.chars[x + i] = ch

    def to_string(self) -> str:
        return "".join(self.chars).rstrip()


def _lifeline_row(diagram_width: int, centers: list[int]) -> _Row:
    row = _Row(diagram_width)
    for x in centers:
        row.set(x, "\u2502")  # │
    return row


def _participant_box(width: int, label: str) -> tuple[str, str, str]:
    inner = max(width - 2, 0)
    top = "\u250c" + "\u2500" * inner + "\u2510"  # ┌───┐
    mid = "\u2502" + visual_center(label, inner) + "\u2502"
    bot = "\u2514" + "\u2500" * inner + "\u2518"  # └───┘
    return top, mid, bot


def _header_rows(
    participants: list[Participant],
    box_lefts: list[int],
    box_widths: list[int],
    diagram_width: int,
) -> tuple[str, str, str]:
    top_row = _Row(diagram_width)
    mid_row = _Row(diagram_width)
    bot_row = _Row(diagram_width)
    for p, left, w in zip(participants, box_lefts, box_widths):
        top, mid, bot = _participant_box(w, p.label)
        top_row.set(left, top)
        mid_row.set(left, mid)
        bot_row.set(left, bot)
    return top_row.to_string(), mid_row.to_string(), bot_row.to_string()


def _line_row(
    diagram_width: int,
    centers: list[int],
    lo: int,
    hi: int,
    rightwards: bool,
    dashed: bool,
    head_kind: str,
) -> str:
    row = _lifeline_row(diagram_width, centers)
    line_char = _LINE_CHAR[dashed]
    x0, x1 = centers[lo], centers[hi]
    for x in range(x0 + 1, x1):
        row.set(x, line_char)
    for x in centers[lo + 1 : hi]:
        row.set(x, "┼")
    glyphs = _HEAD_GLYPH[head_kind]
    if rightwards:
        row.set(x0, "├")
        row.set(x1 - 1, glyphs["right"])
    else:
        row.set(x1, "┤")
        row.set(x0 + 1, glyphs["left"])
    return row.to_string()


def _label_row(
    diagram_width: int, centers: list[int], lo: int, hi: int, label_text: str
) -> str | None:
    if not label_text:
        return None
    row = _lifeline_row(diagram_width, centers)
    span_width = centers[hi] - centers[lo] + 1
    row.set(centers[lo], visual_center(label_text, span_width))
    return row.to_string()


def _self_loop_rows(
    diagram_width: int,
    centers: list[int],
    idx_s: int,
    label_text: str,
    dashed: bool,
    head_kind: str,
) -> list[str]:
    x = centers[idx_s]
    line_char = _LINE_CHAR[dashed]
    glyphs = _HEAD_GLYPH[head_kind]

    out_row = _lifeline_row(diagram_width, centers)
    out_row.set(x, line_char + "\u256e")  # ╮ (round down-right corner)

    mid_row = _lifeline_row(diagram_width, centers)
    label_part = ("\u2502 " + label_text) if label_text else "\u2502"
    mid_row.set(x + 1, label_part)

    in_row = _lifeline_row(diagram_width, centers)
    in_row.set(x, glyphs["left"] + "\u256f")  # ╯ (round up-left corner)

    return [out_row.to_string(), mid_row.to_string(), in_row.to_string()]


def _note_box_rows(
    diagram_width: int, centers: list[int], box_left: int, box_width: int, text: str
) -> list[str]:
    top, mid, bot = _participant_box(box_width, text)
    rows = []
    for content in (top, mid, bot):
        row = _lifeline_row(diagram_width, centers)
        row.set(max(box_left, 0), content)
        rows.append(row.to_string())
    return rows


def _band_row(diagram_width: int, kind: str, label: str) -> str:
    if kind == "end":
        fill = max(diagram_width - 2, 0)
        return "\u2514" + "\u2500" * fill + "\u2518"  # └───┘
    left, right = ("\u250c", "\u2510") if kind == "start" else ("\u251c", "\u2524")
    prefix = f"\u2500 {label} " if label else "\u2500 "
    fill = max(diagram_width - 2 - visual_len(prefix), 0)
    return left + prefix + "\u2500" * fill + right


def _plain_label_row(diagram_width: int, text: str) -> str:
    row = _Row(diagram_width)
    content = visual_center(text, diagram_width) if diagram_width > 0 else text
    row.set(0, content)
    return row.to_string()


def _render_arrow(
    ev: Arrow, centers: list[int], id_index: dict[str, int], diagram_width: int
) -> list[str]:
    si, ti = id_index[ev.source], id_index[ev.target]
    label_text = _format_label(ev)

    if si == ti:
        return _self_loop_rows(diagram_width, centers, si, label_text, ev.dashed, ev.head_kind)

    lo, hi = (si, ti) if si < ti else (ti, si)
    rightwards = si < ti
    rows: list[str] = []
    label_row = _label_row(diagram_width, centers, lo, hi, label_text)
    if label_row is not None:
        rows.append(label_row)
    rows.append(_line_row(diagram_width, centers, lo, hi, rightwards, ev.dashed, ev.head_kind))
    return rows


def _render_note(
    ev: NoteEvent, centers: list[int], id_index: dict[str, int], diagram_width: int
) -> list[str]:
    idxs = [id_index[p] for p in ev.participants if p in id_index]
    if not idxs:
        return [_plain_label_row(diagram_width, f"Note: {ev.text}")]
    lo, hi = min(idxs), max(idxs)
    text = ev.text
    box_width = visual_len(text) + 4

    if ev.position == "over":
        span_center = (centers[lo] + centers[hi]) // 2
        box_width = max(box_width, centers[hi] - centers[lo] + 4)
        box_left = span_center - box_width // 2
    elif ev.position == "left":
        box_left = centers[lo] - 2 - box_width
    else:  # "right"
        box_left = centers[lo] + 2

    return _note_box_rows(diagram_width, centers, box_left, box_width, text)


def _render_event(
    ev: Event, centers: list[int], id_index: dict[str, int], diagram_width: int
) -> list[str]:
    if isinstance(ev, Arrow):
        return _render_arrow(ev, centers, id_index, diagram_width)
    if isinstance(ev, NoteEvent):
        return _render_note(ev, centers, id_index, diagram_width)
    if isinstance(ev, BlockBoundary):
        return [_band_row(diagram_width, ev.kind, ev.label)]
    if isinstance(ev, PlainLabel):
        return [_plain_label_row(diagram_width, ev.text)]
    raise SequenceDiagramError(f"unrenderable event: {ev!r}")


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def render_sequence(source: str, width: int) -> list[str]:
    """Render a mermaid ``sequenceDiagram`` source to ASCII lines.

    Args:
        source: The mermaid fence body; its first non-blank line must
            start with ``sequenceDiagram``.
        width: Advisory terminal width. Sequence diagrams have an
            intrinsic width driven by participant labels and message
            text; this function does not wrap or truncate to fit —
            overflow beyond ``width`` is acceptable, matching the
            existing flowchart renderer's contract.

    Returns:
        Rendered lines: monochrome unicode box-drawing, no ANSI, no
        significant trailing whitespace.

    Raises:
        SequenceDiagramError: If ``source`` is not a mermaid sequence
            diagram at all (missing the ``sequenceDiagram`` header).
    """
    del width  # advisory only; diagrams have intrinsic width (see docstring)

    lines = source.splitlines()
    sniff_lines = strip_prelude_lines(lines)
    first = next((line.strip() for line in sniff_lines if line.strip()), "")
    if not first.lower().startswith("sequencediagram"):
        raise SequenceDiagramError(
            "not a mermaid sequence diagram: source must start with 'sequenceDiagram'"
        )

    participants, events = _parse(lines)
    centers, box_widths = _layout_columns(participants, events)
    box_lefts = [c - w // 2 for c, w in zip(centers, box_widths)]
    diagram_width = (box_lefts[-1] + box_widths[-1]) if participants else 0

    out: list[str] = []
    header: tuple[str, str, str] | None = None
    if participants:
        header = _header_rows(participants, box_lefts, box_widths, diagram_width)
        out.extend(header)
        out.append(_lifeline_row(diagram_width, centers).to_string())

    id_index = {p.id: i for i, p in enumerate(participants)}
    for ev in events:
        out.extend(_render_event(ev, centers, id_index, diagram_width))
        if participants:
            out.append(_lifeline_row(diagram_width, centers).to_string())

    if header is not None:
        out.extend(header)

    return out
