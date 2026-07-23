"""Two-pass markdown+directive parser for termrender.

Pass 1 (directive pass): Scans raw source for :::name{attrs} directives using
a stack-based depth tracker. Segments between directives are plain markdown.

Pass 2 (mistune pass): Parses plain markdown segments via mistune v3 AST mode,
then converts the dict-based AST into our Block tree.
"""

from __future__ import annotations

import re
from typing import Any

import mistune

from termrender.blocks import Block, BlockType, InlineSpan
from termrender.renderers.arrow_chain import parse_arrow_chain


class DirectiveError(Exception):
    """Raised when directive syntax is malformed (unclosed, stray closer, etc.)."""

# Matches ANSI escape sequences that are NOT SGR (Select Graphic Rendition).
# SGR sequences have the form \x1b[...m — we keep those.
# Strip OSC (\x1b]), screen control (\x1b[...J, \x1b[...H, etc.), and others.
_UNSAFE_ANSI_RE = re.compile(
    r'\x1b'           # ESC
    r'(?!'             # negative lookahead: don't match SGR
    r'\[[0-9;]*m'      # SGR pattern
    r')'
    r'[\x20-\x7e]*'   # match the rest of the sequence
)


def _sanitize_text(text: str) -> str:
    """Strip non-SGR ANSI escape sequences from text."""
    return _UNSAFE_ANSI_RE.sub('', text)

# Directive opener: :::name or ::::name etc. (3+ colons)
_DIRECTIVE_OPEN = re.compile(
    r"^(:{3,})(\w+)(?:\{([^}]*)\})?\s*$"
)
# Directive closer: 3+ colons on its own line
_DIRECTIVE_CLOSE = re.compile(r"^(:{3,})\s*$")

# Attribute parser: key=value or key="quoted value"
_ATTR_PAIR = re.compile(
    r"""(\w+)\s*=\s*(?:"([^"]*?)"|(\S+))"""
)

# Inline role: :role[content]{key=value ...}
# Used for badges and other inline styled spans.
_INLINE_ROLE_RE = re.compile(
    r":(\w+)\[([^\]]*)\](?:\{([^}]*)\})?"
)

_DIRECTIVE_TO_BLOCK: dict[str, BlockType] = {
    "panel": BlockType.PANEL,
    "columns": BlockType.COLUMNS,
    "col": BlockType.COL,
    "tree": BlockType.TREE,
    "callout": BlockType.CALLOUT,
    "quote": BlockType.QUOTE,
    "code": BlockType.CODE,
    "divider": BlockType.DIVIDER,
    "diff": BlockType.DIFF,
    "bar": BlockType.BAR,
    "progress": BlockType.PROGRESS,
    "gauge": BlockType.GAUGE,
    "stat": BlockType.STAT,
    "timeline": BlockType.TIMELINE,
    "mermaid": BlockType.MERMAID,
    "tasklist": BlockType.LIST,  # alias: forces tasklist styling on the inner list
}

_SELF_CLOSING_DIRECTIVES = frozenset({"divider", "progress", "gauge"})

# Option line: :key: value — intentionally requires a value after the key
# (the \s+(.+) part). Flag-style options like :nosandbox: (no value) won't match
# and will be treated as body content.
_OPTION_LINE_RE = re.compile(r"^:(\w[\w-]*):\s+(.+)$")

_mistune_md = mistune.create_markdown(renderer="ast", plugins=["table"])


def _any_self_closing_before(lines: list[str], close_idx: int) -> bool:
    """Check if there's a self-closing directive on a preceding non-blank line."""
    for j in range(close_idx - 1, -1, -1):
        line = lines[j].strip()
        if not line:
            continue
        m = _DIRECTIVE_OPEN.match(lines[j])
        if m and m.group(2) in _SELF_CLOSING_DIRECTIVES:
            return True
        return False
    return False


