import unittest
from datetime import datetime

from termrender import render
from termrender.renderers.mermaid_gantt import parse_gantt, render as render_gantt
from termrender.style import visual_len


class TestParseGantt(unittest.TestCase):

    def test_parses_title_and_dateformat(self):
        src = "gantt\n    title Release Plan\n    dateFormat YYYY-MM-DD\n    Task1 :2024-01-01, 5d"
        parsed = parse_gantt(src)
        self.assertEqual(parsed["title"], "Release Plan")

    def test_start_date_plus_duration(self):
        src = "gantt\n    dateFormat YYYY-MM-DD\n    Task1 :2024-01-01, 5d"
        parsed = parse_gantt(src)
        task = parsed["sections"][0]["tasks"][0]
        self.assertEqual(task["start"], datetime(2024, 1, 1))
        self.assertEqual(task["end"], datetime(2024, 1, 6))

    def test_two_explicit_dates(self):
        src = "gantt\n    dateFormat YYYY-MM-DD\n    Task1 :2024-01-01, 2024-01-10"
        parsed = parse_gantt(src)
        task = parsed["sections"][0]["tasks"][0]
        self.assertEqual(task["start"], datetime(2024, 1, 1))
        self.assertEqual(task["end"], datetime(2024, 1, 10))

    def test_after_dependency_chains_from_prior_task(self):
        src = (
            "gantt\n"
            "    dateFormat YYYY-MM-DD\n"
            "    Task1 :a1, 2024-01-01, 5d\n"
            "    Task2 :after a1, 3d\n"
        )
        parsed = parse_gantt(src)
        tasks = parsed["sections"][0]["tasks"]
        self.assertEqual(tasks[1]["start"], datetime(2024, 1, 6))
        self.assertEqual(tasks[1]["end"], datetime(2024, 1, 9))

    def test_sections_grouped(self):
        src = (
            "gantt\n"
            "    dateFormat YYYY-MM-DD\n"
            "    section Design\n"
            "    Spec :2024-01-01, 5d\n"
            "    section Build\n"
            "    Implement :2024-01-10, 5d\n"
        )
        parsed = parse_gantt(src)
        names = [s["name"] for s in parsed["sections"]]
        self.assertEqual(names, ["Design", "Build"])

    def test_status_tokens_ignored(self):
        src = "gantt\n    dateFormat YYYY-MM-DD\n    Task1 :done, crit, 2024-01-01, 5d"
        parsed = parse_gantt(src)
        task = parsed["sections"][0]["tasks"][0]
        self.assertEqual(task["start"], datetime(2024, 1, 1))

    def test_unresolvable_task_skipped_not_crashed(self):
        src = "gantt\n    dateFormat YYYY-MM-DD\n    NoAnchor :after nonexistent, 5d"
        parsed = parse_gantt(src)
        self.assertEqual(parsed["sections"], [])

    def test_excludes_and_axisformat_ignored(self):
        src = (
            "gantt\n"
            "    dateFormat YYYY-MM-DD\n"
            "    excludes weekends\n"
            "    axisFormat %m/%d\n"
            "    Task1 :2024-01-01, 5d\n"
        )
        parsed = parse_gantt(src)
        self.assertEqual(len(parsed["sections"][0]["tasks"]), 1)

    def test_garbage_line_does_not_crash(self):
        src = "gantt\n    dateFormat YYYY-MM-DD\n    this has no colon\n    Task1 :2024-01-01, 5d"
        parsed = parse_gantt(src)
        self.assertEqual(len(parsed["sections"][0]["tasks"]), 1)

    def test_custom_dateformat(self):
        src = "gantt\n    dateFormat DD/MM/YYYY\n    Task1 :01/02/2024, 5d"
        parsed = parse_gantt(src)
        task = parsed["sections"][0]["tasks"][0]
        self.assertEqual(task["start"], datetime(2024, 2, 1))


class TestRenderGantt(unittest.TestCase):

    def test_renders_bars_for_each_task(self):
        src = (
            "gantt\n"
            "    dateFormat YYYY-MM-DD\n"
            "    Task1 :2024-01-01, 5d\n"
            "    Task2 :2024-01-06, 5d\n"
        )
        lines = render_gantt(src, width=70)
        joined = "\n".join(lines)
        self.assertIn("Task1", joined)
        self.assertIn("Task2", joined)
        self.assertIn("█", joined)
        self.assertIn("░", joined)

    def test_section_headers_appear(self):
        src = (
            "gantt\n"
            "    dateFormat YYYY-MM-DD\n"
            "    section Design\n"
            "    Spec :2024-01-01, 5d\n"
        )
        lines = render_gantt(src, width=70)
        self.assertTrue(any("Design" in ln for ln in lines))

    def test_no_tasks_degrades_to_source(self):
        src = "gantt\n    title nothing here\n"
        lines = render_gantt(src, width=40)
        self.assertEqual(lines, src.splitlines())

    def test_no_ansi_when_monochrome(self):
        src = "gantt\n    dateFormat YYYY-MM-DD\n    Task1 :2024-01-01, 5d"
        lines = render_gantt(src, width=40)
        self.assertNotIn("\x1b[", "\n".join(lines))

    def test_full_pipeline_renders_gantt(self):
        src = (
            "```mermaid\n"
            "gantt\n"
            "    dateFormat YYYY-MM-DD\n"
            "    section Build\n"
            "    Implement :2024-01-01, 10d\n"
            "```"
        )
        out = render(src, width=60, color=False)
        self.assertIn("Build", out)
        self.assertIn("Implement", out)
        self.assertIn("█", out)

    def test_full_pipeline_widths_match(self):
        src = (
            "```mermaid\n"
            "gantt\n"
            "    dateFormat YYYY-MM-DD\n"
            "    Task1 :2024-01-01, 5d\n"
            "```"
        )
        out = render(src, width=55, color=False)
        for ln in out.split("\n"):
            if ln:
                self.assertEqual(visual_len(ln), 55)


if __name__ == "__main__":
    unittest.main()
