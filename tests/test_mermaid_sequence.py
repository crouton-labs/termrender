import unittest

from termrender.renderers.mermaid_sequence import SequenceDiagramError, render_sequence


class TestNotASequenceDiagram(unittest.TestCase):

    def test_flowchart_source_raises(self):
        with self.assertRaises(SequenceDiagramError):
            render_sequence("graph TD\n  A-->B", 80)

    def test_pie_source_raises(self):
        with self.assertRaises(SequenceDiagramError):
            render_sequence('pie\n    "A" : 1', 80)

    def test_blank_source_raises(self):
        with self.assertRaises(SequenceDiagramError):
            render_sequence("", 80)

    def test_leading_blank_lines_before_header_are_tolerated(self):
        src = "\n\n  sequenceDiagram\n    A->>B: hi\n"
        # Should not raise, and should render something.
        lines = render_sequence(src, 80)
        self.assertTrue(any("hi" in line for line in lines))


class TestGoldenBasicArrows(unittest.TestCase):
    """Locks down the canonical two-participant example."""

    def test_classic_two_participant_exchange(self):
        src = (
            "sequenceDiagram\n"
            "    Alice->>Bob: Hello Bob, how are you?\n"
            "    Bob-->>Alice: Great!\n"
        )
        expected = [
            "┌───────┐                 ┌─────┐",
            "│ Alice │                 │ Bob │",
            "└───────┘                 └─────┘",
            "    │                        │",
            "     Hello Bob, how are you?",
            "    ─────────────────────────>",
            "    │                        │",
            "              Great!",
            "    <╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌",
            "    │                        │",
            "┌───────┐                 ┌─────┐",
            "│ Alice │                 │ Bob │",
            "└───────┘                 └─────┘",
        ]
        self.assertEqual(render_sequence(src, 80), expected)

    def test_self_message_golden(self):
        src = "sequenceDiagram\n    participant A\n    A->>A: Think\n"
        expected = [
            "┌───┐",
            "│ A │",
            "└───┘",
            "  │",
            "  ─╮",
            "  ││ Think",
            "  <╯",
            "  │",
            "┌───┐",
            "│ A │",
            "└───┘",
        ]
        self.assertEqual(render_sequence(src, 80), expected)

    def test_autonumber_golden(self):
        src = (
            "sequenceDiagram\n"
            "    autonumber\n"
            "    participant A\n"
            "    participant B\n"
            "    A->>B: one\n"
            "    B->>A: two\n"
        )
        expected = [
            "┌───┐   ┌───┐",
            "│ A │   │ B │",
            "└───┘   └───┘",
            "  │       │",
            "   1: one",
            "  ────────>",
            "  │       │",
            "   2: two",
            "  <────────",
            "  │       │",
            "┌───┐   ┌───┐",
            "│ A │   │ B │",
            "└───┘   └───┘",
        ]
        self.assertEqual(render_sequence(src, 80), expected)


class TestArrowVariants(unittest.TestCase):
    """All 8 arrow forms must be visually distinct: solid vs dashed line,
    and a distinct arrowhead glyph per marker type."""

    def _arrow_lines(self, arrow: str) -> list[str]:
        src = f"sequenceDiagram\n    participant A\n    participant B\n    A{arrow}B: x\n"
        lines = render_sequence(src, 80)
        # The arrow line has a horizontal connector but is not a box border
        # (box borders also contain \u2500/\u254c via their corners).
        return [
            l
            for l in lines
            if ("\u2500" in l or "\u254c" in l) and "\u250c" not in l and "\u2514" not in l
        ]

    def test_solid_open(self):
        lines = self._arrow_lines("->")
        self.assertTrue(any(l.rstrip().endswith("\u203a") for l in lines))  # ›
        self.assertTrue(any("\u2500" in l for l in lines))
        self.assertFalse(any("\u254c" in l for l in lines))

    def test_dashed_open(self):
        lines = self._arrow_lines("-->")
        self.assertTrue(any(l.rstrip().endswith("\u203a") for l in lines))
        self.assertTrue(any("\u254c" in l for l in lines))

    def test_solid_filled(self):
        lines = self._arrow_lines("->>")
        self.assertTrue(any(l.rstrip().endswith(">") for l in lines))
        self.assertTrue(any("\u2500" in l for l in lines))
        self.assertFalse(any("\u254c" in l for l in lines))

    def test_dashed_filled(self):
        lines = self._arrow_lines("-->>")
        self.assertTrue(any(l.rstrip().endswith(">") for l in lines))
        self.assertTrue(any("\u254c" in l for l in lines))

    def test_solid_lost(self):
        lines = self._arrow_lines("-x")
        self.assertTrue(any(l.rstrip().endswith("\u2717") for l in lines))  # ✗
        self.assertFalse(any("\u254c" in l for l in lines))

    def test_dashed_lost(self):
        lines = self._arrow_lines("--x")
        self.assertTrue(any(l.rstrip().endswith("\u2717") for l in lines))
        self.assertTrue(any("\u254c" in l for l in lines))

    def test_solid_async(self):
        lines = self._arrow_lines("-)")
        self.assertTrue(any(l.rstrip().endswith(")") for l in lines))
        self.assertFalse(any("\u254c" in l for l in lines))

    def test_dashed_async(self):
        lines = self._arrow_lines("--)")
        self.assertTrue(any(l.rstrip().endswith(")") for l in lines))
        self.assertTrue(any("\u254c" in l for l in lines))

    def test_reverse_direction_arrowhead_points_left(self):
        src = "sequenceDiagram\n    participant A\n    participant B\n    B->>A: back\n"
        lines = render_sequence(src, 80)
        arrow_line = next(
            l for l in lines if "\u2500" in l and "\u250c" not in l and "\u2514" not in l
        )
        self.assertTrue(arrow_line.lstrip().startswith("<"))


