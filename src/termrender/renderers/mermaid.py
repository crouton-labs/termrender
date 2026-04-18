"""Mermaid diagram renderer for termrender."""

from __future__ import annotations

import re
import subprocess

from termrender.blocks import Block
from termrender.style import visual_ljust


def fix_mermaid_encoding(text: str) -> str:
    """Undo mermaid-ascii's double-encoding of UTF-8 characters.

    mermaid-ascii misinterprets UTF-8 input bytes as Latin-1 and re-encodes
    to UTF-8, corrupting multi-byte characters (e.g. → becomes â\\x86\\x92).
    Reversing the process: encode back to Latin-1 to recover the original
    UTF-8 bytes, then decode as UTF-8.
    """
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


_NOTE_RE = re.compile(
    r"^(\s*)[Nn]ote\s+(?:over|left\s+of|right\s+of)\s+([^:]+?)\s*:\s*(.*)$"
)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_UNSUPPORTED_BLOCK_RE = re.compile(
    r"^\s*(?:loop|alt|else|opt|par|and|critical|option|break|rect|"
    r"activate|deactivate|autonumber|end)\b.*$",
    re.IGNORECASE,
)


def preprocess_mermaid_for_ascii(source: str) -> str:
    """Rewrite mermaid sequence diagrams into the subset mermaid-ascii supports.

    mermaid-ascii only understands ``->>`` and ``-->>`` arrows plus ``participant``
    declarations. This helper converts ``Note`` lines into self-loops, maps the
    other arrow variants (``->``, ``-x``, ``--x``, ``-)``, ``--)``, ``-->``) to
    the supported pair, drops block keywords (``loop``, ``alt``, ``activate``…),
    and flattens ``<br/>`` tags. Non-sequence diagrams are returned unchanged.
    """
    lines = source.splitlines()
    first = next((l.strip() for l in lines if l.strip()), "")
    if not first.lower().startswith("sequencediagram"):
        return source

    out: list[str] = []
    for line in lines:
        m = _NOTE_RE.match(line)
        if m:
            indent, parts, msg = m.group(1), m.group(2), m.group(3)
            first_p = parts.split(",")[0].strip()
            msg = _BR_RE.sub(" / ", msg)
            out.append(f"{indent}{first_p}->>{first_p}: 📝 {msg}")
            continue

        if _UNSUPPORTED_BLOCK_RE.match(line):
            continue

        line = _BR_RE.sub(" / ", line)
        line = re.sub(r"--x(?=\s|\w|\()", "-->>", line)
        line = re.sub(r"-x(?=\s|\w|\()", "->>", line)
        line = re.sub(r"--\)(?=\s|\w|\()", "-->>", line)
        line = re.sub(r"-\)(?=\s|\w|\()", "->>", line)
        line = re.sub(r"-->(?!>)", "-->>", line)
        line = re.sub(r"(?<!-)->(?!>)", "->>", line)
        out.append(line)
    return "\n".join(out)


def render(block: Block, color: bool) -> list[str]:
    """Render a mermaid diagram from pre-rendered or on-the-fly ASCII output."""
    w = block.width
    rendered = block.attrs.get("_rendered")

    if rendered is None:
        source = block.attrs.get("source", "")
        try:
            result = subprocess.run(
                ["mermaid-ascii", "-f", "-", "-w", str(block.width or 80), "-y", "1"],
                input=preprocess_mermaid_for_ascii(source),
                capture_output=True,
                text=True,
                timeout=30,
            )
            rendered = fix_mermaid_encoding(result.stdout)
        except Exception:
            rendered = source

    lines: list[str] = []
    for raw_line in rendered.split("\n"):
        lines.append(visual_ljust(raw_line, w))

    return lines