def _parse_attrs(raw: str | None) -> dict[str, Any]:
    """Parse directive attributes from {key=value key2="quoted"} string."""
    if not raw:
        return {}
    attrs: dict[str, Any] = {}
    for m in _ATTR_PAIR.finditer(raw):
        key = m.group(1)
        value = m.group(2) if m.group(2) is not None else m.group(3)
        attrs[key] = value
    return attrs


def _convert_inline(nodes: list[dict]) -> list[InlineSpan]:
    """Convert mistune inline AST nodes to InlineSpan list."""
    spans: list[InlineSpan] = []
    for node in nodes:
        ntype = node["type"]
        if ntype == "text":
            spans.append(InlineSpan(text=_sanitize_text(node["raw"])))
        elif ntype == "codespan":
            spans.append(InlineSpan(text=node["raw"], code=True))
        elif ntype == "strong":
            for child in _convert_inline(node.get("children", [])):
                spans.append(InlineSpan(
                    text=child.text, bold=True, italic=child.italic, code=child.code,
                    fg=child.fg, bg=child.bg,
                ))
        elif ntype == "emphasis":
            for child in _convert_inline(node.get("children", [])):
                spans.append(InlineSpan(
                    text=child.text, italic=True, bold=child.bold, code=child.code,
                    fg=child.fg, bg=child.bg,
                ))
        elif ntype == "softbreak":
            spans.append(InlineSpan(text=" "))
        elif ntype == "linebreak":
            # Two \n so wrap_text emits a blank line between the two sides
            # of the hard break, giving more vertical breathing room than a
            # soft wrap. See tests/test_linebreak.py.
            spans.append(InlineSpan(text="\n\n"))
        else:
            # Fallback: try raw text
            if "raw" in node:
                spans.append(InlineSpan(text=node["raw"]))
            elif "children" in node:
                spans.extend(_convert_inline(node["children"]))
    return _expand_inline_roles(_merge_plain_spans(spans))


def _merge_plain_spans(spans: list[InlineSpan]) -> list[InlineSpan]:
    """Coalesce adjacent spans with identical formatting into one.

    Mistune splits text on `[` and other special characters even when no
    valid link/image follows, leaving inline role syntax fragmented across
    multiple text nodes. Merging restores the contiguous text needed for
    `_expand_inline_roles` to find role patterns.
    """
    out: list[InlineSpan] = []
    for span in spans:
        if (
            out
            and not out[-1].code and not span.code
            and out[-1].bold == span.bold
            and out[-1].italic == span.italic
            and out[-1].fg == span.fg
            and out[-1].bg == span.bg
        ):
            merged = InlineSpan(
                text=out[-1].text + span.text,
                bold=span.bold,
                italic=span.italic,
                code=False,
                fg=span.fg,
                bg=span.bg,
            )
            out[-1] = merged
        else:
            out.append(span)
    return out


# Map of badge color name -> (fg, bg) pair. Uses dim background tones so the
# pill reads as subtle but distinct rather than a loud solid block.
_BADGE_COLORS: dict[str, tuple[str, str]] = {
    "red": ("red", "dim_red"),
    "green": ("green", "dim_green"),
    "yellow": ("yellow", "dim_yellow"),
    "blue": ("blue", "dim_blue"),
    "magenta": ("magenta", "dim_magenta"),
    "cyan": ("cyan", "dim_cyan"),
    "gray": ("white", "gray"),
}


