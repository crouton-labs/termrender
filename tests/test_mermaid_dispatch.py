import unittest
from unittest import mock

from termrender.renderers import mermaid


class TestMermaidDispatch(unittest.TestCase):
    """Routing tests for mermaid.py's first-line type dispatcher.

    These mock the per-type renderers/binary call so they verify *routing*
    only, independent of the actual rendering logic (covered by
    test_mermaid_pie.py, test_mermaid_gantt.py, test_mermaid_sequence.py,
    test_mermaid_mindmap.py, test_mermaid_journey.py, test_mermaid_timeline.py,
    and test_mermaid_compat.py).
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

    def test_sequence_routes_to_native_sequence_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_sequence.render_sequence",
            return_value=["SEQ"],
        ) as seq_mock, mock.patch(
            "termrender.renderers.mermaid._render_via_binary"
        ) as binary_mock:
            lines = mermaid.render_mermaid_lines("sequenceDiagram\n    A->>B: hi", 40)
            self.assertEqual(lines, ["SEQ"])
            seq_mock.assert_called_once()
            binary_mock.assert_not_called()

    def test_mindmap_routes_to_native_mindmap_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_mindmap.render", return_value=["MM"]
        ) as mm_mock, mock.patch(
            "termrender.renderers.mermaid._render_via_binary"
        ) as binary_mock:
            lines = mermaid.render_mermaid_lines("mindmap\n  root", 40)
            self.assertEqual(lines, ["MM"])
            mm_mock.assert_called_once()
            binary_mock.assert_not_called()

    def test_journey_routes_to_native_journey_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_journey.render", return_value=["J"]
        ) as journey_mock, mock.patch(
            "termrender.renderers.mermaid._render_via_binary"
        ) as binary_mock:
            lines = mermaid.render_mermaid_lines("journey\n    title My journey", 40)
            self.assertEqual(lines, ["J"])
            journey_mock.assert_called_once()
            binary_mock.assert_not_called()

    def test_timeline_routes_to_native_timeline_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_timeline.render", return_value=["T"]
        ) as timeline_mock, mock.patch(
            "termrender.renderers.mermaid._render_via_binary"
        ) as binary_mock:
            lines = mermaid.render_mermaid_lines("timeline\n    2024 : x", 40)
            self.assertEqual(lines, ["T"])
            timeline_mock.assert_called_once()
            binary_mock.assert_not_called()

    def test_unsupported_type_routes_to_binary_fallback(self):
        for source in (
            "classDiagram\n    Animal <|-- Duck",
            "stateDiagram-v2\n    [*] --> Idle",
            "erDiagram\n    A ||--o{ B : has",
        ):
            with mock.patch(
                "termrender.renderers.mermaid._render_via_binary", return_value="X"
            ) as binary_mock:
                mermaid.render_mermaid_lines(source, 40)
                binary_mock.assert_called_once()

    def test_prelude_comment_before_pie_routes_natively(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_pie.render", return_value=["PIE"]
        ) as pie_mock, mock.patch(
            "termrender.renderers.mermaid._render_via_binary"
        ) as binary_mock:
            src = '%% a leading comment\npie\n    "A" : 1'
            lines = mermaid.render_mermaid_lines(src, 40)
            self.assertEqual(lines, ["PIE"])
            pie_mock.assert_called_once()
            binary_mock.assert_not_called()

    def test_prelude_init_directive_before_sequence_routes_natively(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_sequence.render_sequence",
            return_value=["SEQ"],
        ) as seq_mock, mock.patch(
            "termrender.renderers.mermaid._render_via_binary"
        ) as binary_mock:
            src = '%%{init: {"theme": "dark"}}%%\nsequenceDiagram\n    A->>B: hi'
            lines = mermaid.render_mermaid_lines(src, 40)
            self.assertEqual(lines, ["SEQ"])
            seq_mock.assert_called_once()
            binary_mock.assert_not_called()

    def test_prelude_frontmatter_before_gantt_routes_natively(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_gantt.render", return_value=["GANTT"]
        ) as gantt_mock, mock.patch(
            "termrender.renderers.mermaid._render_via_binary"
        ) as binary_mock:
            src = "---\ntitle: my diagram\n---\ngantt\n    dateFormat YYYY-MM-DD"
            lines = mermaid.render_mermaid_lines(src, 40)
            self.assertEqual(lines, ["GANTT"])
            gantt_mock.assert_called_once()
            binary_mock.assert_not_called()

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

    def test_sequence_full_integration_renders_real_diagram(self):
        # No mocking: proves the wiring actually reaches render_sequence and
        # produces its real box-drawing output, not just that routing occurs.
        lines = mermaid.render_mermaid_lines(
            "sequenceDiagram\n    Alice->>Bob: hi\n", 60
        )
        joined = "\n".join(lines)
        self.assertIn("Alice", joined)
        self.assertIn("Bob", joined)
        self.assertIn("┌", joined)

    def test_mindmap_full_integration_renders_real_diagram(self):
        lines = mermaid.render_mermaid_lines("mindmap\n  root\n    Origins\n", 60)
        joined = "\n".join(lines)
        self.assertIn("Origins", joined)
        self.assertIn("└──", joined)

    def test_journey_full_integration_renders_real_diagram(self):
        lines = mermaid.render_mermaid_lines(
            "journey\n    section A\n    Task: 5: Me\n", 60
        )
        joined = "\n".join(lines)
        self.assertIn("Task", joined)
        self.assertIn("★", joined)

    def test_timeline_full_integration_renders_real_diagram(self):
        lines = mermaid.render_mermaid_lines("timeline\n    2024 : Launch\n", 60)
        joined = "\n".join(lines)
        self.assertIn("Launch", joined)
        self.assertIn("●", joined)

    def test_init_directive_does_not_leak_into_journey_output(self):
        # Regression: the dispatcher must pass prelude-stripped source to
        # the native journey renderer, not just use the prelude for sniffing.
        src = (
            '%%{init: {"theme": "dark"}}%%\n'
            "journey\n"
            "  title T\n"
            "  section S\n"
            "    Task: 4: Me\n"
        )
        joined = "\n".join(mermaid.render_mermaid_lines(src, 60))
        self.assertNotIn("init", joined)
        self.assertNotIn("theme", joined)
        self.assertNotIn("%%", joined)
        self.assertIn("Task", joined)

    def test_init_directive_does_not_leak_into_mindmap_output(self):
        src = '%%{init: {"theme": "dark"}}%%\nmindmap\n  root\n    Origins\n'
        joined = "\n".join(mermaid.render_mermaid_lines(src, 60))
        self.assertNotIn("init", joined)
        self.assertNotIn("%%", joined)
        self.assertIn("Origins", joined)

    def test_init_directive_does_not_leak_into_timeline_output(self):
        src = '%%{init: {"theme": "dark"}}%%\ntimeline\n    2024 : Launch\n'
        joined = "\n".join(mermaid.render_mermaid_lines(src, 60))
        self.assertNotIn("init", joined)
        self.assertNotIn("%%", joined)
        self.assertIn("Launch", joined)


if __name__ == "__main__":
    unittest.main()
