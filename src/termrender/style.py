"""ANSI style primitives for terminal rendering."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

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
    return prefix + text + RESET


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


def visual_len(s: str) -> int:
    """Return visual display width of string, ignoring ANSI codes."""
    stripped = ANSI_RE.sub('', s)
    width = 0
    i = 0
    chars = list(stripped)
    while i < len(chars):
        c = chars[i]
        cp = ord(c)
        # Check if next char is VS16 (emoji presentation selector)
        if i + 1 < len(chars) and ord(chars[i + 1]) == 0xFE0F:
            cw = _char_width(c)
            # VS16 makes the preceding char display as 2 cells
            width += max(cw, 2)
            i += 2  # skip the VS16
            continue
        # VS15 (text presentation) - just skip it
        if cp == 0xFE0E:
            i += 1
            continue
        width += _char_width(c)
        i += 1
    return width


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
