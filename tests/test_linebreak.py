import unittest

from termrender import render
from termrender.style import visual_len, wrap_text


class TestWrapTextLinebreak(unittest.TestCase):
    def test_single_newline_splits(self):
        self.assertEqual(wrap_text("a\nb", 10), ["a", "b"])

    def test_newline_with_wrap(self):
        # Each segment wraps independently.
        self.assertEqual(wrap_text("aa bb\ncc dd", 3), ["aa", "bb", "cc", "dd"])

    def test_leading_newline(self):
        self.assertEqual(wrap_text("\nfoo", 10), ["", "foo"])

    def test_trailing_newline(self):
        self.assertEqual(wrap_text("foo\n", 10), ["foo", ""])

    def test_consecutive_newlines(self):
        self.assertEqual(wrap_text("a\n\nb", 10), ["a", "", "b"])

    def test_plain_wrap_unchanged(self):
        self.assertEqual(wrap_text("hello world foo bar", 10),
                         ["hello", "world foo", "bar"])


class TestLinebreakRendering(unittest.TestCase):
    def test_hard_break_in_paragraph_pads_both_lines(self):
        # Two trailing spaces = markdown hard line break.
        output = render("line one  \nline two", width=40, color=False)
        lines = output.split("\n")
        if lines and lines[-1] == "":
            lines = lines[:-1]
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertEqual(visual_len(line), 40)

    def test_hard_break_in_panel_aligns_borders(self):
        src = ':::panel{title="t"}\nline one  \nline two\n:::'
        output = render(src, width=30, color=False)
        lines = [ln for ln in output.split("\n") if ln]
        # Panel: top border, line 1, line 2, bottom border = 4 lines.
        self.assertEqual(len(lines), 4)
        widths = {visual_len(ln) for ln in lines}
        self.assertEqual(widths, {30})
        # Interior lines begin and end with the side border glyph.
        for interior in lines[1:-1]:
            self.assertTrue(interior.startswith("│"))
            self.assertTrue(interior.rstrip().endswith("│"))

    def test_hard_break_in_columns_preserves_row_width(self):
        src = (
            "::::columns\n:::col\nleft one  \nleft two\n:::\n"
            ":::col\nright\n:::\n::::"
        )
        output = render(src, width=40, color=False)
        lines = [ln for ln in output.split("\n") if ln]
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertEqual(visual_len(line), 40)

    def test_hard_break_preserves_inline_style(self):
        # Bold span followed by hard break and plain text — bold must not
        # bleed onto line two.
        output = render("**bold**  \nplain", width=30, color=True)
        lines = output.rstrip("\n").split("\n")
        self.assertEqual(len(lines), 2)
        self.assertIn("\x1b[1m", lines[0])
        self.assertNotIn("\x1b[1m", lines[1])


if __name__ == "__main__":
    unittest.main()
