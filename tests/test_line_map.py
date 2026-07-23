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
