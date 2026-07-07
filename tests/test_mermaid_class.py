"""Golden-output tests for the native mermaid classDiagram renderer.

Mirrors ``test_mermaid_flow_corpus.py``'s methodology: real rendered
geometry (exact line lists, or topology assertions on a full relation
chain), not merely "no exception raised". ``render_class`` reuses the
flowchart engine's grandalf layout + rasterizer + router (via the shared
``FlowGraph``/``FlowNode``/``FlowEdge`` model — see ``mermaid_class.py``'s
module docstring), so these tests exercise the two UML-specific
extensions (compartmented boxes, arrow-kind glyphs) end to end rather than
re-testing the underlying engine (already covered by
``test_mermaid_flow_corpus.py``/``test_mermaid_flow_shapes.py``).
"""

from __future__ import annotations

import re

from termrender.renderers.mermaid_class import render_class

_BOX_GLYPH_RE = re.compile(r"[\u2500-\u259F\u25A0-\u25FF]")


def _lines(source: str, width: int = 80) -> list[str]:
    return render_class(source, width)


def _has_box_glyphs(lines: list[str]) -> bool:
    return any(_BOX_GLYPH_RE.search(line) for line in lines)


def _row_col(lines: list[str], glyph: str) -> tuple[int, int]:
    for r, line in enumerate(lines):
        c = line.find(glyph)
        if c != -1:
            return r, c
    raise AssertionError(f"glyph {glyph!r} not found in {lines!r}")


# --------------------------------------------------------------------------
# Compartmented classes
# --------------------------------------------------------------------------


def test_multiline_class_block_compartments():
    src = (
        "classDiagram\n"
        "class Animal {\n"
        "  +String name\n"
        "  +int age\n"
        "  +isMammal() bool\n"
        "}\n"
    )
    assert _lines(src) == [
        "┌──────────────────┐",
        "│      Animal      │",
        "├──────────────────┤",
        "│ +String name     │",
        "│ +int age         │",
        "├──────────────────┤",
        "│ +isMammal() bool │",
        "└──────────────────┘",
    ]


def test_oneline_semicolon_class_block():
    src = "classDiagram\nclass Name { +field type; +method() }\n"
    assert _lines(src) == [
        "┌─────────────┐",
        "│    Name     │",
        "├─────────────┤",
        "│ +field type │",
        "├─────────────┤",
        "│ +method()   │",
        "└─────────────┘",
    ]


def test_member_association_form():
    src = "classDiagram\nAnimal : +int age\nAnimal : +walk()\n"
    assert _lines(src) == [
        "┌──────────┐",
        "│  Animal  │",
        "├──────────┤",
        "│ +int age │",
        "├──────────┤",
        "│ +walk()  │",
        "└──────────┘",
    ]


def test_bare_class_no_body_is_plain_box_not_compartmented():
    # No block, no members, no annotation -> ordinary single-label box
    # (compartments=None path), not a 3-band UML box.
    assert _lines("classDiagram\nclass Foo\n") == [
        "┌─────┐",
        "│ Foo │",
        "└─────┘",
    ]


def test_annotation_only_class_has_no_body_but_shows_stereotype():
    assert _lines("classDiagram\n<<interface>> Shape\n") == [
        "┌─────────────┐",
        "│ «interface» │",
        "│    Shape    │",
        "└─────────────┘",
    ]


def test_class_with_body_and_no_fields_still_shows_blank_fields_band():
    src = "classDiagram\nclass Stack {\n  +push()\n}\n"
    lines = _lines(src)
    # 3 compartments: name / (blank fields band) / methods — two separator
    # rows present even though the fields section has zero declared fields.
    sep_rows = [i for i, l in enumerate(lines) if set(l.strip()) <= {"├", "─", "┤"}]
    assert len(sep_rows) == 2


# --------------------------------------------------------------------------
# Generics
# --------------------------------------------------------------------------