class TestParticipantsAndAliases(unittest.TestCase):

    def test_explicit_participant_and_actor_with_alias(self):
        src = (
            "sequenceDiagram\n"
            "    participant C1 as Core (PID 92348)\n"
            "    actor U as User\n"
            "    C1->>U: ping\n"
        )
        lines = render_sequence(src, 80)
        self.assertTrue(any("Core (PID 92348)" in l for l in lines))
        self.assertTrue(any("User" in l for l in lines))

    def test_implicit_participants_ordered_by_first_appearance(self):
        src = "sequenceDiagram\n    B->>A: hi\n    A->>C: hey\n"
        lines = render_sequence(src, 80)
        header = lines[1]  # the row with participant labels
        self.assertLess(header.index("B"), header.index("A"))
        self.assertLess(header.index("A"), header.index("C"))

    def test_implicit_and_explicit_participants_mixed(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    A->>B: hi\n"  # B is implicit
        )
        lines = render_sequence(src, 80)
        self.assertTrue(any("A" in l and "B" in l for l in lines[:3]))


class TestNotes(unittest.TestCase):

    def test_note_over_two_participants_and_solo_golden(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    Note over A,B: shared context\n"
            "    Note over A: solo\n"
        )
        expected = [
            "┌───┐  ┌───┐",
            "│ A │  │ B │",
            "└───┘  └───┘",
            "  │      │",
            "┌────────────────┐",
            "│ shared context │",
            "└────────────────┘",
            "  │      │",
            "┌──────┐ │",
            "│ solo │ │",
            "└──────┘ │",
            "  │      │",
            "┌───┐  ┌───┐",
            "│ A │  │ B │",
            "└───┘  └───┘",
        ]
        self.assertEqual(render_sequence(src, 80), expected)

    def test_note_left_of_and_right_of_render_without_crashing(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    Note left of A: L\n"
            "    Note right of B: R\n"
        )
        lines = render_sequence(src, 80)
        self.assertTrue(any("L" in l for l in lines))
        self.assertTrue(any("R" in l for l in lines))

    def test_note_left_of_first_participant_clamps_instead_of_going_negative(self):
        # Known degradation: overflow to the left of column 0 clamps to 0
        # rather than producing a negative-index crash.
        src = (
            "sequenceDiagram\n"
            "    Note left of A: a very long note that would overflow left\n"
            "    A->>B: hi\n"
        )
        lines = render_sequence(src, 80)  # must not raise
        self.assertTrue(any("overflow left" in l for l in lines))


class TestBrAndActivateTolerated(unittest.TestCase):

    def test_br_flattened_in_message(self):
        src = "sequenceDiagram\n    participant A\n    participant B\n    A->>B: line1<br/>line2\n"
        lines = render_sequence(src, 80)
        self.assertTrue(any("line1 / line2" in l for l in lines))
        self.assertFalse(any("<br" in l for l in lines))

    def test_br_flattened_in_note(self):
        src = "sequenceDiagram\n    participant A\n    Note over A: line1<br/>line2\n"
        lines = render_sequence(src, 80)
        self.assertTrue(any("line1 / line2" in l for l in lines))

    def test_standalone_activate_deactivate_tolerated(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    activate A\n"
            "    A->>B: hi\n"
            "    deactivate A\n"
        )
        lines = render_sequence(src, 80)  # must not raise
        self.assertTrue(any("hi" in l for l in lines))

    def test_arrow_activation_shorthand_tolerated(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    A->>+B: hi\n"
            "    B-->>-A: bye\n"
        )
        lines = render_sequence(src, 80)  # must not raise
        self.assertTrue(any("hi" in l for l in lines))
        self.assertTrue(any("bye" in l for l in lines))


