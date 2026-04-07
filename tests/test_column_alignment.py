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


if __name__ == "__main__":
    unittest.main()