def _expand_inline_roles(spans: list[InlineSpan]) -> list[InlineSpan]:
    """Split spans on inline role patterns like :badge[text]{color=green}.

    Code spans are left untouched. Other spans have their text scanned for
    role matches; matches become new spans with role-specific styling, and
    surrounding text becomes plain spans inheriting the original formatting.
    """
    out: list[InlineSpan] = []
    for span in spans:
        if span.code or ":" not in span.text or "[" not in span.text:
            out.append(span)
            continue
        text = span.text
        last = 0
        had_match = False
        for m in _INLINE_ROLE_RE.finditer(text):
            had_match = True
            if m.start() > last:
                out.append(InlineSpan(
                    text=text[last:m.start()],
                    bold=span.bold, italic=span.italic, code=span.code,
                    fg=span.fg, bg=span.bg,
                ))
            role = m.group(1)
            content = m.group(2)
            attrs = _parse_attrs(m.group(3))
            if role == "badge":
                color = attrs.get("color", "blue")
                fg, bg = _BADGE_COLORS.get(color, _BADGE_COLORS["blue"])
                out.append(InlineSpan(
                    text=f" {content} ",
                    bold=True,
                    fg=fg,
                    bg=bg,
                ))
            else:
                # Unknown role — keep raw text so authors notice the typo.
                out.append(InlineSpan(
                    text=m.group(0),
                    bold=span.bold, italic=span.italic,
                    fg=span.fg, bg=span.bg,
                ))
            last = m.end()
        if not had_match:
            out.append(span)
            continue
        if last < len(text):
            out.append(InlineSpan(
                text=text[last:],
                bold=span.bold, italic=span.italic, code=span.code,
                fg=span.fg, bg=span.bg,
            ))
    return out


def _strip_options(body: str) -> tuple[dict[str, str], str]:
    """Strip option lines from the start of a directive body.

    Option lines have the form `:key: value` and appear at the start of the body.
    Blank lines between option lines are allowed. Scanning stops at the first
    non-option, non-blank line.

    Returns (options_dict, remaining_body).
    """
    if not body or not body.lstrip("\n").startswith(":"):
        return {}, body
    lines = body.split("\n")
    options: dict[str, str] = {}
    last_option_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            # blank lines are OK between options
            continue
        m = _OPTION_LINE_RE.match(stripped)
        if m:
            options[m.group(1)] = m.group(2)
            last_option_idx = i
        else:
            break
    if last_option_idx == -1:
        return {}, body
    remaining = "\n".join(lines[last_option_idx + 1:])
    # Strip leading blank lines from remaining body
    remaining = remaining.lstrip("\n")
    return options, remaining


