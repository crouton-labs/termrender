"""ANSI style primitives for terminal rendering."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from termrender.blocks import InlineSpan

# Compiled regex matching ANSI escape sequences
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

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


def resolve_color(name: str | None) -> str:
    if name is None:
        return ''
    return COLOR_MAP.get(name, '')


def style(
    text: str,
    color: str | None = None,
    bold: bool = False,
    italic: bool = False,
    dim: bool = False,
    enabled: bool = True,
) -> str:
    if not enabled:
        return text
    prefix = resolve_color(color)
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
    """Return display width of a single character (2 for wide/fullwidth, 1 otherwise)."""
    return 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1


def visual_len(s: str) -> int:
    stripped = ANSI_RE.sub('', s)
    return sum(_char_width(c) for c in stripped)


def visual_ljust(s: str, width: int) -> str:
    vl = visual_len(s)
    if vl >= width:
        return s
    return s + ' ' * (width - vl)


def visual_center(s: str, width: int, fillchar: str = ' ') -> str:
    vl = visual_len(s)
    if vl >= width:
        return s
    total_pad = width - vl
    left_pad = total_pad // 2
    right_pad = total_pad - left_pad
    return fillchar * left_pad + s + fillchar * right_pad


def wrap_text(text: str, width: int) -> list[str]:
    if not text or text.isspace():
        return ['']
    if width <= 0:
        return [text] if text else ['']
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
            text = style(text, dim=True, enabled=color)
        elif span.bold or span.italic:
            text = style(text, bold=span.bold, italic=span.italic, enabled=color)
        parts.append(text)
    return ''.join(parts)
