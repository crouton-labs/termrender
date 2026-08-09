import unittest
from unittest import mock

from termrender.renderers import mermaid
from termrender.renderers.mermaid_degradation import raw_echo


class TestMermaidDispatch(unittest.TestCase):
    """Routing tests for mermaid.py's first-line type dispatcher.

    These mock the per-type renderers so they verify *routing* only,
    independent of the actual rendering logic (covered by
    test_mermaid_pie.py, test_mermaid_gantt.py, test_mermaid_sequence.py,
    test_mermaid_mindmap.py, test_mermaid_journey.py, test_mermaid_timeline.py,
    test_mermaid_flow.py, test_mermaid_class.py, test_mermaid_state.py, and
    test_mermaid_er.py).
    """

    def test_pie_routes_to_native_pie_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_pie.render", return_value=["PIE"]
        ) as pie_mock:
            lines = mermaid.render_mermaid_lines('pie\n    "A" : 1', 40)
            self.assertEqual(lines, ["PIE"])
            pie_mock.assert_called_once()

    def test_gantt_routes_to_native_gantt_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_gantt.render", return_value=["GANTT"]
        ) as gantt_mock:
            lines = mermaid.render_mermaid_lines("gantt\n    dateFormat YYYY-MM-DD", 40)
            self.assertEqual(lines, ["GANTT"])
            gantt_mock.assert_called_once()

    def test_graph_routes_to_native_flowchart_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_flow.render_flowchart",
            return_value=["FLOW"],
        ) as flow_mock:
            lines = mermaid.render_mermaid_lines("graph LR\nA-->B", 40)
            self.assertEqual(lines, ["FLOW"])
            flow_mock.assert_called_once()

    def test_flowchart_routes_to_native_flowchart_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_flow.render_flowchart",
            return_value=["FLOW"],
        ) as flow_mock:
            mermaid.render_mermaid_lines("flowchart TD\nA-->B", 40)
            flow_mock.assert_called_once()

    def test_class_diagram_routes_to_native_class_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_class.render_class",
            return_value=["CLASS"],
        ) as class_mock:
            lines = mermaid.render_mermaid_lines("classDiagram\n    Animal <|-- Duck", 40)
            self.assertEqual(lines, ["CLASS"])
            class_mock.assert_called_once()

    def test_state_diagram_routes_to_native_state_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_state.render_state",
            return_value=["STATE"],
        ) as state_mock:
            lines = mermaid.render_mermaid_lines("stateDiagram-v2\n    [*] --> Idle", 40)
            self.assertEqual(lines, ["STATE"])
            state_mock.assert_called_once()

    def test_er_diagram_routes_to_native_er_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_er.render_er", return_value=["ER"]
        ) as er_mock:
            lines = mermaid.render_mermaid_lines("erDiagram\n    A ||--o{ B : has", 40)
            self.assertEqual(lines, ["ER"])
            er_mock.assert_called_once()

    def test_gitgraph_routes_to_native_gitgraph_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_gitgraph.render", return_value=["GIT"]
        ) as gitgraph_mock:
            lines = mermaid.render_mermaid_lines('gitGraph\n    commit id: "first"', 40)
            self.assertEqual(lines, ["GIT"])
            gitgraph_mock.assert_called_once()

    def test_sequence_routes_to_native_sequence_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_sequence.render_sequence",
            return_value=["SEQ"],
        ) as seq_mock:
            lines = mermaid.render_mermaid_lines("sequenceDiagram\n    A->>B: hi", 40)
            self.assertEqual(lines, ["SEQ"])
            seq_mock.assert_called_once()

    def test_mindmap_routes_to_native_mindmap_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_mindmap.render", return_value=["MM"]
        ) as mm_mock:
            lines = mermaid.render_mermaid_lines("mindmap\n  root", 40)
            self.assertEqual(lines, ["MM"])
            mm_mock.assert_called_once()

    def test_journey_routes_to_native_journey_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_journey.render", return_value=["J"]
        ) as journey_mock:
            lines = mermaid.render_mermaid_lines("journey\n    title My journey", 40)
            self.assertEqual(lines, ["J"])
            journey_mock.assert_called_once()

    def test_timeline_routes_to_native_timeline_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_timeline.render", return_value=["T"]
        ) as timeline_mock:
            lines = mermaid.render_mermaid_lines("timeline\n    2024 : x", 40)
            self.assertEqual(lines, ["T"])
            timeline_mock.assert_called_once()

    def test_exotic_type_degrades_to_raw_echo(self):
        src = "sankey-beta\n\nA,B,10\nB,C,5"
        lines = mermaid.render_mermaid_lines(src, 40)
        self.assertEqual(lines, src.splitlines())

    def test_unsupported_families_remain_source_only_raw_echoes(self):
        for src in (
            "sankey-beta\nA,B,10",
            "C4Context\n    Person(a, \"A\")",
            "block-beta\n    columns 1\n    a",
            "packet-beta\n    0-15: \"data\"",
            "kanban\n    Todo\n    Task1",
        ):
            lines = mermaid.render_mermaid_lines(src, 40)
            self.assertEqual(lines, raw_echo(src))
            self.assertFalse(lines[0].startswith("mermaid error: "))

    def test_exotic_type_raw_echo_contains_no_box_glyphs(self):
        # Pinning the degradation contract: the crouter viewer keys on the
        # *absence* of box-drawing glyphs to keep the original code fence,
        # so an exotic type's echo must never contain one — even one
        # present verbatim in the source itself.
        for src in (
            "sankey-beta\nA,B,10",
            "C4Context\n    Person(a, \"A\")",
            "block-beta\n    columns 1\n    a",
            "packet-beta\n    0-15: \"data\"",
            "kanban\n    Todo\n    Task1",
            "totally-unknown-type\nsome line with a literal ┌ box glyph",
        ):
            lines = mermaid.render_mermaid_lines(src, 40)
            joined = "\n".join(lines)
            for cp in range(0x2500, 0x2600):
                self.assertNotIn(chr(cp), joined)

    def test_unknown_type_routes_to_raw_echo_not_any_native_renderer(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_flow.render_flowchart"
        ) as flow_mock, mock.patch(
            "termrender.renderers.mermaid.mermaid_class.render_class"
        ) as class_mock, mock.patch(
            "termrender.renderers.mermaid.mermaid_state.render_state"
        ) as state_mock, mock.patch(
            "termrender.renderers.mermaid.mermaid_er.render_er"
        ) as er_mock:
            mermaid.render_mermaid_lines("sankey-beta\nA,B,10", 40)
            flow_mock.assert_not_called()
            class_mock.assert_not_called()
            state_mock.assert_not_called()
            er_mock.assert_not_called()

    def test_flowchart_full_integration_renders_real_diagram(self):
        # No mocking: proves the wiring actually reaches render_flowchart and
        # produces its real box-drawing output, not just that routing occurs.
        lines = mermaid.render_mermaid_lines("flowchart LR\n    A[Start] --> B[End]", 60)
        joined = "\n".join(lines)
        self.assertIn("Start", joined)
        self.assertIn("End", joined)
        self.assertIn("┌", joined)

    def test_class_diagram_full_integration_renders_real_diagram(self):
        lines = mermaid.render_mermaid_lines("classDiagram\n    class Animal", 60)
        joined = "\n".join(lines)
        self.assertIn("Animal", joined)
        self.assertIn("┌", joined)

    def test_state_diagram_full_integration_renders_real_diagram(self):
        lines = mermaid.render_mermaid_lines("stateDiagram-v2\n    [*] --> Idle", 60)
        joined = "\n".join(lines)
        self.assertIn("Idle", joined)
        self.assertIn("┌", joined)

    def test_er_diagram_full_integration_renders_real_diagram(self):
        lines = mermaid.render_mermaid_lines("erDiagram\n    CUSTOMER ||--o{ ORDER : places", 60)
        joined = "\n".join(lines)
        self.assertIn("CUSTOMER", joined)
        self.assertIn("ORDER", joined)
        self.assertIn("┌", joined)

    def test_prelude_comment_before_pie_routes_natively(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_pie.render", return_value=["PIE"]
        ) as pie_mock:
            src = '%% a leading comment\npie\n    "A" : 1'
            lines = mermaid.render_mermaid_lines(src, 40)
            self.assertEqual(lines, ["PIE"])
            pie_mock.assert_called_once()

    def test_prelude_init_directive_before_sequence_routes_natively(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_sequence.render_sequence",
            return_value=["SEQ"],
        ) as seq_mock:
            src = '%%{init: {"theme": "dark"}}%%\nsequenceDiagram\n    A->>B: hi'
            lines = mermaid.render_mermaid_lines(src, 40)
            self.assertEqual(lines, ["SEQ"])
            seq_mock.assert_called_once()

    def test_prelude_frontmatter_before_gantt_routes_natively(self):
        with mock.patch(
            "termrender.renderers.mermaid.mermaid_gantt.render", return_value=["GANTT"]
        ) as gantt_mock:
            src = "---\ntitle: my diagram\n---\ngantt\n    dateFormat YYYY-MM-DD"
            lines = mermaid.render_mermaid_lines(src, 40)
            self.assertEqual(lines, ["GANTT"])
            gantt_mock.assert_called_once()

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
