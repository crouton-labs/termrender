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

_DIRECTIVE_TO_BLOCK: dict[str, BlockType] = {
    "panel": BlockType.PANEL,
    "columns": BlockType.COLUMNS,
    "col": BlockType.COL,
    "tree": BlockType.TREE,
    "callout": BlockType.CALLOUT,
    "quote": BlockType.QUOTE,
    "code": BlockType.CODE,
    "divider": BlockType.DIVIDER,
}

_SELF_CLOSING_DIRECTIVES = frozenset({"divider"})

# MyST backtick fence directive: ```{name} optional-argument
_BACKTICK_DIRECTIVE_RE = re.compile(r"^\{(\w[\w-]*)\}(.*)")

# MyST option line: :key: value — intentionally requires a value after the key
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
                spans.append(InlineSpan(text=child.text, bold=True, italic=child.italic, code=child.code))
        elif ntype == "emphasis":
            for child in _convert_inline(node.get("children", [])):
                spans.append(InlineSpan(text=child.text, italic=True, bold=child.bold, code=child.code))
        elif ntype == "softbreak":
            spans.append(InlineSpan(text=" "))
        elif ntype == "linebreak":
            spans.append(InlineSpan(text="\n"))
        else:
            # Fallback: try raw text
            if "raw" in node:
                spans.append(InlineSpan(text=node["raw"]))
            elif "children" in node:
                spans.extend(_convert_inline(node["children"]))
    return spans


def _strip_options(body: str) -> tuple[dict[str, str], str]:
    """Strip MyST option lines from the start of a directive body.

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
            # MyST backtick fence directive: ```{name} optional-arg
            m_directive = _BACKTICK_DIRECTIVE_RE.match(info) if info else None
            if m_directive:
                dir_name = m_directive.group(1)
                arg_text = m_directive.group(2).strip()
                if dir_name == "mermaid":
                    options, body = _strip_options(raw)
                    attrs = dict(options)
                    if arg_text:
                        attrs["argument"] = arg_text
                    attrs["source"] = body
                    blocks.append(Block(type=BlockType.MERMAID, attrs=attrs))
                else:
                    attrs: dict[str, Any] = {}
                    if arg_text:
                        attrs["argument"] = arg_text
                    blocks.append(_directive_to_block(dir_name, attrs, raw, _depth=_depth))
            elif info == "mermaid":
                blocks.append(Block(
                    type=BlockType.MERMAID,
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
                    # list_item contains block_text nodes
                    item_spans: list[InlineSpan] = []
                    sub_blocks: list[Block] = []
                    for child in item_children:
                        if child["type"] == "block_text":
                            item_spans.extend(_convert_inline(child.get("children", [])))
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


def _split_directives(source: str) -> list[dict]:
    """Split source into directive and markdown segments.

    Returns a list of segments, each being either:
      {"type": "markdown", "content": str}
      {"type": "directive", "name": str, "attrs": dict, "body": str}
    """
    lines = source.split("\n")
    segments: list[dict] = []
    current_md_lines: list[str] = []
    stack: list[dict] = []  # stack of open directives

    i = 0
    while i < len(lines):
        line = lines[i]

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
                    })
                    current_md_lines = []
                entry = {
                    "name": name,
                    "attrs_raw": attrs_raw,
                    "body_lines": [],
                    "colon_count": len(colons),
                }
                # Self-closing directives (no body content expected)
                if entry["name"] in _SELF_CLOSING_DIRECTIVES:
                    segments.append({
                        "type": "directive",
                        "name": entry["name"],
                        "attrs": _parse_attrs(entry["attrs_raw"]),
                        "body": "",
                    })
                else:
                    stack.append(entry)
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
                raise DirectiveError(
                    f"line {i + 1}: stray '{close_colons}' closer with no open directive"
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
                segments.append({
                    "type": "directive",
                    "name": entry["name"],
                    "attrs": _parse_attrs(entry["attrs_raw"]),
                    "body": "\n".join(entry["body_lines"]),
                })
            i += 1
            continue

        # Regular line
        if stack:
            stack[-1]["body_lines"].append(line)
        else:
            current_md_lines.append(line)
        i += 1

    # Flush remaining markdown
    if current_md_lines:
        segments.append({
            "type": "markdown",
            "content": "\n".join(current_md_lines),
        })

    # If stack is not empty, the source has unclosed directives
    if stack:
        unclosed = stack[-1]
        colons = ":" * unclosed["colon_count"]
        name = unclosed["name"]
        raise DirectiveError(
            f"unclosed directive '{colons}{name}' — missing closing '{colons}'"
        )

    return segments


_MAX_PARSE_DEPTH = 50


def _directive_to_block(name: str, attrs: dict[str, Any], body: str, _depth: int = 0) -> Block:
    """Convert a parsed directive into a Block."""
    # Strip option lines from body; inline attrs take precedence over options
    options, body = _strip_options(body)
    for key, value in options.items():
        if key not in attrs:
            attrs[key] = value

    block_type = _DIRECTIVE_TO_BLOCK.get(name, BlockType.PANEL)

    # Tree and Code directives: store raw body, don't parse as markdown
    if block_type in (BlockType.TREE, BlockType.CODE):
        attrs["source"] = body
        return Block(type=block_type, attrs=attrs)

    # Divider: no children
    if block_type == BlockType.DIVIDER:
        return Block(type=BlockType.DIVIDER, attrs=attrs)

    # Recursively parse the body through the full two-pass pipeline
    body_doc = parse(body, _depth=_depth + 1)
    return Block(
        type=block_type,
        children=body_doc.children,
        attrs=attrs,
    )


def parse(source: str, _depth: int = 0) -> Block:
    """Parse markdown+directive source into a Block tree.

    Returns a Block with type=DOCUMENT as root.
    """
    if _depth > _MAX_PARSE_DEPTH:
        raise ValueError(f"Maximum directive nesting depth ({_MAX_PARSE_DEPTH}) exceeded")
    segments = _split_directives(source)
    children: list[Block] = []

    for seg in segments:
        if seg["type"] == "markdown":
            children.extend(_parse_markdown(seg["content"], _depth=_depth))
        else:
            children.append(_directive_to_block(
                seg["name"], seg["attrs"], seg["body"], _depth=_depth,
            ))

    return Block(type=BlockType.DOCUMENT, children=children)
