"""Line-map contract: render_with_map maps rendered rows to source blocks.

This is the load-bearing contract humanloop's terminal review surface anchors
on: `lines` must equal the plain render, `rows` must be parallel to `lines`,
and each top-level block must carry a sane 1-indexed source range.
"""

from termrender import render, render_with_map

SOURCE = """\
# Title

First paragraph line one
still the first paragraph.

- item one
- item two
  - nested

```python
print("hi")
```

| a | b |
|---|---|
| 1 | 2 |

:::panel{title="P"}
inside the panel
:::

```mermaid
graph LR
  A --> B
```

Last paragraph.
"""


def test_lines_match_plain_render():
    result = render_with_map(SOURCE, width=60, color=True)
    plain = render(SOURCE, width=60, color=True)
    assert "\n".join(result["lines"]) == plain


def test_rows_parallel_and_valid():
    result = render_with_map(SOURCE, width=60, color=True)
    lines, rows, blocks = result["lines"], result["rows"], result["blocks"]
    assert len(rows) == len(lines)
    n = len(blocks)
    for entry in rows:
        assert entry is None or (0 <= entry < n)
    # Every block owns at least one row, in order.
    seen = [e for e in rows if e is not None]
    assert seen == sorted(seen)
    assert set(seen) == set(range(n))


def test_block_source_ranges():
    result = render_with_map(SOURCE, width=60, color=True)
    blocks = result["blocks"]
    types = [b["type"] for b in blocks]
    assert types == [
        "heading", "paragraph", "list", "code", "table",
        "panel", "mermaid", "paragraph",
    ]
    heading, para1, lst, code, table, panel, mermaid, para2 = blocks
    assert (heading["start"], heading["end"]) == (1, 1)
    assert (para1["start"], para1["end"]) == (3, 4)
    assert (lst["start"], lst["end"]) == (6, 8)
    assert (code["start"], code["end"]) == (10, 12)
    assert (table["start"], table["end"]) == (14, 16)
    # Directive block spans opener..closer.
    assert (panel["start"], panel["end"]) == (18, 20)
    assert (mermaid["start"], mermaid["end"]) == (22, 25)
    assert blocks[-1]["start"] == 27 and blocks[-1]["end"] == 27
    # Ranges are monotonic and non-overlapping.
    for prev, cur in zip(blocks, blocks[1:]):
        assert prev["end"] < cur["start"]


def test_empty_document():
    result = render_with_map("", width=40, color=False)
    assert result["blocks"] == []
    assert result["rows"] == [None] * len(result["rows"])


# ── Leaf spans ──────────────────────────────────────────────────────────────
# spans[] refines rows[]: per rendered row, the finest source range the
# renderer knows — list items, table rows, and code lines each their own.

import re

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

SPAN_SOURCE = """\
- item one
- item two has a fairly long text that wraps at this width
  - nested a
  - nested b
- item three

| a | b |
|---|---|
| 1 | 2 |
| 3 | 4 |

```python
print("hi")
x = 1
```
"""


def _spans_by_text(result):
    """Map plain rendered text -> span for single rows of interest."""
    return {
        _ANSI.sub("", line).strip(): tuple(span) if span else None
        for line, span in zip(result["lines"], result["spans"])
    }


def test_spans_parallel_and_shape():
    result = render_with_map(SPAN_SOURCE, width=40, color=True)
    assert len(result["spans"]) == len(result["lines"])
    for span, row in zip(result["spans"], result["rows"]):
        if row is None:
            assert span is None  # separator rows carry no span
        else:
            assert span is not None
            start, end = span
            assert isinstance(start, int) and isinstance(end, int)
            assert 1 <= start <= end


def test_list_items_get_own_spans():
    result = render_with_map(SPAN_SOURCE, width=40, color=True)
    by_text = _spans_by_text(result)
    assert by_text["• item one"] == (1, 1)
    assert by_text["• nested a"] == (3, 3)
    assert by_text["• nested b"] == (4, 4)
    assert by_text["• item three"] == (5, 5)
    # Wrapped continuation rows of item two share its own text line (not the
    # nested items' lines).
    item_two_spans = {
        tuple(span)
        for line, span in zip(result["lines"], result["spans"])
        if "item two" in _ANSI.sub("", line) or "wraps" in _ANSI.sub("", line)
    }
    assert item_two_spans == {(2, 2)}


def test_table_rows_get_own_spans():
    result = render_with_map(SPAN_SOURCE, width=40, color=True)
    rows = [
        (tuple(span), _ANSI.sub("", line).strip())
        for line, span, row in zip(result["lines"], result["spans"], result["rows"])
        if span is not None and "│ 1" in _ANSI.sub("", line)
    ]
    assert rows and all(s == (9, 9) for s, _ in rows)
    rows3 = [
        tuple(span)
        for line, span in zip(result["lines"], result["spans"])
        if span is not None and "│ 3" in _ANSI.sub("", line)
    ]
    assert rows3 and all(s == (10, 10) for s in rows3)
    # Header rows map to the header source line.
    header = [
        tuple(span)
        for line, span in zip(result["lines"], result["spans"])
        if span is not None and re.search(r"│\s*a\s*│", _ANSI.sub("", line))
    ]
    assert header and all(s == (7, 7) for s in header)


def test_code_lines_map_one_to_one():
    result = render_with_map(SPAN_SOURCE, width=40, color=True)
    print_row = next(
        tuple(span)
        for line, span in zip(result["lines"], result["spans"])
        if span is not None and 'print("hi")' in _ANSI.sub("", line)
    )
    x_row = next(
        tuple(span)
        for line, span in zip(result["lines"], result["spans"])
        if span is not None and "x = 1" in _ANSI.sub("", line)
    )
    assert print_row == (13, 13)
    assert x_row == (14, 14)
    # Chrome rows (borders) span the whole block.
    chrome = [
        tuple(span)
        for line, span, row in zip(result["lines"], result["spans"], result["rows"])
        if span is not None and row == 2 and "┌" in _ANSI.sub("", line)
    ]
    assert chrome == [(12, 15)]


def test_adjacent_lists_of_different_types_split():
    src = "1. ordered one\n2. ordered two\n\n- [ ] task open\n- [x] task done\n"
    result = render_with_map(src, width=40, color=False)
    assert [b["type"] for b in result["blocks"]] == ["list", "list"]
    assert (result["blocks"][0]["start"], result["blocks"][0]["end"]) == (1, 2)
    assert result["blocks"][1]["start"] == 4
    by_text = _spans_by_text(result)
    assert by_text["1. ordered one"] == (1, 1)
    assert by_text["2. ordered two"] == (2, 2)
    assert by_text["○ task open"] == (4, 4)
    assert by_text["● task done"] == (5, 5)


def test_spans_do_not_change_rendered_lines():
    result = render_with_map(SPAN_SOURCE, width=40, color=True)
    assert "\n".join(result["lines"]) == render(SPAN_SOURCE, width=40, color=True)