def test_generics_render_as_angle_brackets():
    src = "classDiagram\nclass Stack~T~ {\n  +push(item T)\n  +pop() T\n}\n"
    lines = _lines(src)
    assert any("Stack<T>" in line for line in lines)
    assert not any("~" in line for line in lines)


def test_generic_reference_resolves_to_same_node_as_declaration():
    # `List~T~` declared, then referenced bare as `List` in a relation —
    # both must resolve to one node (one box), not two.
    src = "classDiagram\nclass List~T~\nList <|-- ArrayList\n"
    lines = _lines(src)
    assert sum(1 for line in lines if "List<T>" in line) == 1
    assert any("ArrayList" in line for line in lines)


# --------------------------------------------------------------------------
# All six UML relationship kinds — distinct glyph, correct topology
# --------------------------------------------------------------------------


def test_inheritance_hollow_triangle_at_parent():
    lines = _lines("classDiagram\nAnimal <|-- Duck\n")
    assert _has_box_glyphs(lines)
    assert any("△" in line for line in lines)
    assert "◆" not in "".join(lines) and "◇" not in "".join(lines)
    animal_row, _ = _row_col(lines, "Animal")
    duck_row, _ = _row_col(lines, "Duck")
    assert animal_row < duck_row  # parent above child (TB)


def test_composition_filled_diamond_at_owner():
    lines = _lines("classDiagram\nCar *-- Engine\n")
    assert any("◆" in line for line in lines)
    car_row, _ = _row_col(lines, "Car")
    engine_row, _ = _row_col(lines, "Engine")
    assert car_row < engine_row
    diamond_row, _ = _row_col(lines, "◆")
    assert diamond_row < engine_row  # marker sits at the owner (Car) end


def test_aggregation_hollow_diamond_at_owner():
    lines = _lines("classDiagram\nCar o-- Wheel\n")
    assert any("◇" in line for line in lines)


def test_two_source_side_markers_from_one_class_both_survive():
    # Regression: Whole both composes Part1 and aggregates Part2, so both
    # relations' source-side marker used to land on Whole's one shared
    # exit anchor — only the last-drawn glyph survived there. Both must
    # now be visible (see mermaid_flow_layout.py's _allocate_edge_anchors).
    lines = _lines("classDiagram\nWhole *-- Part1\nWhole o-- Part2\n")
    joined = "\n".join(lines)
    assert "◆" in joined
    assert "◇" in joined
    for name in ("Whole", "Part1", "Part2"):
        assert name in joined


def test_association_filled_arrow_at_target():
    lines = _lines("classDiagram\nDriver --> Car\n")
    assert any("▼" in line for line in lines)
    driver_row, _ = _row_col(lines, "Driver")
    car_row, _ = _row_col(lines, "Car")
    assert driver_row < car_row


def test_dependency_dashed_arrow_at_target():
    lines = _lines("classDiagram\nOrderService ..> Logger\n")
    joined = "\n".join(lines)
    assert "╎" in joined  # dashed vertical line style
    assert "▼" in joined  # plain (non-hollow, non-diamond) arrowhead


def test_realization_hollow_triangle_dashed():
    lines = _lines("classDiagram\nShape <|.. Circle\n")
    joined = "\n".join(lines)
    assert "△" in joined
    assert "╎" in joined


def test_headless_solid_and_dashed_links_draw_no_arrowhead():
    solid = "\n".join(_lines("classDiagram\nA -- B\n"))
    dashed = "\n".join(_lines("classDiagram\nA .. B\n"))
    for glyph in ("△", "▽", "◁", "▷", "◆", "◇", "▲", "▼", "◀", "▶"):
        assert glyph not in solid
        assert glyph not in dashed
    assert "╎" in dashed
    assert "╎" not in solid


