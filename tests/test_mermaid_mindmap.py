import unittest

from termrender import render
from termrender.renderers.mermaid_mindmap import parse_mindmap, render as render_mindmap
from termrender.style import visual_len


class TestParseMindmap(unittest.TestCase):

    def test_header_line_dropped(self):
        out = parse_mindmap("mindmap\n  root\n")
        self.assertNotIn("mindmap", out.lower())
        self.assertIn("root", out)

    def test_plain_labels_pass_through(self):
        out = parse_mindmap("mindmap\n  root\n    Origins\n")
        self.assertEqual(out, "  root\n    Origins")

    def test_circle_shape_stripped(self):
        out = parse_mindmap("mindmap\n  root((mindmap))\n")
        self.assertEqual(out, "  mindmap")

    def test_square_shape_stripped(self):
        out = parse_mindmap("mindmap\n  a[Square]\n")
        self.assertEqual(out, "  Square")

    def test_hexagon_shape_stripped(self):
        out = parse_mindmap("mindmap\n  a{{Hex}}\n")
        self.assertEqual(out, "  Hex")

    def test_rounded_shape_stripped(self):
        out = parse_mindmap("mindmap\n  a(Rounded)\n")
        self.assertEqual(out, "  Rounded")

    def test_bang_shape_stripped(self):
        out = parse_mindmap("mindmap\n  a))Bang((\n")
        self.assertEqual(out, "  Bang")

    def test_cloud_shape_stripped(self):
        out = parse_mindmap("mindmap\n  a)Cloud(\n")
        self.assertEqual(out, "  Cloud")

    def test_icon_line_dropped(self):
        out = parse_mindmap("mindmap\n  root\n    ::icon(fa fa-book)\n    Origins\n")
        self.assertNotIn("icon", out)
        self.assertIn("Origins", out)

    def test_class_line_dropped(self):
        out = parse_mindmap("mindmap\n  root\n    :::urgent\n    Origins\n")
        self.assertNotIn(":::", out)
        self.assertIn("Origins", out)

    def test_br_tags_flattened(self):
        out = parse_mindmap("mindmap\n  root\n    Origins<br/>text\n")
        self.assertIn("Origins / text", out)

    def test_blank_lines_skipped(self):
        out = parse_mindmap("mindmap\n  root\n\n    Origins\n")
        self.assertNotIn("", out.splitlines())

    def test_indentation_preserved(self):
        out = parse_mindmap("mindmap\n  root\n    Origins\n      Deep\n")
        lines = out.splitlines()
        self.assertEqual(lines, ["  root", "    Origins", "      Deep"])

    def test_only_header_yields_empty(self):
        self.assertEqual(parse_mindmap("mindmap\n"), "")

    def test_indented_comment_line_dropped(self):
        out = parse_mindmap("mindmap\n  root\n    %% a comment\n    Origins\n")
        self.assertNotIn("comment", out)
        self.assertNotIn("%%", out)
        self.assertIn("Origins", out)

    def test_init_directive_before_header_dropped(self):
        out = parse_mindmap('%%{init: {"theme": "dark"}}%%\nmindmap\n  root\n    Origins\n')
        self.assertNotIn("init", out)
        self.assertNotIn("%%", out)
        self.assertIn("Origins", out)


class TestRenderMindmap(unittest.TestCase):

    def test_golden_small_tree(self):
        src = "mindmap\n  root((mindmap))\n    Origins\n      Long history\n    Research\n"
        lines = render_mindmap(src, width=30)
        self.assertEqual(
            lines,
            [
                "\u2514\u2500\u2500 mindmap                   ",
                "    \u251c\u2500\u2500 Origins               ",
                "    \u2502   \u2514\u2500\u2500 Long history      ",
                "    \u2514\u2500\u2500 Research              ",
            ],
        )

    def test_widths_match(self):
        src = "mindmap\n  root\n    A\n    B\n"
        for line in render_mindmap(src, width=25):
            self.assertEqual(visual_len(line), 25)

    def test_no_survivable_content_degrades_to_source(self):
        src = "mindmap\n"
        self.assertEqual(render_mindmap(src, width=40), src.splitlines())

    def test_no_ansi_when_monochrome(self):
        src = "mindmap\n  root\n    Origins\n"
        lines = render_mindmap(src, width=40)
        self.assertNotIn("\x1b[", "\n".join(lines))

    def test_full_pipeline_renders_mindmap(self):
        src = "```mermaid\nmindmap\n  root((mindmap))\n    Origins\n    Research\n```"
        out = render(src, width=40, color=False)
        self.assertIn("mindmap", out)
        self.assertIn("Origins", out)
        self.assertIn("\u251c\u2500\u2500", out)

    def test_full_pipeline_widths_match(self):
        src = "```mermaid\nmindmap\n  root\n    A\n```"
        out = render(src, width=45, color=False)
        for ln in out.split("\n"):
            if ln:
                self.assertEqual(visual_len(ln), 45)

    def test_indented_comment_produces_no_fake_tree_node(self):
        # Regression: an indented %% comment line must not render as a
        # tree node.
        src = "mindmap\n  root\n    %% a comment\n    Origins\n"
        lines = render_mindmap(src, width=40)
        joined = "\n".join(lines)
        self.assertNotIn("comment", joined)
        self.assertNotIn("%%", joined)
        self.assertIn("Origins", joined)


if __name__ == "__main__":
    unittest.main()
