"""Shared label-text decoding for the mermaid renderers.

Mermaid draws labels as HTML, so an author writes characters that would
otherwise collide with mermaid's own grammar as *entity codes*: either the
HTML form (``A["Record&lt;K, V&gt;"]``) or mermaid's documented hash form
(``A["A quote: #quot;"]``, ``B["#35; is a hash"]``). Both render as the bare
character in mermaid proper, so a terminal renderer that echoes them
literally shows ``Record&lt;K, V&gt;`` — the exact thing the author escaped
*away*.

:func:`decode_entities` is that decode step, applied by each renderer where
it normalizes a label (alongside the ``<br/>`` handling), i.e. *after*
parsing has already used the raw text for structure. Decoding at the label
level rather than over the whole source is deliberate: ``--&gt;`` inside a
quoted label must not become a real ``-->`` connector, and ``&amp;`` must
not become flowchart's ``&`` node-group separator.

This module also owns :data:`BREAK_RE`, the shared "author asked for a line
break" pattern. Authors write that break two ways — the documented ``<br/>``
and a literal backslash-``n`` (``A["live list\nroute match"]``), which mermaid
renders as a break too — so both must be recognized wherever a renderer
normalizes a label, or the escape shows up verbatim in the box.

Decoding is strict, unlike :func:`html.unescape`: only a complete
``&name;`` / ``&#nnn;`` / ``&#xhh;`` (or the hash-form equivalent) is
decoded. The stdlib's leniency about a missing semicolon would mangle
ordinary label prose — ``html.unescape("&params")`` is ``"¶ms"``.
"""

from __future__ import annotations

import html
import re

# Numeric codes (``&#35;`` / ``#35;`` / ``&#x2b;`` / ``#x2b;``) in group 1,
# named ones (``&lt;`` / ``#quot;``) in group 2. Both prefixes are accepted for
# both forms because mermaid's hash form is exactly its HTML form with the
# ``&`` swapped for ``#``. A bare name with no prefix (ordinary prose ending
# in a semicolon, e.g. ``see lt;``) matches nothing and is left alone.
_CODE_RE = re.compile(
    r"(?:&#|#)(\d{1,7}|[xX][0-9a-fA-F]{1,6});|(?:&|#)([A-Za-z][A-Za-z0-9]{1,31});"
)

# An author-requested line break: ``<br>``/``<br/>``/``<BR />`` or a literal
# backslash-n. Each renderer substitutes its own replacement — a real newline
# where the surface can stack lines, a separator where it cannot.
BREAK_RE = re.compile(r"<br\s*/?>|\\n", re.IGNORECASE)


def _resolve(code: str) -> str | None:
    """Return the character ``code`` (an ``&…;`` string) names, or ``None`` if
    it names nothing."""
    decoded = html.unescape(code)
    return decoded if decoded != code else None


def decode_entities(text: str) -> str:
    """Replace complete HTML/mermaid entity codes in ``text`` with their
    characters, leaving anything that resolves to no character untouched."""
    if "&" not in text and "#" not in text:
        return text

    def sub(m: re.Match[str]) -> str:
        num, name = m.group(1), m.group(2)
        code = f"&#{num};" if num is not None else f"&{name};"
        return _resolve(code) or m.group(0)

    return _CODE_RE.sub(sub, text)