def _convert_ast(nodes: list[dict], _depth: int = 0) -> list[Block]:
    """Convert mistune AST nodes into Block tree."""
    blocks: list[Block] = []
    for node in nodes:
        ntype = node["type"]

        if ntype == "blank_line":
            continue

        if ntype == "heading":
            level = node.get("attrs", {}).get("level", 1)
            text = _convert_inline(node.get("children", []))
            blocks.append(Block(
                type=BlockType.HEADING,
                text=text,
                attrs={"level": level},
            ))

        elif ntype == "paragraph":
            text = _convert_inline(node.get("children", []))
            blocks.append(Block(type=BlockType.PARAGRAPH, text=text))

        elif ntype == "block_code":
            raw = node.get("raw", "")
            info = node.get("attrs", {}).get("info", "")
            # A ```mermaid fence is GFM's standard way to tag a mermaid diagram
            # (GitHub, and most docs/agents that don't know this project's
            # :::mermaid directive, use this form) — route it through the
            # mermaid renderer same as :::mermaid, instead of a plain code panel.
            lang = info.split()[0].lower() if info.split() else ""
            if lang == "mermaid":
                blocks.append(Block(
                    type=BlockType.MERMAID,
                    attrs={"source": raw},
                ))
            # A text/plain (or untagged) fence containing one Unicode-arrow
            # chain is a compact process diagram, not source code. Keep every
            # other language and multi-line fence on the normal code path.
            elif lang in {"", "text", "plain", "plaintext"} and parse_arrow_chain(raw) is not None:
                blocks.append(Block(
                    type=BlockType.ARROW_CHAIN,
                    attrs={"source": raw},
                ))
            else:
                blocks.append(Block(
                    type=BlockType.CODE,
                    attrs={"lang": info, "source": raw},
                ))

        elif ntype == "list":
            ordered = node.get("attrs", {}).get("ordered", False)
            items: list[Block] = []
            for item_node in node.get("children", []):
                if item_node["type"] == "list_item":
                    item_children = item_node.get("children", [])
                    # Tight lists wrap item content in block_text; loose lists
                    # (blank line between items) wrap it in paragraph. Either way,
                    # the first text-bearing child becomes the bullet's inline text.
                    item_spans: list[InlineSpan] = []
                    sub_blocks: list[Block] = []
                    bullet_text_taken = False
                    for child in item_children:
                        ctype = child["type"]
                        if ctype == "block_text":
                            item_spans.extend(_convert_inline(child.get("children", [])))
                        elif ctype == "paragraph" and not bullet_text_taken:
                            item_spans.extend(_convert_inline(child.get("children", [])))
                            bullet_text_taken = True
                        else:
                            sub_blocks.extend(_convert_ast([child], _depth=_depth))
                    items.append(Block(
                        type=BlockType.LIST_ITEM,
                        text=item_spans,
                        children=sub_blocks,
                    ))
            blocks.append(Block(
                type=BlockType.LIST,
                children=items,
                attrs={"ordered": ordered},
            ))

        elif ntype == "table":
            children = node.get("children", [])
            head_node = next((c for c in children if c["type"] == "table_head"), None)
            body_node = next((c for c in children if c["type"] == "table_body"), None)

            headers: list[list[InlineSpan]] = []
            aligns: list[str | None] = []
            if head_node:
                for cell in head_node.get("children", []):
                    headers.append(_convert_inline(cell.get("children", [])))
                    aligns.append(cell.get("attrs", {}).get("align"))

            rows: list[list[list[InlineSpan]]] = []
            if body_node:
                for row_node in body_node.get("children", []):
                    if row_node["type"] == "table_row":
                        row_cells = [
                            _convert_inline(cell.get("children", []))
                            for cell in row_node.get("children", [])
                        ]
                        rows.append(row_cells)

            blocks.append(Block(
                type=BlockType.TABLE,
                attrs={"headers": headers, "rows": rows, "aligns": aligns},
            ))

        elif ntype == "thematic_break":
            blocks.append(Block(type=BlockType.DIVIDER))

        elif ntype == "block_quote":
            children = _convert_ast(node.get("children", []), _depth=_depth)
            blocks.append(Block(type=BlockType.QUOTE, children=children))

        else:
            # Unknown block type - try to extract any content
            if "children" in node:
                blocks.extend(_convert_ast(node["children"], _depth=_depth))

    return blocks


def _parse_markdown(source: str, _depth: int = 0) -> list[Block]:
    """Parse a markdown string via mistune and convert to Block list."""
    if not source.strip():
        return []
    ast_nodes = _mistune_md(source)
    return _convert_ast(ast_nodes, _depth=_depth)


def _find_nested_directives(body_lines: list[str]) -> list[str]:
    """Return names of directive openers found in body lines."""
    names: list[str] = []
    for line in body_lines:
        m = _DIRECTIVE_OPEN.match(line)
        if m:
            names.append(m.group(2))
    return names


def _stray_closer_message(
    abs_line: int, close_colons: str, trace: list[str],
    last_closed: dict | None,
) -> str:
    """Format a stray-closer error with trace and fix suggestion."""
    msg = f"line {abs_line}: stray '{close_colons}' closer — no directive is open"
    if trace:
        msg += "\n\n  directive trace:\n" + "\n".join(trace)

    if last_closed:
        nested = _find_nested_directives(last_closed["body_lines"])
        if nested:
            outer = last_closed["name"]
            inner = nested[0]
            fix_colons = ":" * (last_closed["colon_count"] + 1)
            msg += (
                f"\n\n  Likely cause: :::{outer} at line {last_closed['open_line']} "
                f"contains a nested :::{inner} with the same colon count.\n"
                f"  The inner ':::' closer (line {last_closed['close_line']}) "
                f"matched the outer directive instead.\n"
                f"  Fix: use {fix_colons}{outer} for the outer directive"
            )
            return msg

    msg += (
        "\n\n  Fix: remove this stray closer, or if nesting is intended,\n"
        "  use more colons on outer directives (::::outer wraps :::inner)"
    )
    return msg


