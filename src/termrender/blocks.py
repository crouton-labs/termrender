"""Core block data model for termrender."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BlockType(Enum):
    """Types of renderable blocks."""

    DOCUMENT = "document"
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    PANEL = "panel"
    COLUMNS = "columns"
    COL = "col"
    TREE = "tree"
    CALLOUT = "callout"
    QUOTE = "quote"
    CODE = "code"
    DIVIDER = "divider"
    MERMAID = "mermaid"
    TABLE = "table"
    LIST = "list"
    LIST_ITEM = "list_item"


@dataclass
class InlineSpan:
    """A span of inline text with optional formatting."""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


@dataclass
class Block:
    """A renderable block element with optional children and inline text."""

    type: BlockType
    children: list[Block] = field(default_factory=list)
    text: list[InlineSpan] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)
    width: int | None = None
    height: int | None = None
