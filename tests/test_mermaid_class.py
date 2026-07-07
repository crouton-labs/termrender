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


def test_multiple_labeled_relationships_around_one_class():
    # One class (Hub) is a crowded junction: six labeled UML relationships
    # of different kinds all fan out from it, every one crossing the
    # identical Hub-to-children band — each must get its own jog row so its
    # label survives distinct and unfused rather than every edge piling
    # onto one shared row. Each marker glyph must survive too (not just
    # the last-drawn one).
    src = (
        "classDiagram\n"
        "Hub <|-- Alpha : extends\n"
        "Hub *-- Beta : has\n"
        "Hub o-- Gamma : owns\n"
        "Hub --> Delta : uses\n"
        "Hub --> Echo : likes\n"
        "Hub --> Foxtrot : needs\n"
    )
    lines = _lines(src, width=100)
    joined = "\n".join(lines)
    labels = ["extends", "has", "owns", "uses", "likes", "needs"]
    for label in labels:
        assert joined.count(label) == 1, f"{label!r} must appear exactly once: {lines!r}"
    for name in ("Hub", "Alpha", "Beta", "Gamma", "Delta", "Echo", "Foxtrot"):
        assert name in joined
    assert "△" in joined  # Hub<|--Alpha (inheritance)
    assert "◆" in joined  # Hub*--Beta (composition)
    assert "◇" in joined  # Hub o-- Gamma (aggregation)

    # None fused onto a class's own name/border row.
    for label in labels:
        row, _ = _row_col(lines, label)
        for name in ("Hub", "Alpha", "Beta", "Gamma", "Delta", "Echo", "Foxtrot"):
            assert name not in lines[row], (
                f"{label!r} landed on {name}'s own row: {lines[row]!r}"
            )

    # None detached below the whole diagram body.
    last_box_row = max(i for i, line in enumerate(lines) if _BOX_GLYPH_RE.search(line))
    for label in labels:
        row, _ = _row_col(lines, label)
        assert row <= last_box_row, f"{label!r} detached below the diagram: {lines!r}"

    # All six share the identical Hub-to-children band, so each must land
    # on its own distinct row rather than fusing onto one shared row.
    rows = [_row_col(lines, label)[0] for label in labels]
    assert len(set(rows)) == len(labels), (
        f"labels shared a row instead of each getting its own: {lines!r}"
    )


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


def test_unrecognized_body_line_forces_raw_echo():
    src = 'classDiagram\nclass Animal\nnote for Animal "hello ┌"'
    lines = _lines(src)
    assert lines == ["classDiagram", "class Animal", 'note for Animal "hello ?"']
    assert not _has_box_glyphs(lines)


def test_unterminated_class_body_forces_raw_echo():
    src = "classDiagram\nclass A {\n+foo"
    lines = _lines(src)
    assert lines == ["classDiagram", "class A {", "+foo"]
    assert not _has_box_glyphs(lines)


def test_malformed_presentational_directive_without_payload_forces_raw_echo():
    src = "classDiagram\nclass Animal\nstyle"
    lines = _lines(src)
    assert lines == ["classDiagram", "class Animal", "style"]
    assert not _has_box_glyphs(lines)


def test_malformed_class_assignment_directive_forces_raw_echo():
    src = "classDiagram\nclass Animal\nclass this is not mermaid ┌"
    lines = _lines(src)
    assert lines == ["classDiagram", "class Animal", "class this is not mermaid ?"]
    assert not _has_box_glyphs(lines)


def test_presentational_directive_inside_class_body_forces_raw_echo():
    src = "classDiagram\nclass Animal {\nstyle\n}\n"
    lines = _lines(src)
    assert lines == ["classDiagram", "class Animal {", "style", "}"]
    assert not _has_box_glyphs(lines)


def test_presentational_lines_are_ignored_and_diagram_renders_natively():
    src = (
        "classDiagram\n"
        "classDef important fill:#f00,stroke:#333,stroke-width:2px\n"
        "style Animal fill:#efe,stroke:#333\n"
        "cssClass Animal important\n"
        "accTitle: Animal diagram\n"
        "accDescr: accessible description\n"
        "class Animal\n"
    )
    lines = _lines(src)
    assert _has_box_glyphs(lines)
    assert any("Animal" in line for line in lines)


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


# --------------------------------------------------------------------------
# Back-edge labels are placed outside all node rects: a back-edge's
# horizontal exit leg travels along its source's own rank row, a row every
# rank-mate box also occupies, so the label must clear every sibling in
# that rank, not just the edge's own source and destination.
# --------------------------------------------------------------------------


def test_back_edge_label_does_not_cross_sibling_boxes():
    # Hub fans out to six children; Alpha alone routes a labeled edge back
    # into Hub. Alpha's rank has five siblings (Beta..Eff) to its right —
    # the crowded-rank shape that exercises the lane clearing every
    # sibling's box, not just Alpha's and Hub's.
    src = (
        "classDiagram\n"
        "    Hub --> Alpha : extends\n"
        "    Hub --> Beta : has\n"
        "    Hub --> Cee : owns\n"
        "    Hub --> Dee : uses\n"
        "    Hub --> Eee : likes\n"
        "    Hub --> Eff : needs\n"
        "    Alpha --> Hub : returns\n"
    )
    lines = _lines(src, width=100)
    text = "\n".join(lines)
    assert text.count("returns") == 1, f"'returns' must appear exactly once: {lines!r}"

    from termrender.renderers.mermaid_class import _build_graph
    from termrender.renderers import mermaid_flow_layout as fl

    graph = _build_graph(src)
    node_subgraph = fl._node_subgraph_map(graph.subgraphs)
    rects = fl._place_nodes(graph.nodes, graph.edges, graph.direction, node_subgraph)

    label_cells: set[tuple[int, int]] = set()
    for r, line in enumerate(lines):
        c = line.find("returns")
        if c != -1:
            label_cells.update((c + i, r) for i in range(len("returns")))
    assert label_cells, f"expected to find 'returns' in the rendered output: {lines!r}"

    for node_id, rect in rects.items():
        box_cells = {
            (x, y)
            for x in range(rect.x, rect.x + rect.w)
            for y in range(rect.y, rect.y + rect.h)
        }
        overlap = label_cells & box_cells
        assert not overlap, f"'returns' label overlaps {node_id}'s box at {overlap}: {lines!r}"

    # Every sibling node name must survive intact, on its own line, not
    # fused with the back-edge's label onto one run-together line.
    for name in ("Alpha", "Beta", "Cee", "Dee", "Eee", "Eff", "Hub"):
        assert name in text
    for r, line in enumerate(lines):
        if "returns" in line:
            assert "Beta" not in line and "Cee" not in line, (
                f"'returns' fused onto a sibling box's row: {line!r}"
            )