class TestBlockConstructs(unittest.TestCase):

    def test_loop_renders_as_labeled_band(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    loop every second\n"
            "    A->>B: poll\n"
            "    end\n"
        )
        lines = render_sequence(src, 80)
        self.assertTrue(any(l.startswith("\u250c\u2500 loop every second") for l in lines))
        self.assertTrue(any(l.startswith("\u2514") for l in lines))

    def test_alt_else_renders_start_mid_end_bands(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    alt success\n"
            "    A->>B: ok\n"
            "    else failure\n"
            "    A->>B: fail\n"
            "    end\n"
        )
        lines = render_sequence(src, 80)
        self.assertTrue(any("alt success" in l and l.startswith("\u250c") for l in lines))
        self.assertTrue(any("else failure" in l and l.startswith("\u251c") for l in lines))
        self.assertTrue(any(l.startswith("\u2514") for l in lines))

    def test_nested_loop_and_alt_does_not_crash(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    loop outer\n"
            "    alt inner\n"
            "    A->>B: x\n"
            "    end\n"
            "    end\n"
        )
        lines = render_sequence(src, 80)  # must not raise
        self.assertTrue(any("x" in l for l in lines))

    def test_par_and_renders_bands(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    par one\n"
            "    A->>B: x\n"
            "    and two\n"
            "    A->>B: y\n"
            "    end\n"
        )
        lines = render_sequence(src, 80)
        self.assertTrue(any("par one" in l for l in lines))
        self.assertTrue(any("and two" in l for l in lines))


class TestDegradationCases(unittest.TestCase):
    """Malformed or unrecognized constructs must degrade to plain lines,
    never crash."""

    def test_stray_else_with_no_open_block_degrades_to_plain_line(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    else stray\n"
            "    A->>A: x\n"
        )
        lines = render_sequence(src, 80)  # must not raise
        self.assertTrue(any("else stray" in l for l in lines))

    def test_stray_end_with_no_open_block_is_ignored(self):
        src = "sequenceDiagram\n    participant A\n    end\n    A->>A: x\n"
        lines = render_sequence(src, 80)  # must not raise
        self.assertTrue(any("x" in l for l in lines))

    def test_unrecognized_line_degrades_to_plain_label(self):
        src = "sequenceDiagram\n    participant A\n    title Some Title\n    A->>A: x\n"
        lines = render_sequence(src, 80)  # must not raise
        self.assertTrue(any("Some Title" in l for l in lines))

    def test_no_participants_no_events_returns_empty(self):
        src = "sequenceDiagram\n"
        self.assertEqual(render_sequence(src, 80), [])

    def test_comment_lines_ignored(self):
        src = "sequenceDiagram\n    %% a comment\n    participant A\n    A->>A: hi\n"
        lines = render_sequence(src, 80)  # must not raise
        self.assertFalse(any("%%" in l for l in lines))


class TestMultiHopSpacing(unittest.TestCase):

    def test_message_spanning_multiple_columns_widens_gaps(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    participant C\n"
            "    A->>C: a rather long message across two hops\n"
        )
        lines = render_sequence(src, 80)
        arrow_line = next(
            l for l in lines if "\u2500" in l and "\u250c" not in l and "\u2514" not in l
        )
        # the arrow line must span at least as wide as the label text needs
        self.assertGreaterEqual(len(arrow_line), len("a rather long message across two hops"))

    def test_self_message_on_last_participant_does_not_crash(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    B->>B: last col self loop\n"
        )
        lines = render_sequence(src, 80)  # must not raise
        self.assertTrue(any("last col self loop" in l for l in lines))


class TestNoSignificantTrailingWhitespace(unittest.TestCase):

    def _assert_no_trailing_whitespace(self, src: str) -> None:
        for line in render_sequence(src, 80):
            self.assertEqual(line, line.rstrip(), f"trailing whitespace in: {line!r}")

    def test_basic_exchange(self):
        self._assert_no_trailing_whitespace(
            "sequenceDiagram\n    A->>B: hi\n    B-->>A: bye\n"
        )

    def test_notes_and_blocks(self):
        self._assert_no_trailing_whitespace(
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    Note over A,B: n\n"
            "    loop x\n"
            "    A->>B: y\n"
            "    end\n"
        )

    def test_self_message(self):
        self._assert_no_trailing_whitespace(
            "sequenceDiagram\n    participant A\n    A->>A: think\n"
        )


if __name__ == "__main__":
    unittest.main()