def _unclosed_directive_message(
    open_line: int, colons: str, name: str, trace: list[str],
    body_lines: list[str],
) -> str:
    """Format an unclosed-directive error with trace and fix suggestion."""
    msg = f"line {open_line}: unclosed '{colons}{name}' — add '{colons}' on a new line to close it"
    if trace:
        msg += "\n\n  directive trace:\n" + "\n".join(trace)
    return msg


def _split_directives(source: str, _line_offset: int = 0) -> list[dict]:
    """Split source into directive and markdown segments.

    Returns a list of segments, each being either:
      {"type": "markdown", "content": str}
      {"type": "directive", "name": str, "attrs": dict, "body": str,
       "body_start_offset": int}

    On error, raises DirectiveError with a directive trace showing the
    sequence of opens/closes that led to the error state.
    """
    lines = source.split("\n")
    segments: list[dict] = []
    current_md_lines: list[str] = []
    md_start_idx: int | None = None  # 0-based index of the first accumulated md line
    stack: list[dict] = []  # stack of open directives
    trace: list[str] = []   # event log for error diagnostics
    last_closed: dict | None = None  # most recently closed directive entry

    i = 0
    while i < len(lines):
        line = lines[i]
        abs_line = _line_offset + i + 1  # 1-indexed file-absolute line number

        # Check for directive opener
        m_open = _DIRECTIVE_OPEN.match(line)
        if m_open:
            colons = m_open.group(1)
            name = m_open.group(2)
            attrs_raw = m_open.group(3)
            if not stack:
                # Top-level directive opening — flush accumulated markdown
                if current_md_lines:
                    segments.append({
                        "type": "markdown",
                        "content": "\n".join(current_md_lines),
                        "line_offset": _line_offset + (md_start_idx or 0),
                    })
                    current_md_lines = []
                    md_start_idx = None
                entry = {
                    "name": name,
                    "attrs_raw": attrs_raw,
                    "body_lines": [],
                    "colon_count": len(colons),
                    "open_line": abs_line,
                    "body_start_offset": _line_offset + i + 1,
                }
                # Self-closing directives (no body content expected)
                if entry["name"] in _SELF_CLOSING_DIRECTIVES:
                    segments.append({
                        "type": "directive",
                        "name": entry["name"],
                        "attrs": _parse_attrs(entry["attrs_raw"]),
                        "body": "",
                        "body_start_offset": entry["body_start_offset"],
                        "src_start": abs_line,
                        "src_end": abs_line,
                    })
                    trace.append(f"    line {abs_line}: {colons}{name}  (self-closing)")
                else:
                    stack.append(entry)
                    trace.append(f"    line {abs_line}: {colons}{name}  opened")
            else:
                # Nested directive — always treat as body content
                stack[-1]["body_lines"].append(line)
            i += 1
            continue

        # Check for directive closer
        m_close = _DIRECTIVE_CLOSE.match(line)
        if m_close and not stack:
            if not _any_self_closing_before(lines, i):
                close_colons = m_close.group(1)
                trace.append(f"    line {abs_line}: {close_colons}  stray closer (nothing is open)")
                raise DirectiveError(
                    _stray_closer_message(abs_line, close_colons, trace, last_closed)
                )
            # Stray closer after a self-closing directive like divider — skip
            i += 1
            continue
        if m_close and stack:
            close_colon_count = len(m_close.group(1))
            if close_colon_count != stack[-1]["colon_count"]:
                # Different colon count — treat as body content
                stack[-1]["body_lines"].append(line)
            else:
                # Closing the open directive
                entry = stack.pop()
                closed_colons = ":" * entry["colon_count"]
                nested = _find_nested_directives(entry["body_lines"])
                nested_note = ""
                if nested:
                    names = ", ".join(f":::{n}" for n in nested[:3])
                    nested_note = f"  — body has nested {names}"
                trace.append(
                    f"    line {abs_line}: {closed_colons}  "
                    f"closed {entry['name']} (opened line {entry['open_line']})"
                    f"{nested_note}"
                )
                last_closed = {
                    "name": entry["name"],
                    "colon_count": entry["colon_count"],
                    "open_line": entry["open_line"],
                    "close_line": abs_line,
                    "body_lines": entry["body_lines"],
                }
                segments.append({
                    "type": "directive",
                    "name": entry["name"],
                    "attrs": _parse_attrs(entry["attrs_raw"]),
                    "body": "\n".join(entry["body_lines"]),
                    "body_start_offset": entry["body_start_offset"],
                    "src_start": entry["open_line"],
                    "src_end": abs_line,
                })
            i += 1
            continue

        # Regular line
        if stack:
            stack[-1]["body_lines"].append(line)
        else:
            if md_start_idx is None:
                md_start_idx = i
            current_md_lines.append(line)
        i += 1

    # Flush remaining markdown
    if current_md_lines:
        segments.append({
            "type": "markdown",
            "content": "\n".join(current_md_lines),
            "line_offset": _line_offset + (md_start_idx or 0),
        })

    # If stack is not empty, the source has unclosed directives
    if stack:
        unclosed = stack[-1]
        colons = ":" * unclosed["colon_count"]
        name = unclosed["name"]
        open_line = unclosed["open_line"]
        trace.append(f"    line {open_line}: {colons}{name}  ← still open at end of input")
        raise DirectiveError(
            _unclosed_directive_message(open_line, colons, name, trace, unclosed["body_lines"])
        )

    return segments


