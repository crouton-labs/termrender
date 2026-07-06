import unittest

from termrender import render
from termrender.renderers.mermaid_timeline import parse_timeline, render as render_timeline
from termrender.style import visual_len


class TestParseTimeline(unittest.TestCase):

    def test_parses_title(self):
        parsed = parse_timeline("timeline\n    title Launches\n    2002 : LinkedIn\n")
        self.assertEqual(parsed["title"], "Launches")

    def test_parses_period_and_event(self):
        parsed = parse_timeline("timeline\n    2002 : LinkedIn\n")
        entries = parsed["sections"][0]["entries"]
        self.assertEqual(entries, [{"date": "2002", "event": "LinkedIn"}])

    def test_multiple_events_same_period_on_one_line(self):
        parsed = parse_timeline("timeline\n    2004 : Facebook : Google\n")
        entries = parsed["sections"][0]["entries"]
        self.assertEqual(
            entries,
            [{"date": "2004", "event": "Facebook"}, {"date": "", "event": "Google"}],
        )

    def test_continuation_line_reuses_last_period(self):
        parsed = parse_timeline("timeline\n    2004 : Facebook\n         : Google\n")
        entries = parsed["sections"][0]["entries"]
        self.assertEqual(entries[1], {"date": "", "event": "Google"})

    def test_leading_continuation_with_no_prior_period_skipped(self):
        parsed = parse_timeline("timeline\n    : orphan event\n    2002 : LinkedIn\n")
        entries = parsed["sections"][0]["entries"]
        self.assertEqual(entries, [{"date": "2002", "event": "LinkedIn"}])

    def test_sections_grouped(self):
        parsed = parse_timeline(
            "timeline\n"
            "    2002 : LinkedIn\n"
            "    section Recent\n"
            "        2020 : TikTok\n"
        )
        self.assertEqual([s["name"] for s in parsed["sections"]], [None, "Recent"])

    def test_empty_section_dropped(self):
        parsed = parse_timeline(
            "timeline\n    section Empty\n    section Full\n    2020 : X\n"
        )
        self.assertEqual([s["name"] for s in parsed["sections"]], ["Full"])

    def test_no_entries_yields_no_sections(self):
        parsed = parse_timeline("timeline\n    title Empty\n")
        self.assertEqual(parsed["sections"], [])


class TestRenderTimeline(unittest.TestCase):

    def test_golden_small_timeline(self):
        src = "timeline\n    title Launches\n    2002 : LinkedIn\n    2004 : Facebook\n"
        lines = render_timeline(src, width=30)
        self.assertEqual(
            lines,
            [
                "Launches                      ",
                "2002 \u25cf LinkedIn               ",
                "     \u2502                        ",
                "2004 \u25cf Facebook               ",
            ],
        )

    def test_no_entries_degrades_to_source(self):
        src = "timeline\n    title nothing here\n"
        self.assertEqual(render_timeline(src, width=40), src.splitlines())

    def test_section_names_appear(self):
        src = "timeline\n    2002 : LinkedIn\n    section Recent\n    2020 : TikTok\n"
        lines = render_timeline(src, width=40)
        self.assertTrue(any("Recent" in ln for ln in lines))

    def test_no_ansi_when_monochrome(self):
        src = "timeline\n    2002 : LinkedIn\n"
        lines = render_timeline(src, width=40)
        self.assertNotIn("\x1b[", "\n".join(lines))

    def test_widths_match(self):
        src = "timeline\n    title T\n    2002 : LinkedIn\n    2004 : Facebook\n"
        for line in render_timeline(src, width=45):
            self.assertEqual(visual_len(line), 45)

    def test_full_pipeline_renders_timeline(self):
        src = "```mermaid\ntimeline\n    title Launches\n    2002 : LinkedIn\n```"
        out = render(src, width=40, color=False)
        self.assertIn("Launches", out)
        self.assertIn("LinkedIn", out)
        self.assertIn("\u25cf", out)

    def test_full_pipeline_widths_match(self):
        src = "```mermaid\ntimeline\n    2002 : LinkedIn\n```"
        out = render(src, width=50, color=False)
        for ln in out.split("\n"):
            if ln:
                self.assertEqual(visual_len(ln), 50)


if __name__ == "__main__":
    unittest.main()
