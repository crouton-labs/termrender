import unittest

from termrender import render
from termrender.parser import parse
from termrender.blocks import BlockType
from termrender.style import visual_len


class TestTasklist(unittest.TestCase):

    def test_plain_markdown_checkboxes_become_tasklist(self):
        src = "- [x] done\n- [ ] todo\n"
        doc = parse(src)
        list_block = doc.children[0]
        self.assertEqual(list_block.type, BlockType.LIST)
        self.assertTrue(list_block.attrs.get("tasklist"))
        items = list_block.children
        self.assertEqual(items[0].attrs.get("checked"), True)
        self.assertEqual(items[1].attrs.get("checked"), False)

    def test_pending_marker(self):
        src = "- [!] in progress\n"
        doc = parse(src)
        items = doc.children[0].children
        self.assertTrue(items[0].attrs.get("pending"))

    def test_renders_checkboxes(self):
        src = "- [x] done\n- [ ] todo\n- [!] in progress\n"
        output = render(src, width=40, color=False)
        self.assertIn("●", output)  # checked
        self.assertIn("○", output)  # unchecked
        self.assertIn("◐", output)  # pending

    def test_tasklist_directive_alias(self):
        src = ":::tasklist\n- write parser\n- write tests\n:::"
        doc = parse(src)
        list_block = doc.children[0]
        self.assertEqual(list_block.type, BlockType.LIST)
        self.assertTrue(list_block.attrs.get("tasklist"))
        # Items without explicit markers default to unchecked
        for item in list_block.children:
            self.assertEqual(item.attrs.get("checked"), False)

    def test_tasklist_directive_renders_unchecked(self):
        src = ":::tasklist\n- foo\n- bar\n:::"
        output = render(src, width=40, color=False)
        # Both items should render as unchecked
        self.assertEqual(output.count("○"), 2)

    def test_visual_widths_match(self):
        src = "- [x] done\n- [ ] todo\n"
        output = render(src, width=40, color=False)
        for ln in output.split("\n"):
            if ln:
                self.assertEqual(visual_len(ln), 40)

    def test_marker_stripped_from_text(self):
        src = "- [x] done\n"
        doc = parse(src)
        item = doc.children[0].children[0]
        self.assertEqual(item.text[0].text, "done")

    def test_color_used_for_checked(self):
        src = "- [x] done\n- [ ] todo\n"
        out = render(src, width=40, color=True)
        self.assertIn("\x1b[32m", out)  # green for checked

    def test_mixed_list_does_not_become_tasklist(self):
        # A list with no markers stays a regular bulleted list
        src = "- foo\n- bar\n"
        doc = parse(src)
        self.assertFalse(doc.children[0].attrs.get("tasklist"))

    def test_partial_markers_promote_whole_list(self):
        # If at least one item has a marker, the whole list becomes a tasklist
        src = "- [x] done\n- without marker\n"
        doc = parse(src)
        self.assertTrue(doc.children[0].attrs.get("tasklist"))


if __name__ == "__main__":
    unittest.main()