_MAX_PARSE_DEPTH = 50


def _directive_to_block(name: str, attrs: dict[str, Any], body: str, _depth: int = 0, _line_offset: int = 0) -> Block:
    """Convert a parsed directive into a Block."""
    # Strip option lines from body; inline attrs take precedence over options
    options, body = _strip_options(body)
    for key, value in options.items():
        if key not in attrs:
            attrs[key] = value

    block_type = _DIRECTIVE_TO_BLOCK.get(name, BlockType.PANEL)

    # Tree, Code, Diff, Mermaid: store raw body, don't parse as markdown
    if block_type in (BlockType.TREE, BlockType.CODE, BlockType.DIFF, BlockType.MERMAID):
        attrs["source"] = body
        return Block(type=block_type, attrs=attrs)

    # Bar chart: parse body as label:value lines
    if block_type == BlockType.BAR:
        attrs["items"] = _parse_bar_items(body)
        return Block(type=block_type, attrs=attrs)

    # Timeline: parse body as list of date/event entries
    if block_type == BlockType.TIMELINE:
        attrs["entries"] = _parse_timeline_entries(body)
        return Block(type=block_type, attrs=attrs)

    # Divider, progress, gauge: no children, attrs only
    if block_type in (BlockType.DIVIDER, BlockType.PROGRESS, BlockType.GAUGE):
        return Block(type=block_type, attrs=attrs)

    # Stat: optional caption body parsed as markdown
    if block_type == BlockType.STAT:
        body_doc = parse(body, _depth=_depth + 1, _line_offset=_line_offset) if body.strip() else Block(type=BlockType.DOCUMENT)
        return Block(type=block_type, children=body_doc.children, attrs=attrs)

    # Tasklist alias: parse body, find the inner list, force tasklist styling
    if name == "tasklist":
        body_doc = parse(body, _depth=_depth + 1, _line_offset=_line_offset)
        for child in body_doc.children:
            if child.type == BlockType.LIST:
                child.attrs["tasklist"] = True
                # Treat any unmarked items as unchecked todo entries.
                for item in child.children:
                    if item.type == BlockType.LIST_ITEM and "checked" not in item.attrs:
                        item.attrs["checked"] = False
                return child
        # No list found — return an empty tasklist for graceful degradation
        return Block(type=BlockType.LIST, attrs={"tasklist": True, **attrs})

    # Recursively parse the body through the full two-pass pipeline
    body_doc = parse(body, _depth=_depth + 1, _line_offset=_line_offset)
    return Block(
        type=block_type,
        children=body_doc.children,
        attrs=attrs,
    )


_BAR_ITEM_RE = re.compile(r"^\s*(.+?)\s*[:|]\s*([-+]?\d+(?:\.\d+)?)\s*(\S*)\s*$")


