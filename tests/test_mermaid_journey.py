import unittest

from termrender import render
from termrender.renderers.mermaid_journey import parse_journey, render as render_journey
from termrender.style import visual_len


class TestParseJourney(unittest.TestCase):

    def test_parses_title(self):
        parsed = parse_journey("journey\n    title My working day\n    section A\n    T: 5: Me\n")
        self.assertEqual(parsed["title"], "My working day")

    def test_parses_section_names(self):
        parsed = parse_journey(
            "journey\n"
            "    section Go to work\n"
            "    Make tea: 5: Me\n"
            "    section Go home\n"
            "    Sit down: 5: Me\n"
        )
        self.assertEqual([s["name"] for s in parsed["sections"]], ["Go to work", "Go home"])

    def test_parses_task_score_and_actors(self):
        parsed = parse_journey("journey\n    section A\n    Do work: 1: Me, Cat\n")
        task = parsed["sections"][0]["tasks"][0]
        self.assertEqual(task, {"name": "Do work", "score": 1, "actors": ["Me", "Cat"]})

    def test_task_with_no_actors(self):
        parsed = parse_journey("journey\n    section A\n    Solo task: 3\n")
        task = parsed["sections"][0]["tasks"][0]
        self.assertEqual(task["actors"], [])
        self.assertEqual(task["score"], 3)

    def test_task_with_no_score(self):
        parsed = parse_journey("journey\n    section A\n    Bare task\n")
        # No colon at all: unparseable, skipped rather than crashed.
        self.assertEqual(parsed["sections"], [])

    def test_non_numeric_score_tolerated(self):
        parsed = parse_journey("journey\n    section A\n    Task: high: Me\n")
        task = parsed["sections"][0]["tasks"][0]
        self.assertIsNone(task["score"])
        self.assertEqual(task["actors"], ["Me"])

    def test_task_before_any_section_lands_in_unnamed_bucket(self):
        parsed = parse_journey("journey\n    Loose task: 5: Me\n")
        self.assertEqual(len(parsed["sections"]), 1)
        self.assertIsNone(parsed["sections"][0]["name"])
        self.assertEqual(parsed["sections"][0]["tasks"][0]["name"], "Loose task")

    def test_empty_section_dropped(self):
        parsed = parse_journey(
            "journey\n    section Empty\n    section Full\n    T: 5: Me\n"
        )
        self.assertEqual([s["name"] for s in parsed["sections"]], ["Full"])

    def test_no_tasks_yields_no_sections(self):
        parsed = parse_journey("journey\n    title Empty Journey\n")
        self.assertEqual(parsed["sections"], [])


class TestRenderJourney(unittest.TestCase):

    def test_golden_small_journey(self):
        src = (
            "journey\n"
            "    title My working day\n"
            "    section Go to work\n"
            "      Make tea: 5: Me\n"
            "      Go upstairs: 3: Me\n"
        )
        lines = render_journey(src, width=40)
        self.assertEqual(
            lines,
            [
                "My working day                          ",
                "Go to work                              ",
                "\u251c\u2500\u2500 Make tea  \u2605\u2605\u2605\u2605\u2605  (Me)               ",
                "\u2514\u2500\u2500 Go upstairs  \u2605\u2605\u2605\u2606\u2606  (Me)            ",
            ],
        )

    def test_stars_reflect_score(self):
        src = "journey\n    section A\n    Full: 5: Me\n    Empty: 0: Me\n"
        lines = render_journey(src, width=50)
        joined = "\n".join(lines)
        self.assertIn("\u2605\u2605\u2605\u2605\u2605", joined)
        self.assertIn("\u2606\u2606\u2606\u2606\u2606", joined)

    def test_no_score_omits_stars(self):
        src = "journey\n    section A\n    Task: high\n"
        lines = render_journey(src, width=40)
        self.assertNotIn("\u2605", "\n".join(lines))

    def test_no_tasks_degrades_to_source(self):
        src = "journey\n    title nothing here\n"
        self.assertEqual(render_journey(src, width=40), src.splitlines())

    def test_no_ansi_when_monochrome(self):
        src = "journey\n    section A\n    T: 5: Me\n"
        lines = render_journey(src, width=40)
        self.assertNotIn("\x1b[", "\n".join(lines))

    def test_widths_match(self):
        src = "journey\n    title T\n    section A\n    Task one: 5: Me\n"
        for line in render_journey(src, width=45):
            self.assertEqual(visual_len(line), 45)

    def test_full_pipeline_renders_journey(self):
        src = (
            "```mermaid\njourney\n    section Go home\n    Sit down: 5: Me\n```"
        )
        out = render(src, width=40, color=False)
        self.assertIn("Go home", out)
        self.assertIn("Sit down", out)
        self.assertIn("\u2605", out)

    def test_full_pipeline_widths_match(self):
        src = "```mermaid\njourney\n    section A\n    T: 5: Me\n```"
        out = render(src, width=50, color=False)
        for ln in out.split("\n"):
            if ln:
                self.assertEqual(visual_len(ln), 50)


if __name__ == "__main__":
    unittest.main()
