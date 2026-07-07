"""Shared raw-echo degradation contract for the native mermaid renderers.

Every native mermaid renderer in this package (``mermaid.py``'s exotic-type
fallback, and the flowchart-model-backed ``mermaid_flow.py``,
``mermaid_class.py``, ``mermaid_state.py``, ``mermaid_er.py``) must degrade
identically on any input it cannot fully render under its supported
grammar: echo the source lines verbatim (``.rstrip()``-ed), with every
box-drawing/geometric glyph replaced by ``?``. The downstream crouter
attach viewer keys on the *presence* of one of these glyphs to decide
whether a native render succeeded and the original mermaid fence can be
dropped — so the echo path must never contain one, even when malformed or
degenerate source happens to contain a literal glyph of its own (e.g. a
hand-typed ``"\u250c"`` in otherwise-non-mermaid text).

:func:`raw_echo` is the one shared implementation of that contract; every
renderer module imports it rather than keeping its own copy of the glyph
regex and echo function.
"""

from __future__ import annotations

import re

__all__ = ["GLYPH_RANGE_RE", "raw_echo"]

GLYPH_RANGE_RE = re.compile("[\u2500-\u259f\u25a0-\u25ff]")


def raw_echo(source: str) -> list[str]:
    """Echo ``source``'s lines verbatim, minus trailing whitespace, with
    every box-drawing/geometric glyph (:data:`GLYPH_RANGE_RE`) replaced by
    ``?`` so the echo can never be mistaken for a successful native
    render."""
    return [GLYPH_RANGE_RE.sub("?", line.rstrip()) for line in source.splitlines()]