def _parse_bar_items(body: str) -> list[dict[str, Any]]:
    """Parse bar-chart body lines: 'Label: 123' or 'Label | 123 unit'."""
    items: list[dict[str, Any]] = []
    for raw in body.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _BAR_ITEM_RE.match(line)
        if not m:
            continue
        label = m.group(1)
        try:
            value = float(m.group(2))
        except ValueError:
            continue
        unit = m.group(3) or ""
        items.append({"label": label, "value": value, "unit": unit})
    return items


_TIMELINE_ITEM_RE = re.compile(r"^\s*[-*]\s*(.+?)\s*[:|]\s*(.+)$")


def _parse_timeline_entries(body: str) -> list[dict[str, str]]:
    """Parse timeline body lines: '- 2024-01: launched'."""
    entries: list[dict[str, str]] = []
    for raw in body.split("\n"):
        m = _TIMELINE_ITEM_RE.match(raw)
        if not m:
            continue
        entries.append({"date": m.group(1).strip(), "event": m.group(2).strip()})
    return entries


_TASK_MARKER_RE = re.compile(r"^\s*\[([ xX!])\]\s+")


def _apply_tasklist_markers(block: Block) -> Block:
    """Walk a block tree and convert leading [ ]/[x] in list items to checked attrs."""
    if block.type == BlockType.LIST:
        any_task = False
        for item in block.children:
            if item.type == BlockType.LIST_ITEM and item.text:
                first_text = item.text[0].text
                m = _TASK_MARKER_RE.match(first_text)
                if m:
                    marker = m.group(1)
                    item.attrs["checked"] = marker.lower() == "x"
                    if marker == "!":
                        item.attrs["pending"] = True
                    item.text[0] = InlineSpan(
                        text=first_text[m.end():],
                        bold=item.text[0].bold,
                        italic=item.text[0].italic,
                        code=item.text[0].code,
                        fg=item.text[0].fg,
                        bg=item.text[0].bg,
                    )
                    any_task = True
        if any_task:
            block.attrs["tasklist"] = True
    # Recurse into children
    for child in block.children:
        _apply_tasklist_markers(child)
    return block


# ── Source-line assignment for markdown-parsed blocks ───────────────────────
#
# mistune's AST carries no source positions, so block→line mapping is
# reconstructed by a type-directed scan over the segment's lines: for each
# top-level block mistune produced (in order), consume the lines that belong
# to a block of that type. Best-effort by design — the map feeds block-level
# review anchoring, where ±1 line on exotic constructs is acceptable.

_MD_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_MD_ATX_RE = re.compile(r"^ {0,3}#{1,6}(\s|$)")
_MD_THEMATIC_RE = re.compile(r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
_MD_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d{1,9}[.)])(?:\s|$)")
_MD_QUOTE_RE = re.compile(r"^ {0,3}>")
_MD_SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)\s*$")
_MD_INDENT_RE = re.compile(r"^(?: {2,}|\t)")


def _starts_new_leaf(line: str) -> bool:
    """True when a line unambiguously starts a new leaf block (not a paragraph)."""
    return bool(
        _MD_ATX_RE.match(line)
        or _MD_FENCE_RE.match(line)
        or _MD_THEMATIC_RE.match(line)
        or _MD_QUOTE_RE.match(line)
        or _MD_LIST_RE.match(line)
    )


