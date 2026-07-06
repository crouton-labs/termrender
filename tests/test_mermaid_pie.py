import unittest

from termrender import render
from termrender.renderers.mermaid_pie import parse_pie, render as render_pie
from termrender.style import visual_len


class TestParsePie(unittest.TestCase):

    def test_parses_labels_and_values(self):
        src = 'pie\n    "Bugs" : 40\n    "Features" : 60'
        title, items = parse_pie(src)
        self.assertIsNone(title)
        self.assertEqual(items, [
            {"label": "Bugs", "value": 40.0},
            {"label": "Features", "value": 60.0},
        ])

    def test_parses_title(self):
        src = "pie\n    title Key Findings\n"
        title, items = parse_pie(src)
        self.assertEqual(title, "Key Findings")

    def test_show_data_flag_ignored(self):
        src = 'pie showData\n    "A" : 1\n    "B" : 2'
        title, items = parse_pie(src)
        self.assertEqual(len(items), 2)

    def test_float_values(self):
        src = 'pie\n    "A" : 12.5\n    "B" : 87.5'
        _, items = parse_pie(src)
        self.assertEqual(items[0]["value"], 12.5)

    def test_invalid_line_degrades_whole_diagram(self):
        src = 'pie\n    this is not a data line\n    "A" : 5'
        title, items = parse_pie(src)
        self.assertIsNone(title)
        self.assertEqual(items, [])

    def test_comment_lines_ignored(self):
        src = 'pie\n    %% a note\n    "A" : 5\n    "B" : 5'
        _, items = parse_pie(src)
        self.assertEqual(len(items), 2)

    def test_acc_title_and_descr_ignored(self):
        src = (
            'pie\n'
            '    accTitle: My accessible title\n'
            '    accDescr: My accessible description\n'
            '    "A" : 5\n'
        )
        _, items = parse_pie(src)
        self.assertEqual(len(items), 1)

    def test_single_quoted_label(self):
        src = "pie\n    'Bugs' : 40\n    'Features' : 60"
        _, items = parse_pie(src)
        self.assertEqual(items, [
            {"label": "Bugs", "value": 40.0},
            {"label": "Features", "value": 60.0},
        ])

    def test_escaped_quotes_in_double_quoted_label(self):
        src = 'pie\n    "Say \\"hi\\"" : 5\n'
        _, items = parse_pie(src)
        self.assertEqual(items, [{"label": 'Say "hi"', "value": 5.0}])

    def test_negative_value_degrades_whole_diagram(self):
        src = 'pie\n    "A" : -5\n    "B" : 10'
        title, items = parse_pie(src)
        self.assertIsNone(title)
        self.assertEqual(items, [])

    def test_huge_numeric_value_degrades_whole_diagram(self):
        src = 'pie\n    "A" : ' + "9" * 400 + "\n"
        _, items = parse_pie(src)
        self.assertEqual(items, [])

    def test_invalid_header_tail_degrades_whole_diagram(self):
        src = 'pie bogus\n    "A" : 1\n'
        title, items = parse_pie(src)
        self.assertIsNone(title)
        self.assertEqual(items, [])

    def test_empty_pie_yields_no_items(self):
        _, items = parse_pie("pie\n")
        self.assertEqual(items, [])

    def test_title_inline_on_header_line(self):
        title, items = parse_pie('pie title Pets\n  "Dogs": 42\n')
        self.assertEqual(title, "Pets")
        self.assertEqual(items, [{"label": "Dogs", "value": 42.0}])

    def test_title_inline_after_showdata(self):
        title, _ = parse_pie('pie showData title Pets\n  "Dogs": 1\n')
        self.assertEqual(title, "Pets")


class TestRenderPie(unittest.TestCase):

    def test_renders_bars_with_percentages(self):
        src = 'pie\n    "Bugs" : 40\n    "Features" : 60'
        lines = render_pie(src, width=60)
        joined = "\n".join(lines)
        self.assertIn("Bugs", joined)
        self.assertIn("Features", joined)
        self.assertIn("40.0%", joined)
        self.assertIn("60.0%", joined)
        self.assertIn("█", joined)

    def test_largest_value_gets_full_bar(self):
        src = 'pie\n    "A" : 100\n    "B" : 50'
        lines = render_pie(src, width=60)
        self.assertIn("█" * 10, lines[0])  # line for A should be mostly full

    def test_title_rendered_above_bars(self):
        src = 'pie\n    title My Title\n    "A" : 1'
        lines = render_pie(src, width=40)
        self.assertIn("My Title", lines[0])

    def test_no_data_degrades_to_source(self):
        src = "pie\n"
        lines = render_pie(src, width=40)
        self.assertEqual(lines, ["pie"])

    def test_invalid_line_degrades_to_source(self):
        src = 'pie\n    bad\n    "A" : 5'
        lines = render_pie(src, width=40)
        self.assertEqual(lines, src.splitlines())

    def test_negative_value_degrades_to_source(self):
        src = 'pie\n    "A" : -5\n    "B" : 10'
        lines = render_pie(src, width=40)
        self.assertEqual(lines, src.splitlines())

    def test_huge_numeric_value_degrades_to_source(self):
        src = 'pie\n    "A" : ' + "9" * 400
        lines = render_pie(src, width=40)
        self.assertEqual(lines, src.splitlines())

    def test_no_ansi_when_monochrome(self):
        src = 'pie\n    "A" : 1\n    "B" : 2'
        lines = render_pie(src, width=40)
        self.assertNotIn("\x1b[", "\n".join(lines))

    def test_full_pipeline_renders_pie(self):
        src = '```mermaid\npie\n    title Findings\n    "Bugs" : 40\n    "Docs" : 60\n```'
        out = render(src, width=60, color=False)
        self.assertIn("Findings", out)
        self.assertIn("Bugs", out)
        self.assertIn("█", out)

    def test_full_pipeline_widths_match(self):
        src = '```mermaid\npie\n    "A" : 1\n    "B" : 2\n```'
        out = render(src, width=50, color=False)
        for ln in out.split("\n"):
            if ln:
                self.assertEqual(visual_len(ln), 50)


if __name__ == "__main__":
    unittest.main()

