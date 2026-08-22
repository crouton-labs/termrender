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

:func:`apply_emphasis` is the companion step for the *other* markup mermaid
labels genuinely support: the inline emphasis tags ``<b>``/``<strong>`` and
``<i>``/``<em>``. Mermaid renders those as real emphasis, so echoing them
literally puts ``<b>dialect</b>`` on screen. They become ANSI SGR runs here,
and nothing else does — an arbitrary HTML tag is not markup this renderer
claims to understand, so it is left exactly as the author typed it.

Emphasis is applied *before* :func:`decode_entities`, never after: an author
who wrote ``&lt;b&gt;`` escaped the tag deliberately and wants the literal
characters, so decoding first would style the very text they escaped away.

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

from termrender.style import BOLD, ITALIC, RESET

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

# The inline emphasis tags mermaid's label dialect supports, opening or
# closing. ``<br/>``'s trailing slash form is deliberately not accepted here
# (a tag name must be followed by optional space then ``>``), so a line break
# can never be mistaken for emphasis.
_EMPHASIS_RE = re.compile(r"<(/?)(b|strong|i|em)\s*>", re.IGNORECASE)

_EMPHASIS_SGR: dict[str, str] = {
    "b": BOLD,
    "strong": BOLD,
    "i": ITALIC,
    "em": ITALIC,
}


def apply_emphasis(text: str) -> str:
    """Replace mermaid's inline emphasis tags in ``text`` with ANSI SGR runs.

    Tags nest (``<b>a<i>b</i>c</b>``) and are matched innermost-first; a
    close tag with no matching open one is dropped rather than echoed, and a
    tag left open at the end of the label is closed for you. An escape is
    emitted only when visible text follows it, so an empty pair like
    ``<b></b>`` collapses to nothing rather than to a zero-width styled run
    that later reads as a non-empty label.

    Callers must keep the result out of every geometry decision they make by
    measuring with :func:`~termrender.style.visual_len` and walking it with
    :func:`~termrender.style.styled_clusters`; ``<b>dialect</b>`` is 14
    source characters and 7 visible ones.
    """
    if "<" not in text:
        return text

    out: list[str] = []
    open_tags: list[str] = []
    emitted = ""  # the SGR currently open in ``out``

    def write(chunk: str) -> None:
        nonlocal emitted
        if not chunk:
            return
        want = "".join(_EMPHASIS_SGR[t] for t in dict.fromkeys(open_tags))
        if want != emitted:
            # SGR is additive, so opening a tag inside another only needs
            # the new code; anything else has to reset and re-open.
            if want.startswith(emitted):
                out.append(want[len(emitted):])
            else:
                if emitted:
                    out.append(RESET)
                out.append(want)
            emitted = want
        out.append(chunk)

    pos = 0
    for m in _EMPHASIS_RE.finditer(text):
        write(text[pos:m.start()])
        pos = m.end()
        tag = m.group(2).lower()
        if m.group(1):
            for i in range(len(open_tags) - 1, -1, -1):
                if open_tags[i] == tag:
                    del open_tags[i]
                    break
        else:
            open_tags.append(tag)
    write(text[pos:])

    if emitted:
        out.append(RESET)
    return "".join(out)


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