def _consume_md_block(block: Block, lines: list[str], i: int) -> int:
    """Return the exclusive end index of the block starting at lines[i]."""
    n = len(lines)
    t = block.type

    if t == BlockType.HEADING:
        if _MD_ATX_RE.match(lines[i]):
            return i + 1
        # setext heading: text line(s) + ===/--- underline
        j = i + 1
        while j < n and not _MD_SETEXT_RE.match(lines[j]):
            j += 1
        return min(j + 1, n)

    if t == BlockType.DIVIDER:
        return i + 1

    if t in (BlockType.CODE, BlockType.MERMAID, BlockType.ARROW_CHAIN):
        m = _MD_FENCE_RE.match(lines[i])
        if m:
            fence = m.group(1)
            close = re.compile(
                r"^ {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$"
            )
            j = i + 1
            while j < n and not close.match(lines[j]):
                j += 1
            return min(j + 1, n)
        # indented code block
        j = i
        while j < n and (not lines[j].strip() or lines[j].startswith(("    ", "\t"))):
            j += 1
        while j > i + 1 and not lines[j - 1].strip():
            j -= 1
        return max(j, i + 1)

    if t == BlockType.TABLE:
        j = i
        while j < n and lines[j].strip() and "|" in lines[j]:
            j += 1
        return max(j, i + 1)

    if t == BlockType.LIST:
        j = i
        while j < n:
            line = lines[j]
            if not line.strip():
                # blank inside a list: continues only if the next non-blank
                # line is another marker or an indented continuation
                k = j + 1
                while k < n and not lines[k].strip():
                    k += 1
                if k < n and (_MD_LIST_RE.match(lines[k]) or _MD_INDENT_RE.match(lines[k])):
                    j = k
                    continue
                break
            if _MD_LIST_RE.match(line) or _MD_INDENT_RE.match(line):
                j += 1
                continue
            if _MD_ATX_RE.match(line) or _MD_FENCE_RE.match(line) or _MD_THEMATIC_RE.match(line) or _MD_QUOTE_RE.match(line):
                break
            j += 1  # lazy paragraph continuation of an item
        return max(j, i + 1)

    if t == BlockType.QUOTE:
        j = i
        while j < n and lines[j].strip():
            line = lines[j]
            if j > i and not _MD_QUOTE_RE.match(line) and _starts_new_leaf(line):
                break
            j += 1
        return max(j, i + 1)

    # PARAGRAPH and anything else: until blank or a new-leaf starter
    j = i
    while j < n and lines[j].strip():
        if j > i and _starts_new_leaf(lines[j]):
            break
        j += 1
    return max(j, i + 1)


def _assign_source_lines(blocks: list[Block], lines: list[str], offset: int) -> None:
    """Assign 1-indexed inclusive src_start/src_end to each block, in order.

    `offset` is the number of source lines preceding `lines` in the file.
    """
    i = 0
    n = len(lines)
    for block in blocks:
        while i < n and not lines[i].strip():
            i += 1
        if i >= n:
            # Scanner exhausted (drift on an exotic construct) — pin the
            # remaining blocks to the last line rather than leaving them unmapped.
            block.src_start = offset + n
            block.src_end = offset + n
            continue
        start = i
        i = _consume_md_block(block, lines, start)
        block.src_start = offset + start + 1
        block.src_end = offset + i


def parse(source: str, _depth: int = 0, _line_offset: int = 0) -> Block:
    """Parse markdown+directive source into a Block tree.

    Returns a Block with type=DOCUMENT as root.
    """
    if _depth > _MAX_PARSE_DEPTH:
        raise ValueError(f"Maximum directive nesting depth ({_MAX_PARSE_DEPTH}) exceeded")
    segments = _split_directives(source, _line_offset=_line_offset)
    children: list[Block] = []

    for seg in segments:
        if seg["type"] == "markdown":
            md_blocks = _parse_markdown(seg["content"], _depth=_depth)
            _assign_source_lines(
                md_blocks, seg["content"].split("\n"), seg.get("line_offset", _line_offset),
            )
            children.extend(md_blocks)
        else:
            block = _directive_to_block(
                seg["name"], seg["attrs"], seg["body"], _depth=_depth,
                _line_offset=seg.get("body_start_offset", 0),
            )
            block.src_start = seg.get("src_start")
            block.src_end = seg.get("src_end")
            children.append(block)

    # Walk the tree to auto-promote any markdown list with [ ]/[x] markers
    # into a tasklist, regardless of whether it sits inside a directive.
    for child in children:
        _apply_tasklist_markers(child)

    return Block(type=BlockType.DOCUMENT, children=children)
