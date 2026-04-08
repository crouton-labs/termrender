import unittest

from termrender import render
from termrender.style import visual_len

SHOWPIECE_INPUT = """\
:::::::panel{title="Deploy — api-gateway v3.2.0" color="cyan"}

Completed at **14:32 UTC** on `prod-us-east-1`. Health checks passing.

::::::columns
:::::col{width="55%"}
::::panel{title="Services" color="green"}
:::tree
api-gateway/ [x]
  auth/ [x]
  rate-limiter/ [x]
  cache/ [x]
worker-pool/
  job-runner/ [x]
  scheduler/ [!]
  dead-letter/ [x]
:::
::::
:::::
:::::col{width="45%"}
::::callout{type="success"}
6 of 7 services healthy
::::

::::callout{type="warning"}
scheduler: 83% memory
GC tuning shipping next release
::::

- **p99 latency**: 34ms
- **error rate**: 0.02%
- **throughput**: 12.4k req/s
:::::
::::::

::::divider{label="rollback"}

::::code{lang="bash"}
# If p99 exceeds 200ms:
kubectl rollout undo deployment/api-gateway -n prod
kubectl rollout status deployment/api-gateway -n prod
::::

::::quote{author="deploy-bot"}
Previous stable: v3.1.4 (deployed 2025-03-28)
::::
:::::::
"""

COLUMNS_TREE_INPUT = """\
:::::columns
::::col{width="50%"}
:::tree
root/
  a/ [x]
  b/ [!]
  c/
:::
::::
::::col{width="50%"}
- item one
- item two
- item three
::::
:::::
"""

PANEL_TREE_INPUT = """\
::::panel{title="Test"}
:::tree
a/ [x]
b/ [!]
c/
:::
::::
"""

# A panel nested inside :::col whose content (a wide mermaid diagram) exceeds
# the column allocation. The inner panel's side walls and corner glyphs must
# stay aligned even when content forces the panel to grow past its allotment.
NESTED_PANEL_OVERFLOW_INPUT = """\
::::::panel{title="Outer" color="cyan"}
:::::columns
::::col{width="58%"}
:::panel{title="Request Flow" color="blue"}
```mermaid
graph TD
    A[Edge gateway<br/>accepts request] --> B{Token valid?}
    B -->|yes| C[Route via LB<br/>to backend pool]
    B -->|no| D[Reject 401,<br/>write audit log]
    C --> E[Service responds,<br/>metrics emitted]
```
:::
::::
::::col{width="42%"}
right
::::
:::::
::::::
"""


class TestColumnAlignment(unittest.TestCase):

    def test_showpiece_renders_without_error(self):
        output = render(SHOWPIECE_INPUT, width=80, color=False)
        self.assertTrue(len(output) > 0)

    def test_column_lines_same_width(self):
        output = render(COLUMNS_TREE_INPUT, width=60, color=False)
        lines = output.split("\n")
        # Strip trailing newline artifact — last element may be empty
        if lines and lines[-1] == "":
            lines = lines[:-1]
        widths = [visual_len(line) for line in lines]
        for i, (line, w) in enumerate(zip(lines, widths)):
            self.assertEqual(
                w,
                60,
                f"Line {i} has visual width {w}, expected 60: {line!r}",
            )

    def test_status_marker_visual_width(self):
        # ✔ ⚠ ✖ ℹ are text-presentation by default (1 cell wide);
        # they only become 2-wide with an explicit VS16 suffix.
        self.assertEqual(visual_len("✔"), 1)
        self.assertEqual(visual_len("⚠"), 1)
        self.assertEqual(visual_len("✖"), 1)
        self.assertEqual(visual_len("ℹ"), 1)
        # With VS16, they become 2-wide (emoji presentation)
        self.assertEqual(visual_len("✔\uFE0F"), 2)
        self.assertEqual(visual_len("⚠\uFE0F"), 2)
        # Box-drawing characters: 1 cell normally, 2 in CJK mode
        from termrender.style import get_ambiguous_width
        expected_box = get_ambiguous_width()
        self.assertEqual(visual_len("├"), expected_box)
        self.assertEqual(visual_len("│"), expected_box)
        self.assertEqual(visual_len("─"), expected_box)

    def test_panel_border_alignment_with_markers(self):
        output = render(PANEL_TREE_INPUT, width=40, color=False)
        lines = output.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
        widths = [visual_len(line) for line in lines]
        for i, (line, w) in enumerate(zip(lines, widths)):
            self.assertEqual(
                w,
                40,
                f"Line {i} has visual width {w}, expected 40: {line!r}",
            )

    def test_nested_panel_corners_align_with_side_walls(self):
        # When a panel inside a column receives content wider than the column
        # allocation, both the side walls AND the top/bottom border glyphs
        # must extend to the same width. Otherwise the corner glyphs (┐ ┘)
        # land one column inside the side walls (│), producing a jagged box.
        from termrender.style import _char_width

        output = render(NESTED_PANEL_OVERFLOW_INPUT, width=80, color=False)
        lines = output.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]

        def visual_positions(line, glyphs):
            pos = 0
            found = []
            for ch in line:
                if ch == "\033":
                    continue
                if ch in glyphs:
                    found.append(pos)
                pos += _char_width(ch)
            return found

        # The outer panel's left wall is always at pos 0 and the right wall
        # at the rightmost glyph. The inner panel's right border is the
        # next-most-right border glyph in any row that contains both the
        # outer panel's walls and inner-panel content. Across all such rows
        # the inner panel's right border position must be constant.
        inner_right_positions = []
        for line in lines:
            glyphs = sorted(set(visual_positions(line, "┌┐└┘│")))
            # Skip rows that don't span the inner panel (e.g. outer-only).
            if len(glyphs) < 3:
                continue
            outer_right = glyphs[-1]
            # Inner panel's right border is whichever glyph sits just inside
            # the outer right wall — i.e. the next-rightmost.
            inner_right = glyphs[-2]
            # Ignore the inner panel's LEFT wall (which on bare side-wall
            # rows might appear as glyphs[1]) — we only care about the
            # right-side glyph adjacent to the outer right wall.
            if inner_right == glyphs[0]:
                continue
            inner_right_positions.append(inner_right)

        unique = set(inner_right_positions)
        self.assertEqual(
            len(unique),
            1,
            f"Inner panel right border drifts across rows: {sorted(unique)}",
        )


if __name__ == "__main__":
    unittest.main()
