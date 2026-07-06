"""Tests for directive option lines and the colon-fence mermaid directive."""

import unittest

from termrender.blocks import BlockType
from termrender.parser import parse, _strip_options


class TestMermaidDirective(unittest.TestCase):
    """:::mermaid and ```mermaid fences both produce mermaid diagrams."""

    def test_basic_mermaid_directive(self):
        """:::mermaid\ngraph LR\nA-->B\n::: → BlockType.MERMAID"""
        doc = parse(":::mermaid\ngraph LR\nA-->B\n:::")
        self.assertEqual(len(doc.children), 1)
        block = doc.children[0]
        self.assertEqual(block.type, BlockType.MERMAID)
        self.assertIn("graph LR", block.attrs["source"])

    def test_mermaid_with_option_lines(self):
        """Option lines at the top of a mermaid body set attrs, not source."""
        doc = parse(":::mermaid\n:title: Flow\ngraph LR\nA-->B\n:::")
        block = doc.children[0]
        self.assertEqual(block.type, BlockType.MERMAID)
        self.assertEqual(block.attrs.get("title"), "Flow")
        self.assertIn("graph LR", block.attrs["source"])
        self.assertNotIn(":title:", block.attrs["source"])

    def test_backtick_mermaid_is_mermaid_block(self):
        """```mermaid fences route through the mermaid renderer, same as :::mermaid."""
        doc = parse("```mermaid\ngraph LR\nA-->B\n```")
        block = doc.children[0]
        self.assertEqual(block.type, BlockType.MERMAID)
        self.assertIn("graph LR", block.attrs["source"])

    def test_backtick_directive_is_plain_code_block(self):
        """```{panel} is no longer a directive — it renders as a code block."""
        doc = parse("```{panel}\ncontent\n```")
        block = doc.children[0]
        self.assertEqual(block.type, BlockType.CODE)
        self.assertEqual(block.attrs.get("lang"), "{panel}")


class TestDirectiveOptionLines(unittest.TestCase):
    """Directive option lines (`:key: value` at top of body)."""

    def test_colon_directive_with_options(self):
        """:::panel\n:title: Hi\n:color: blue\ncontent\n::: → attrs have title and color"""
        doc = parse(":::panel\n:title: Hi\n:color: blue\ncontent\n:::")
        panel = doc.children[0]
        self.assertEqual(panel.attrs["title"], "Hi")
        self.assertEqual(panel.attrs["color"], "blue")

    def test_options_dont_override_inline_attrs(self):
        """:::panel{title="Inline"}\n:title: Option\n::: → title is "Inline" """
        doc = parse(':::panel{title="Inline"}\n:title: Option\n:::')
        panel = doc.children[0]
        self.assertEqual(panel.attrs["title"], "Inline")

    def test_body_after_options_preserved(self):
        """Body content after option lines is preserved correctly."""
        doc = parse(":::panel\n:title: Hi\nHello world\n:::")
        panel = doc.children[0]
        self.assertEqual(panel.attrs["title"], "Hi")
        # Body should have been parsed and contain a paragraph with "Hello world"
        self.assertTrue(len(panel.children) > 0)

    def test_non_option_lines_not_eaten(self):
        """:not-an-option without trailing colon-space should not be eaten."""
        doc = parse(":::panel\n:not-an-option\ncontent\n:::")
        panel = doc.children[0]
        # ":not-an-option" doesn't match `:key: value` pattern, so no options
        self.assertNotIn("not-an-option", panel.attrs)


class TestStripOptions(unittest.TestCase):
    """Unit tests for _strip_options."""

    def test_empty_body(self):
        opts, body = _strip_options("")
        self.assertEqual(opts, {})
        self.assertEqual(body, "")

    def test_no_options(self):
        opts, body = _strip_options("just content\nmore content")
        self.assertEqual(opts, {})
        self.assertEqual(body, "just content\nmore content")

    def test_options_with_blank_lines(self):
        opts, body = _strip_options(":title: Hi\n\n:color: blue\ncontent")
        self.assertEqual(opts, {"title": "Hi", "color": "blue"})
        self.assertEqual(body, "content")

    def test_option_key_with_hyphens(self):
        opts, body = _strip_options(":my-key: value\ncontent")
        self.assertEqual(opts, {"my-key": "value"})
        self.assertEqual(body, "content")


if __name__ == "__main__":
    unittest.main()
