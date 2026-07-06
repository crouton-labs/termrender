"""Shared handling for mermaid's optional prelude before the type keyword.

Mermaid tolerates three forms of preamble before a diagram's type line
(``pie``, ``gantt``, ``sequenceDiagram``, …): ``%%`` line comments,
``%%{init: ...}%%`` directives (mermaid's config-block syntax), and
``---``-delimited YAML frontmatter (used for e.g. a top-level ``title:``
key). :func:`strip_prelude_lines` skips all three so callers that sniff or
validate "what type is this diagram" see the real type line, not a
directive or frontmatter key.

Used by ``mermaid.py`` (dispatch sniffing) and ``mermaid_sequence.py`` (its
own "is this actually a sequence diagram" header check) — kept here rather
than in either so neither has to import the other's private helpers.
"""

from __future__ import annotations


def strip_prelude_lines(lines: list[str]) -> list[str]:
    """Return ``lines`` with leading blank/comment/directive/frontmatter lines dropped.

    Skipping is permissive: an unterminated frontmatter block (opening
    ``---`` with no closing ``---``) or an unterminated ``%%{`` directive
    (never reaches a line ending in ``%%``) is left untouched rather than
    consumed — better to sniff a directive/frontmatter line as the "type"
    than to silently discard real content.
    """
    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        if stripped == "---":
            j = i + 1
            while j < n and lines[j].strip() != "---":
                j += 1
            if j >= n:
                break  # unterminated frontmatter
            i = j + 1
            continue
        if stripped.startswith("%%"):
            if stripped.startswith("%%{") and not stripped.endswith("%%"):
                j = i + 1
                while j < n and not lines[j].strip().endswith("%%"):
                    j += 1
                if j >= n:
                    break  # unterminated directive
                i = j + 1
                continue
            i += 1
            continue
        break
    return lines[i:]
