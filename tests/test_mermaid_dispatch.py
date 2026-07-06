import unittest
from unittest import mock

from termrender.renderers import mermaid


class TestMermaidDispatch(unittest.TestCase):
    """Routing tests for mermaid.py's first-line type dispatcher.

    These mock the per-type renderers/binary call so they verify *routing*
    only, independent of the actual rendering logic (covered by
    test_mermaid_pie.py, test_mermaid_gantt.py, and test_mermaid_compat.py).
    """

    def test_pie_routes_to_native_pie_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_pie.render", return_value=["PIE"]
        ) as pie_mock, mock.patch(
            "termrender.renderers.mermaid._render_via_binary"
        ) as binary_mock:
            lines = mermaid.render_mermaid_lines('pie\n    "A" : 1', 40)
            self.assertEqual(lines, ["PIE"])
            pie_mock.assert_called_once()
            binary_mock.assert_not_called()

    def test_gantt_routes_to_native_gantt_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_gantt.render", return_value=["GANTT"]
        ) as gantt_mock, mock.patch(
            "termrender.renderers.mermaid._render_via_binary"
        ) as binary_mock:
            lines = mermaid.render_mermaid_lines("gantt\n    dateFormat YYYY-MM-DD", 40)
            self.assertEqual(lines, ["GANTT"])
            gantt_mock.assert_called_once()
            binary_mock.assert_not_called()

    def test_graph_routes_to_binary_fallback(self):
        with mock.patch(
            "termrender.renderers.mermaid._render_via_binary", return_value="RENDERED"
        ) as binary_mock:
            lines = mermaid.render_mermaid_lines("graph LR\nA-->B", 40)
            self.assertEqual(lines, ["RENDERED"])
            binary_mock.assert_called_once()

    def test_flowchart_routes_to_binary_fallback(self):
        with mock.patch(
            "termrender.renderers.mermaid._render_via_binary", return_value="RENDERED"
        ) as binary_mock:
            mermaid.render_mermaid_lines("flowchart TD\nA-->B", 40)
            binary_mock.assert_called_once()

    def test_sequence_routes_to_binary_fallback(self):
        with mock.patch(
            "termrender.renderers.mermaid._render_via_binary", return_value="RENDERED"
        ) as binary_mock:
            mermaid.render_mermaid_lines("sequenceDiagram\n    A->>B: hi", 40)
            binary_mock.assert_called_once()

    def test_unsupported_type_routes_to_binary_fallback(self):
        for source in (
            "classDiagram\n    Animal <|-- Duck",
            "stateDiagram-v2\n    [*] --> Idle",
            "erDiagram\n    A ||--o{ B : has",
            "journey\n    title My journey",
            "mindmap\n  root",
        ):
            with mock.patch(
                "termrender.renderers.mermaid._render_via_binary", return_value="X"
            ) as binary_mock:
                mermaid.render_mermaid_lines(source, 40)
                binary_mock.assert_called_once()

    def test_type_sniff_is_case_insensitive(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_pie.render", return_value=["PIE"]
        ) as pie_mock:
            mermaid.render_mermaid_lines('PIE\n    "A" : 1', 40)
            pie_mock.assert_called_once()

    def test_type_sniff_skips_leading_blank_lines(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_gantt.render", return_value=["G"]
        ) as gantt_mock:
            mermaid.render_mermaid_lines("\n\n   gantt\n    dateFormat YYYY-MM-DD", 40)
            gantt_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
