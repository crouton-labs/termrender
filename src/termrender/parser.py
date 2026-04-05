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

# Directive opener: :::name or :::name{attrs}
_DIRECTIVE_OPEN = re.compile(
    r"^:::(\w+)(?:\{([^}]*)\})?\s*$"
)
# Directive closer: exactly ::: on its own line
_DIRECTIVE_CLOSE = re.compile(r"^:::\s*$")

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

_mistune_md = mistune.create_markdown(renderer="ast")


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


def _convert_ast(nodes: list[dict]) -> list[Block]:
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
            if info == "mermaid":
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
                            sub_blocks.extend(_convert_ast([child]))
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

        elif ntype == "thematic_break":
            blocks.append(Block(type=BlockType.DIVIDER))

        elif ntype == "block_quote":
            children = _convert_ast(node.get("children", []))
            blocks.append(Block(type=BlockType.QUOTE, children=children))

        else:
            # Unknown block type - try to extract any content
            if "children" in node:
                blocks.extend(_convert_ast(node["children"]))

    return blocks


def _parse_markdown(source: str) -> list[Block]:
    """Parse a markdown string via mistune and convert to Block list."""
    if not source.strip():
        return []
    ast_nodes = _mistune_md(source)
    return _convert_ast(ast_nodes)


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
            if not stack:
                # Top-level directive opening — flush accumulated markdown
                if current_md_lines:
                    segments.append({
                        "type": "markdown",
                        "content": "\n".join(current_md_lines),
                    })
                    current_md_lines = []
                entry = {
                    "name": m_open.group(1),
                    "attrs_raw": m_open.group(2),
                    "body_lines": [],
                    "depth": 1,
                }
                # Self-closing directives (no body content expected)
                if entry["name"] in ("divider",):
                    segments.append({
                        "type": "directive",
                        "name": entry["name"],
                        "attrs": _parse_attrs(entry["attrs_raw"]),
                        "body": "",
                    })
                else:
                    stack.append(entry)
            else:
                # Nested directive — track depth and include line in body
                stack[-1]["depth"] += 1
                stack[-1]["body_lines"].append(line)
            i += 1
            continue

        # Check for directive closer
        m_close = _DIRECTIVE_CLOSE.match(line)
        if m_close and stack:
            if stack[-1]["depth"] > 1:
                # Closing a nested directive
                stack[-1]["depth"] -= 1
                stack[-1]["body_lines"].append(line)
            else:
                # Closing the top-level directive
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

    # If stack is not empty, treat unclosed directives as markdown
    for entry in stack:
        body = "\n".join(entry["body_lines"])
        segments.append({
            "type": "markdown",
            "content": f":::{entry['name']}\n{body}",
        })

    return segments


_MAX_PARSE_DEPTH = 50


def _directive_to_block(name: str, attrs: dict[str, Any], body: str, _depth: int = 0) -> Block:
    """Convert a parsed directive into a Block."""
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
            children.extend(_parse_markdown(seg["content"]))
        else:
            children.append(_directive_to_block(
                seg["name"], seg["attrs"], seg["body"], _depth=_depth,
            ))

    return Block(type=BlockType.DOCUMENT, children=children)
