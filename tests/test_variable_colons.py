import unittest

from termrender.parser import parse, DirectiveError
from termrender.blocks import BlockType
from termrender import render


class TestVariableColons(unittest.TestCase):
    """Tests for variable colon counts (3+) in directive markers."""

    def test_basic_four_colon_directive(self):
        """::::panel parses correctly with 4 colons."""
        doc = parse("::::panel\ncontent\n::::")
        self.assertEqual(len(doc.children), 1)
        self.assertEqual(doc.children[0].type, BlockType.PANEL)

    def test_five_colon_directive(self):
        """:::::panel parses correctly with 5 colons."""
        doc = parse(":::::panel\ncontent\n:::::")
        self.assertEqual(len(doc.children), 1)
        self.assertEqual(doc.children[0].type, BlockType.PANEL)

    def test_mixed_nesting(self):
        """Outer ::::panel containing inner :::col — both parse correctly."""
        source = (
            "::::panel\n"
            ":::col\n"
            "hello\n"
            ":::\n"
            "::::"
        )
        doc = parse(source)
        self.assertEqual(len(doc.children), 1)
        panel = doc.children[0]
        self.assertEqual(panel.type, BlockType.PANEL)
        # The inner :::col should be parsed recursively
        col_children = [c for c in panel.children if c.type == BlockType.COL]
        self.assertEqual(len(col_children), 1)

    def test_closer_mismatch_raises_error(self):
        """::::panel closed by ::: raises DirectiveError."""
        source = "::::panel\ncontent\n:::"
        with self.assertRaises(DirectiveError) as ctx:
            parse(source)
        self.assertIn("::::panel", str(ctx.exception))
        self.assertIn("::::", str(ctx.exception))

    def test_self_closing_with_variable_colons(self):
        """::::divider{label="x"} works as self-closing."""
        doc = parse('::::divider{label="x"}')
        self.assertEqual(len(doc.children), 1)
        self.assertEqual(doc.children[0].type, BlockType.DIVIDER)
        self.assertEqual(doc.children[0].attrs.get("label"), "x")

    def test_self_closing_with_explicit_closer(self):
        """::::divider{label="x"} followed by :::: is fine."""
        doc = parse('::::divider{label="x"}\n::::')
        dividers = [c for c in doc.children if c.type == BlockType.DIVIDER]
        self.assertEqual(len(dividers), 1)

    def test_deep_nesting_different_colon_counts(self):
        """4+ levels each with different colon counts."""
        source = (
            "::::::panel{title=\"outer\"}\n"
            ":::::panel{title=\"mid\"}\n"
            "::::panel{title=\"inner\"}\n"
            ":::callout{type=\"info\"}\n"
            "deep content\n"
            ":::\n"
            "::::\n"
            ":::::\n"
            "::::::"
        )
        doc = parse(source)
        self.assertEqual(len(doc.children), 1)
        outer = doc.children[0]
        self.assertEqual(outer.type, BlockType.PANEL)
        self.assertEqual(outer.attrs.get("title"), "outer")

        # Drill down
        mid = [c for c in outer.children if c.type == BlockType.PANEL]
        self.assertEqual(len(mid), 1)
        self.assertEqual(mid[0].attrs.get("title"), "mid")

        inner = [c for c in mid[0].children if c.type == BlockType.PANEL]
        self.assertEqual(len(inner), 1)
        self.assertEqual(inner[0].attrs.get("title"), "inner")

        callout = [c for c in inner[0].children if c.type == BlockType.CALLOUT]
        self.assertEqual(len(callout), 1)

    def test_render_integration_four_colons(self):
        """::::panel renders identically to :::panel."""
        source_3 = ":::panel{title=\"Test\"}\ncontent\n:::"
        source_4 = "::::panel{title=\"Test\"}\ncontent\n::::"
        output_3 = render(source_3, width=60, color=False)
        output_4 = render(source_4, width=60, color=False)
        self.assertEqual(output_3, output_4)

    def test_three_colon_backward_compat(self):
        """Existing ::: syntax is fully backward compatible."""
        source = (
            ":::panel{title=\"Hello\"}\n"
            "Some **bold** text\n"
            ":::"
        )
        doc = parse(source)
        self.assertEqual(len(doc.children), 1)
        self.assertEqual(doc.children[0].type, BlockType.PANEL)
        self.assertEqual(doc.children[0].attrs.get("title"), "Hello")

    def test_four_colon_with_attrs(self):
        """::::panel{title="X" color="red"} parses attrs correctly."""
        doc = parse('::::panel{title="X" color="red"}\nbody\n::::')
        panel = doc.children[0]
        self.assertEqual(panel.attrs["title"], "X")
        self.assertEqual(panel.attrs["color"], "red")

    def test_stray_closer_different_colons(self):
        """Stray :::: closer with no open directive raises DirectiveError."""
        with self.assertRaises(DirectiveError) as ctx:
            parse("::::")
        self.assertIn("::::", str(ctx.exception))

    def test_mixed_nesting_columns(self):
        """Real-world pattern: ::::columns with :::col children."""
        source = (
            "::::columns\n"
            ":::col{width=\"50%\"}\n"
            "left side\n"
            ":::\n"
            ":::col{width=\"50%\"}\n"
            "right side\n"
            ":::\n"
            "::::"
        )
        doc = parse(source)
        self.assertEqual(len(doc.children), 1)
        columns = doc.children[0]
        self.assertEqual(columns.type, BlockType.COLUMNS)
        cols = [c for c in columns.children if c.type == BlockType.COL]
        self.assertEqual(len(cols), 2)


if __name__ == "__main__":
    unittest.main()
