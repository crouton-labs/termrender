"""Mermaid diagram renderer for termrender."""

from __future__ import annotations

import re
import subprocess

from termrender._mermaid_bin import mermaid_ascii_bin
from termrender.blocks import Block
from termrender.renderers import (
    mermaid_gantt,
    mermaid_journey,
    mermaid_mindmap,
    mermaid_pie,
    mermaid_sequence,
    mermaid_timeline,
)
from termrender.renderers.mermaid_prelude import strip_prelude_lines
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

# Flowchart node-shape normalizers. mermaid-ascii only parses the ``[text]``
# rectangle form; every other mermaid node shape leaks its raw delimiters (or
# the node id) into the rendered box — e.g. ``B{Auth?}`` renders the literal
# ``B{Auth?}`` and ``E[(Database)]`` renders ``(Database)``. Since mermaid-ascii
# draws every node as a rectangle regardless, we rewrite each alternate shape to
# ``id[label]``, preserving the label text and dropping only the shape (which
# the ASCII backend cannot draw anyway). Order matters: multi-char delimiters
# (``{{``, ``[[``, ``[(``, ``((``, ``([``) must run before their single-char
# counterparts so the greedy single forms don't bite off half a delimiter.
_FLOWCHART_SHAPE_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(\w+)\{\{(.+?)\}\}"), r"\1[\2]"),        # hexagon {{ }}
    (re.compile(r"(\w+)\[\[(.+?)\]\]"), r"\1[\2]"),        # subroutine [[ ]]
    (re.compile(r"(\w+)\[\((.+?)\)\]"), r"\1[\2]"),        # cylinder [( )]
    (re.compile(r"(\w+)\(\(\((.+?)\)\)\)"), r"\1[\2]"),    # double circle ((( )))
    (re.compile(r"(\w+)\(\((.+?)\)\)"), r"\1[\2]"),        # circle (( ))
    (re.compile(r"(\w+)\(\[(.+?)\]\)"), r"\1[\2]"),        # stadium ([ ])
    (re.compile(r"(\w+)\[[\\/](.+?)[\\/]\]"), r"\1[\2]"),  # parallelogram/trapezoid [/ /] [\ \] [/ \] [\ /]
    (re.compile(r"(\w+)\{(.+?)\}"), r"\1[\2]"),            # rhombus { }
    (re.compile(r"(\w+)>(.+?)\]"), r"\1[\2]"),             # asymmetric/flag > ]
    (re.compile(r"(\w+)\((.+?)\)"), r"\1[\2]"),            # round ( )
]
_UNSUPPORTED_BLOCK_RE = re.compile(
    r"^\s*(?:loop|alt|else|opt|par|and|critical|option|break|rect|"
    r"activate|deactivate|autonumber|end)\b.*$",
    re.IGNORECASE,
)


def normalize_flowchart_shapes(source: str) -> str:
    """Rewrite alternate flowchart node shapes to the ``[text]`` form.

    mermaid-ascii only parses rectangle nodes (``id[text]``); rhombus ``{}``,
    cylinder ``[()]``, circle ``(())``, stadium ``([])``, hexagon ``{{}}``,
    subroutine ``[[]]``, and parallelogram/trapezoid ``[/ /]`` nodes otherwise
    render with their raw delimiters or bare node id. Each is rewritten to
    ``id[text]`` so the label survives; the backend draws a rectangle either way.
    """
    out: list[str] = []
    for line in source.splitlines():
        for pattern, repl in _FLOWCHART_SHAPE_SUBS:
            line = pattern.sub(repl, line)
        out.append(line)
    return "\n".join(out)


def preprocess_mermaid_for_ascii(source: str) -> str:
    """Rewrite a mermaid diagram into the subset mermaid-ascii supports.

    For sequence diagrams: convert ``Note`` lines into self-loops, map the
    arrow variants (``->``, ``-x``, ``--x``, ``-)``, ``--)``, ``-->``) to the
    supported ``->>``/``-->>`` pair, drop block keywords (``loop``, ``alt``,
    ``activate``…), and flatten ``<br/>`` tags. For flowcharts (``graph`` /
    ``flowchart``): normalize alternate node shapes to ``[text]`` rectangles.
    Other diagram types are returned unchanged.
    """
    lines = source.splitlines()
    first = next((l.strip() for l in lines if l.strip()), "")
    first_lower = first.lower()
    if not first_lower.startswith("sequencediagram"):
        if first_lower.startswith(("graph", "flowchart")):
            return normalize_flowchart_shapes(source)
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


def _first_line_type(source: str) -> str:
    """Return the lowercased first real line's leading keyword.

    This is the dispatch key: mermaid identifies a diagram's type from its
    first line (``graph``/``flowchart``, ``pie``, ``gantt``, ``sequenceDiagram``,
    ``classDiagram``, …), after skipping any prelude (blank lines, ``%%``
    comments/directives, ``---`` YAML frontmatter — see ``mermaid_prelude.py``).
    Returns ``""`` for a source with no real content past its prelude.
    """
    lines = strip_prelude_lines(source.splitlines())
    first = next((l.strip() for l in lines if l.strip()), "")
    return first.lower()


def _render_via_binary(source: str) -> str:
    """Render via the vendored mermaid-ascii binary, falling back to source.

    This is the pre-existing path for every type without a native Python
    renderer (flowchart/graph, sequence, class, state, ER, …): normalize
    what mermaid-ascii can parse, shell out, and undo its Latin-1
    double-encoding. Any failure (missing binary, timeout, non-zero exit,
    a parser panic on unsupported input) degrades to the raw source text —
    mermaid-ascii has no notion of "partial" output, so there is no middle
    ground between a full render and falling back.
    """
    try:
        result = subprocess.run(
            [mermaid_ascii_bin(), "-f", "-", "-y", "1"],
            input=preprocess_mermaid_for_ascii(source),
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return fix_mermaid_encoding(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return source


def render_mermaid_lines(source: str, width: int) -> list[str]:
    """Dispatch a mermaid source to its type's renderer and return raw lines.

    ``pie``, ``gantt``, ``sequenceDiagram``, ``mindmap``, ``journey``, and
    ``timeline`` get dedicated native Python renderers. Every other type
    (flowchart/graph, class, state, ER, …) keeps today's exact path: the
    vendored Go mermaid-ascii binary, which echoes unparseable/unsupported
    source back verbatim. Lines are returned unpadded; callers apply width
    padding uniformly.
    """
    diagram_type = _first_line_type(source)
    if diagram_type.startswith("pie"):
        return mermaid_pie.render(source, width)
    if diagram_type.startswith("gantt"):
        return mermaid_gantt.render(source, width)
    if diagram_type.startswith("sequencediagram"):
        return mermaid_sequence.render_sequence(source, width)
    if diagram_type.startswith("mindmap"):
        return mermaid_mindmap.render(source, width)
    if diagram_type.startswith("journey"):
        return mermaid_journey.render(source, width)
    if diagram_type.startswith("timeline"):
        return mermaid_timeline.render(source, width)
    return _render_via_binary(source).split("\n")


def render(block: Block, color: bool) -> list[str]:
    """Render a mermaid diagram from pre-rendered or on-the-fly ASCII output."""
    w = block.width
    rendered = block.attrs.get("_rendered")

    if rendered is None:
        source = block.attrs.get("source", "")
        raw_lines = render_mermaid_lines(source, w or 60)
    else:
        raw_lines = rendered.split("\n")

    return [visual_ljust(raw_line, w) for raw_line in raw_lines]
