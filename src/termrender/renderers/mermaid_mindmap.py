"""Native renderer for mermaid ``mindmap`` diagrams.

Mermaid mindmap grammar (subset)::

    mindmap
      root((mindmap))
        Origins
          Long history
          ::icon(fa fa-book)
        Research
          On effectiveness<br/>and features
        Tools
          Pen and paper

Mindmap source is *already* an indentation-based tree — the same shape
``tree.py`` renders — so this module does no layout of its own: it strips
mermaid-only decoration (the ``mindmap`` header, node-shape delimiters,
``::icon(...)`` and ``:::className`` lines) down to plain indented labels
and hands the result to ``tree.py`` via a synthetic ``Block``, reusing its
guide-line rendering rather than duplicating it (mirrors how
``mermaid_pie.py`` reuses ``charts.py``'s ``render_bar``).
"""

from __future__ import annotations

import re

from termrender.blocks import Block, BlockType
from termrender.renderers.mermaid_text import BREAK_RE, decode_entities
from termrender.renderers.tree import render as render_tree

_HEADER_RE = re.compile(r"^\s*mindmap\b", re.IGNORECASE)
_ICON_RE = re.compile(r"^::icon\(", re.IGNORECASE)
_CLASS_RE = re.compile(r"^:::")
_BR_RE = BREAK_RE

# Node-shape wrappers, most-specific delimiter pair first so a greedy
# shorter pattern doesn't bite off half of a longer one (mirrors the
# ordering discipline in mermaid.py's ``_FLOWCHART_SHAPE_SUBS``). The
# leading ``\w*`` is an optional node id, discarded — only ever the label
# text is displayed.
_NODE_SHAPE_RES: list[re.Pattern[str]] = [
    re.compile(r"^(\w*)\)\)(.+)\(\($"),  # bang: id))text((
    re.compile(r"^(\w*)\(\((.+)\)\)$"),  # circle: id((text))
    re.compile(r"^(\w*)\{\{(.+)\}\}$"),  # hexagon: id{{text}}
    re.compile(r"^(\w*)\[(.+)\]$"),  # square: id[text]
    re.compile(r"^(\w*)\((.+)\)$"),  # rounded: id(text)
    re.compile(r"^(\w*)\)(.+)\($"),  # cloud: id)text(
]


def _node_label(text: str) -> str:
    """Strip a mindmap node's shape delimiters, keeping only its label.

    A bare word with no shape (the common case) matches nothing and is
    returned unchanged.
    """
    for pattern in _NODE_SHAPE_RES:
        m = pattern.match(text)
        if m:
            return decode_entities(_BR_RE.sub(" / ", m.group(2).strip()))
    return decode_entities(_BR_RE.sub(" / ", text))


def parse_mindmap(source: str) -> str:
    """Parse mermaid mindmap syntax into ``tree.py``'s plain indented format.

    Drops the ``mindmap`` header line, any ``%%`` comment/directive line
    (wherever it appears in the body, not just in the leading prelude), and
    any ``::icon(...)``/``:::class`` decoration lines (termrender's tree has
    no icon/class concept); every other line's original indentation is
    preserved (depth comes from indentation, exactly as ``tree.py`` already
    expects) with its node-shape delimiters stripped down to label text.
    Returns the transformed multi-line indented string, empty if nothing
    survived.
    """
    out_lines: list[str] = []
    for raw_line in source.splitlines():
        if not raw_line.strip():
            continue
        if _HEADER_RE.match(raw_line):
            continue
        stripped = raw_line.strip()
        if stripped.startswith("%%"):
            continue
        if _ICON_RE.match(stripped) or _CLASS_RE.match(stripped):
            continue
        indent = raw_line[: len(raw_line) - len(raw_line.lstrip(" "))]
        out_lines.append(f"{indent}{_node_label(stripped)}")
    return "\n".join(out_lines)


def render(source: str, width: int) -> list[str]:
    """Render mermaid mindmap syntax as a guide-line tree.

    A diagram with no survivable content (only a header, or blank)
    degrades to the raw source text.
    """
    tree_source = parse_mindmap(source)
    if not tree_source.strip():
        return source.splitlines() or [""]

    block = Block(type=BlockType.TREE, attrs={"source": tree_source}, width=width)
    return render_tree(block, color=False)