def test_reversed_writing_direction_is_equivalent():
    # `--|>` (marker on the right) means the same as `<|--` (marker on the
    # left) — same hollow-triangle glyph family, same topological
    # attachment to the parent (Animal). Writing it as `Duck --|> Animal`
    # makes Duck the src (ranked first / above); the marker still lands on
    # Animal (the parent) but now points downward into it (▽) rather than
    # upward (△) — same relation, geometrically correct for the flipped
    # rank order.
    forward = _lines("classDiagram\nAnimal <|-- Duck\n")
    reversed_form = _lines("classDiagram\nDuck --|> Animal\n")
    hollow_triangle = set("△▽◁▷")
    assert any(set(line) & hollow_triangle for line in forward)
    assert any(set(line) & hollow_triangle for line in reversed_form)
    a_row, _ = _row_col(reversed_form, "Animal")
    d_row, _ = _row_col(reversed_form, "Duck")
    assert d_row < a_row  # Duck (src) declared/ranked above Animal (dst/parent)


# --------------------------------------------------------------------------
# Cardinalities + edge labels
# --------------------------------------------------------------------------


def test_cardinality_and_label_combine_on_the_edge():
    lines = _lines('classDiagram\nAnimal "1" --> "many" Leg : has\n')
    assert any("1 has many" in line for line in lines)


def test_cardinality_without_label():
    lines = _lines('classDiagram\nAnimal "1" --> "many" Leg\n')
    assert any("1 many" in line for line in lines)


# --------------------------------------------------------------------------
# Full topology: all six kinds chained in one diagram
# --------------------------------------------------------------------------


def test_all_six_relation_kinds_chained_topology():
    src = (
        "classDiagram\n"
        "A <|-- B\n"
        "B *-- C\n"
        "C o-- D\n"
        "D --> E\n"
        "E ..> F\n"
        "F <|.. G\n"
    )
    lines = _lines(src)
    joined = "\n".join(lines)
    for name in "ABCDEFG":
        assert any(name == line.strip("│ ") for line in lines) or f" {name} " in joined
    # Every declared node appears; rows strictly increase top-to-bottom for
    # this linear TB chain (no phantom or misattached edges).
    rows = {name: _row_col(lines, name)[0] for name in "ABCDEFG"}
    ordered = [rows[n] for n in "ABCDEFG"]
    assert ordered == sorted(ordered)
    assert "△" in joined  # A<|--B and F<|..G
    assert "◆" in joined  # B*--C
    assert "◇" in joined  # C o-- D
    assert "▼" in joined  # D-->E
    assert "╎" in joined  # E..>F dashed


# --------------------------------------------------------------------------
# Direction
# --------------------------------------------------------------------------


def test_lr_direction():
    lines = _lines("classDiagram\ndirection LR\nA <|-- B\n")
    a_row, a_col = _row_col(lines, "A")
    b_row, b_col = _row_col(lines, "B")
    assert a_col < b_col  # A left of B
    assert any("◁" in line for line in lines)  # hollow triangle pointing left, at A


# --------------------------------------------------------------------------
# Degradation: malformed input, empty body, literal-glyph sanitization
# --------------------------------------------------------------------------


def test_non_class_diagram_source_degrades_to_raw_echo():
    src = "graph TD\nA-->B\n"
    lines = _lines(src)
    assert lines == ["graph TD", "A-->B"]
    assert not _has_box_glyphs(lines)


def test_header_only_empty_body_degrades_to_raw_echo():
    lines = _lines("classDiagram\n")
    assert lines == ["classDiagram"]
    assert not _has_box_glyphs(lines)


def test_malformed_input_with_literal_box_glyph_is_sanitized():
    src = "not a class diagram\nhas a \u2500 literal glyph\n"
    lines = _lines(src)
    assert lines == ["not a class diagram", "has a ? literal glyph"]
    assert not _has_box_glyphs(lines)


def test_render_class_never_raises_on_garbage():
    for garbage in ("", "\n\n\n", "classDiagram\nclass {{{\n", "classDiagram\n}}}}\n"):
        # Must not raise.
        render_class(garbage, 80)
