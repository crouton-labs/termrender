"""ANSI style primitives for terminal rendering."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from typing import TYPE_CHECKING

import regex

if TYPE_CHECKING:
    from termrender.blocks import InlineSpan

# Compiled regex matching ANSI escape sequences
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

# Ambiguous-width character handling.
# 1 = narrow (default for most Western terminals)
# 2 = wide (CJK terminals, some tmux configurations)
_ambiguous_width: int = 1


def set_ambiguous_width(w: int) -> None:
    global _ambiguous_width
    _ambiguous_width = w


def get_ambiguous_width() -> int:
    return _ambiguous_width

# Characters with Emoji_Presentation=Yes that terminals render as 2 cells wide
# even without a VS16 (U+FE0F) suffix.  Characters that are Emoji=Yes but
# Emoji_Presentation=No (e.g. ℹ ⚠ ✔ ✖) are 1-wide in text presentation;
# the VS16 handler (visual_len, line ~209) already widens them to 2 when
# an explicit emoji-presentation selector follows.
_EMOJI_WIDE_RANGES: tuple[tuple[int, int], ...] = (
    # BMP — only Emoji_Presentation=Yes codepoints (Unicode 15.0)
    (0x231A, 0x231B),  # ⌚⌛ watch/hourglass
    (0x23E9, 0x23EC),  # ⏩⏪⏫⏬
    (0x23F0, 0x23F0),  # ⏰ alarm clock
    (0x25FD, 0x25FE),  # ◽◾ squares
    (0x2614, 0x2615),  # ☔☕
    (0x2648, 0x2653),  # ♈–♓ zodiac
    (0x267F, 0x267F),  # ♿ wheelchair
    (0x2693, 0x2693),  # ⚓ anchor
    (0x26A1, 0x26A1),  # ⚡ lightning
    (0x26AA, 0x26AB),  # ⚪⚫ circles
    (0x26BD, 0x26BE),  # ⚽⚾ balls
    (0x26C4, 0x26C5),  # ⛄⛅ snowman/sun
    (0x26CE, 0x26CE),  # ⛎ Ophiuchus
    (0x26D4, 0x26D4),  # ⛔ no entry
    (0x26EA, 0x26EA),  # ⛪ church
    (0x26F2, 0x26F3),  # ⛲⛳ fountain/golf
    (0x26F5, 0x26F5),  # ⛵ sailboat
    (0x26FA, 0x26FA),  # ⛺ tent
    (0x26FD, 0x26FD),  # ⛽ fuel pump
    (0x2705, 0x2705),  # ✅ check mark
    (0x270A, 0x270B),  # ✊✋ fists
    (0x2728, 0x2728),  # ✨ sparkles
    (0x2753, 0x2755),  # ❓❔❕ question/exclamation
    (0x2757, 0x2757),  # ❗ exclamation
    (0x2795, 0x2797),  # ➕➖➗ math
    (0x27B0, 0x27B0),  # ➰ curly loop
    (0x27BF, 0x27BF),  # ➿ double curly loop
    (0x2B1B, 0x2B1C),  # ⬛⬜ large squares
    (0x2B50, 0x2B50),  # ⭐ star
    (0x2B55, 0x2B55),  # ⭕ circle
    # Supplementary planes — nearly all Emoji_Presentation=Yes
    (0x1F004, 0x1F004),
    (0x1F0CF, 0x1F0CF),
    (0x1F18E, 0x1F18E),
    (0x1F191, 0x1F19A),
    (0x1F1E0, 0x1F1FF),
    (0x1F200, 0x1F202),
    (0x1F21A, 0x1F21A),
    (0x1F22F, 0x1F22F),
    (0x1F232, 0x1F23A),
    (0x1F250, 0x1F251),
    (0x1F300, 0x1F9FF),
    (0x1FA00, 0x1FA6F),
    (0x1FA70, 0x1FAFF),
)

# Style constants
RESET = '\x1b[0m'
BOLD = '\x1b[1m'
ITALIC = '\x1b[3m'
DIM = '\x1b[2m'

# The attribute-scoped "off" codes. Ending a run with one of these turns off
# exactly that attribute and leaves every other attribute in force — unlike
# RESET (SGR 0), which also clears whatever styling the *host* embedding this
# output had set. See :func:`sgr_transition`.
BOLD_OFF = '\x1b[22m'      # normal intensity: cancels both bold and dim
ITALIC_OFF = '\x1b[23m'

# Which parameter turns each attribute off. Only the attributes termrender
# opens mid-line are listed; a colour has no code that restores the host's
# colour (SGR 39/49 restore the *terminal's* default, which is a different
# thing), so a run holding one is still closed with a full reset.
_SGR_OFF: dict[str, str] = {
    '1': '22',
    '2': '22',
    '3': '23',
}
_SGR_OFF_CODES = frozenset(_SGR_OFF.values())

# Color name -> ANSI code mapping
COLOR_MAP: dict[str, str] = {
    'red': '\x1b[31m',
    'green': '\x1b[32m',
    'yellow': '\x1b[33m',
    'blue': '\x1b[34m',
    'magenta': '\x1b[35m',
    'cyan': '\x1b[36m',
    'white': '\x1b[37m',
    'gray': '\x1b[90m',
}

BG_COLOR_MAP: dict[str, str] = {
    'red': '\x1b[41m',
    'green': '\x1b[42m',
    'yellow': '\x1b[43m',
    'blue': '\x1b[44m',
    'magenta': '\x1b[45m',
    'cyan': '\x1b[46m',
    'white': '\x1b[47m',
    'gray': '\x1b[100m',
    # Dim background variants — use bright-black (dark gray) range
    'dim_red': '\x1b[48;5;52m',
    'dim_green': '\x1b[48;5;22m',
    'dim_yellow': '\x1b[48;5;58m',
    'dim_blue': '\x1b[48;5;17m',
    'dim_magenta': '\x1b[48;5;53m',
    'dim_cyan': '\x1b[48;5;23m',
}


def resolve_color(name: str | None) -> str:
    if name is None:
        return ''
    return COLOR_MAP.get(name, '')


def resolve_bg_color(name: str | None) -> str:
    if name is None:
        return ''
    return BG_COLOR_MAP.get(name, '')


def style(
    text: str,
    color: str | None = None,
    bg: str | None = None,
    bold: bool = False,
    italic: bool = False,
    dim: bool = False,
    enabled: bool = True,
) -> str:
    if not enabled:
        return text
    prefix = resolve_color(color)
    prefix += resolve_bg_color(bg)
    if bold:
        prefix += BOLD
    if italic:
        prefix += ITALIC
    if dim:
        prefix += DIM
    if not prefix:
        return text
    # A pure-attribute run closes with its own disable codes so it can sit
    # inside a host's styling; one carrying a colour still closes with a
    # full reset, because no code restores a colour this process never set.
    return prefix + text + sgr_transition(prefix, '')


def _char_width(c: str) -> int:
    """Return display width of a single character."""
    cat = unicodedata.category(c)
    # Combining marks and format characters are zero-width
    if cat.startswith('M') or cat == 'Cf':
        return 0
    eaw = unicodedata.east_asian_width(c)
    # East Asian wide/fullwidth
    if eaw in ('W', 'F'):
        return 2
    # Ambiguous-width characters (box-drawing, bullets, etc.)
    if eaw == 'A':
        return _ambiguous_width
    # Emoji and symbols that terminals render as 2 cells despite east_asian_width=N
    cp = ord(c)
    for lo, hi in _EMOJI_WIDE_RANGES:
        if cp < lo:
            break  # ranges are sorted, no point continuing
        if lo <= cp <= hi:
            return 2
    return 1


def grapheme_clusters(text: str) -> Iterator[str]:
    """Yield Unicode extended grapheme clusters from ``text``."""
    yield from regex.findall(r"\X", text)


def visual_len(s: str) -> int:
    """Return visual display width of string, ignoring ANSI codes."""
    width = 0
    for cluster in grapheme_clusters(ANSI_RE.sub('', s)):
        cluster_width = max((_char_width(char) for char in cluster), default=0)
        # VS16 turns the cluster into its emoji-presentation form.
        if "\ufe0f" in cluster:
            cluster_width = max(cluster_width, 2)
        width += cluster_width
    return width


def _sgr_params(seq: str) -> list[str]:
    """Every SGR parameter in ``seq``, in order. ``\\x1b[1;31m`` is two
    parameters and ``\\x1b[m`` is the bare reset, spelled ``'0'`` here."""
    params: list[str] = []
    for m in ANSI_RE.finditer(seq):
        body = m.group(0)[2:-1]
        params.extend(body.split(';') if body else ['0'])
    return params


def _fold_params(params: list[str]) -> list[str]:
    """The attributes left in force after ``params`` are applied in order: a
    reset clears everything, an "off" code clears just the attributes it
    names, anything else accumulates."""
    active: list[str] = []
    for p in params:
        if p in ('', '0'):
            active = []
        elif p in _SGR_OFF_CODES:
            active = [q for q in active if _SGR_OFF.get(q) != p]
        elif p not in active:
            active.append(p)
    return active


def _render_params(params: list[str]) -> str:
    return ''.join(f'\x1b[{p}m' for p in params)


def sgr_transition(current: str, wanted: str) -> str:
    """The escapes that move a terminal from ``current`` styling to ``wanted``.

    Attributes no longer wanted are turned off with their own disable code
    (SGR 22 for bold, 23 for italic), never with SGR 0, so styling applied by
    whatever host surrounds this output — a foreground colour on the region
    the diagram is drawn into — survives the run's end. A run that has no
    such code for something it opened (a colour) still closes with a full
    reset, and ``wanted`` is re-opened after it.

    ``sgr_transition(active, "")`` is therefore "close this run", and
    ``sgr_transition("", active)`` is "open it".
    """
    cur = _fold_params(_sgr_params(current))
    want = _fold_params(_sgr_params(wanted))
    if cur == want:
        return ''
    stale = [p for p in cur if p not in want]
    if not stale:
        return _render_params([p for p in want if p not in cur])
    if any(p not in _SGR_OFF for p in stale):
        return RESET + _render_params(want)
    offs = list(dict.fromkeys(_SGR_OFF[p] for p in stale))
    # One disable code can cancel an attribute still wanted (22 turns off
    # bold *and* dim), so re-open anything it takes down with it.
    reopen = [
        p for p in want
        if p not in cur or _SGR_OFF.get(p) in offs
    ]
    return f"\x1b[{';'.join(offs)}m" + _render_params(reopen)


def styled_clusters(s: str) -> Iterator[tuple[str, str]]:
    """Yield ``(sgr, cluster)`` for every *visible* grapheme cluster in ``s``.

    ``sgr`` is the ANSI SGR sequence in force at that cluster (``''`` when
    unstyled), folded from every escape preceding it. Escapes are never
    yielded as clusters, so a caller that lays text out cell by cell can
    neither split one across cells nor count one toward a visual width —
    the guarantee the mermaid flow canvas needs to place a styled label
    into its character grid.
    """
    active: list[str] = []
    rendered = ''
    pos = 0
    for m in ANSI_RE.finditer(s):
        for cluster in grapheme_clusters(s[pos:m.start()]):
            yield rendered, cluster
        active = _fold_params(active + _sgr_params(m.group(0)))
        rendered = _render_params(active)
        pos = m.end()
    for cluster in grapheme_clusters(s[pos:]):
        yield rendered, cluster


def active_sgr(s: str) -> str:
    """The ANSI SGR sequence still in force after ``s`` — what a following
    line must re-open to continue ``s``'s styling."""
    return _render_params(_fold_params(_sgr_params(s)))


def visual_ljust(s: str, width: int) -> str:
    vl = visual_len(s)
    if vl >= width:
        return s
    return s + ' ' * (width - vl)


def visual_center(s: str, width: int, fillchar: str = ' ') -> str:
    vl = visual_len(s)
    if vl >= width:
        return s
    fill_w = visual_len(fillchar) or 1
    total_pad = width - vl
    left_count = (total_pad // 2) // fill_w
    right_count = (total_pad - left_count * fill_w) // fill_w
    return fillchar * left_count + s + fillchar * right_count


def wrap_text(text: str, width: int) -> list[str]:
    if not text:
        return ['']
    if "\n" in text:
        result: list[str] = []
        for seg in text.split("\n"):
            result.extend(wrap_text(seg, width))
        return result
    if text.isspace():
        return ['']
    if width <= 0:
        return [text]
    words = text.split(' ')
    lines: list[str] = []
    current = ''
    for word in words:
        if not word:
            # consecutive spaces produce empty tokens
            if current:
                current += ' '
            continue
        # Hard-break words longer than width
        while len(word) > width:
            chunk_size = width if not current else width - len(current) - 1
            if chunk_size <= 0:
                # Current line is full, flush it and retry
                lines.append(current)
                current = ''
                continue
            chunk = word[:chunk_size]
            if current and chunk:
                lines.append(current + ' ' + chunk)
                word = word[len(chunk):]
                current = ''
            elif current:
                lines.append(current)
                current = ''
            else:
                lines.append(word[:width])
                word = word[width:]
            if not word:
                break
        if not word:
            continue
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += ' ' + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines if lines else ['']


def render_spans(spans: list[InlineSpan], color: bool) -> str:
    parts: list[str] = []
    for span in spans:
        text = span.text
        if span.code:
            text = style(text, color="cyan", enabled=color)
        elif span.fg or span.bg:
            text = style(
                text,
                color=span.fg, bg=span.bg,
                bold=span.bold, italic=span.italic,
                enabled=color,
            )
        elif span.bold or span.italic:
            text = style(text, bold=span.bold, italic=span.italic, enabled=color)
        parts.append(text)
    return ''.join(parts)
