"""Golden-output tests for the native mermaid erDiagram renderer.

Mirrors ``test_mermaid_class.py``'s methodology: real rendered geometry
(exact line lists, or topology assertions on a full relation chain), not
merely "no exception raised". ``render_er`` reuses the flowchart engine's
grandalf layout + rasterizer + router (via the shared ``FlowGraph``/
``FlowNode``/``FlowEdge`` model — see ``mermaid_er.py``'s module
docstring), so these tests exercise the ER-specific parsing (attribute
blocks, cardinality-to-text mapping, aliasing) end to end rather than
re-testing the underlying engine (already covered by
``test_mermaid_flow_corpus.py``/``test_mermaid_flow_shapes.py``).
"""

from __future__ import annotations

import re

from termrender.renderers.mermaid_er import render_er

_BOX_GLYPH_RE = re.compile(r"[\u2500-\u259F\u25A0-\u25FF]")


def _lines(source: str, width: int = 80) -> list[str]:
    return render_er(source, width)


def _has_box_glyphs(lines: list[str]) -> bool:
    return any(_BOX_GLYPH_RE.search(line) for line in lines)


def _row_col(lines: list[str], glyph: str) -> tuple[int, int]:
    for r, line in enumerate(lines):
        c = line.find(glyph)
        if c != -1:
            return r, c
    raise AssertionError(f"glyph {glyph!r} not found in {lines!r}")


# --------------------------------------------------------------------------
# Compartmented entities
# --------------------------------------------------------------------------


def test_multiline_entity_block_compartments():
    src = (
        "erDiagram\n"
        "CUSTOMER {\n"
        "    string name\n"
        "    string custNumber\n"
        "    string sector\n"
        "}\n"
    )
    assert _lines(src) == [
        "┌───────────────────┐",
        "│     CUSTOMER      │",
        "├───────────────────┤",
        "│ string name       │",
        "│ string custNumber │",
        "│ string sector     │",
        "└───────────────────┘",
    ]


def test_oneline_semicolon_entity_block():
    src = "erDiagram\nENTITY { string name PK; int qty }\n"
    lines = _lines(src)
    assert lines[0].startswith("┌")
    assert any("name PK" in line for line in lines)
    assert any("qty" in line for line in lines)
    sep_rows = [i for i, l in enumerate(lines) if set(l.strip()) <= {"├", "─", "┤"}]
    assert len(sep_rows) == 1


def test_bare_entity_no_block_is_plain_box_not_compartmented():
    assert _lines("erDiagram\nFOO\n") == [
        "┌─────┐",
        "│ FOO │",
        "└─────┘",
    ]


def test_entity_referenced_only_in_relationship_is_plain_box():
    lines = _lines("erDiagram\nA ||--o{ B : has\n")
    # Neither A nor B ever got a `{ ... }` block -> both are plain boxes
    # (no separator rows anywhere in the output).
    sep_rows = [i for i, l in enumerate(lines) if set(l.strip()) <= {"├", "─", "┤"}]
    assert sep_rows == []


def test_entity_with_empty_block_still_shows_blank_attribute_row():
    src = "erDiagram\nFOO {\n}\n"
    lines = _lines(src)
    sep_rows = [i for i, l in enumerate(lines) if set(l.strip()) <= {"├", "─", "┤"}]
    assert len(sep_rows) == 1
    assert any(l.strip("│ ") == "" for l in lines)


def test_attribute_comment_is_dropped_but_does_not_corrupt_parse():
    src = 'erDiagram\nFOO {\n  string code PK "a helpful comment"\n}\n'
    lines = _lines(src)
    assert any("code PK" in line for line in lines)
    assert not any("helpful comment" in line for line in lines)


# --------------------------------------------------------------------------
# Aliases / quoted names
# --------------------------------------------------------------------------


def test_entity_alias_bracket_form_displays_alias_not_id():
    lines = _lines("erDiagram\np[Person] {\n  string name\n}\n")
    assert any("Person" in line for line in lines)
    assert not any("p[Person]" in line for line in lines)


def test_alias_declared_once_resolves_same_node_from_relation():
    src = "erDiagram\np[Person] {\n  string name\n}\np ||--o{ CAR : owns\n"
    lines = _lines(src)
    assert sum(1 for line in lines if "Person" in line) == 1
    assert any("CAR" in line for line in lines)


def test_quoted_attribute_name_with_apostrophe():
    src = 'erDiagram\nPERSON {\n  string "driver\'s license" UK\n}\n'
    lines = _lines(src)
    assert any("driver's license" in line for line in lines)
    assert not any('"' in line for line in lines)


def test_quoted_entity_name_with_alias():
    src = 'erDiagram\n"Order Item"[OI] {\n  int qty\n}\n'
    lines = _lines(src)
    assert any("OI" in line for line in lines)
    assert not any("Order Item" in line for line in lines)


# --------------------------------------------------------------------------
# Cardinality grammar (all four kinds, both writing directions) + line style
# --------------------------------------------------------------------------


def test_exactly_one_cardinality_both_sides():
    lines = _lines("erDiagram\nA ||--|| B : rel\n")
    assert any("1 rel 1" in line for line in lines)


def test_zero_or_one_left_and_right_forms():
    left = _lines("erDiagram\nA |o--|| B : rel\n")
    right = _lines("erDiagram\nA ||--o| B : rel\n")
    assert any("0..1 rel 1" in line for line in left)
    assert any("1 rel 0..1" in line for line in right)


def test_one_or_more_left_and_right_forms():
    left = _lines("erDiagram\nA }|--|| B : rel\n")
    right = _lines("erDiagram\nA ||--|{ B : rel\n")
    assert any("1..* rel 1" in line for line in left)
    assert any("1 rel 1..*" in line for line in right)


def test_zero_or_more_left_and_right_forms():
    left = _lines("erDiagram\nA }o--|| B : rel\n")
    right = _lines("erDiagram\nA ||--o{ B : rel\n")
    assert any("0..* rel 1" in line for line in left)
    assert any("1 rel 0..*" in line for line in right)


def test_cardinality_without_label():
    lines = _lines("erDiagram\nCUSTOMER ||--o{ ORDER\n")
    assert any("1 0..*" in line for line in lines)


def test_identifying_relation_is_solid_line():
    lines = _lines("erDiagram\nA ||--o{ B : has\n")
    joined = "\n".join(lines)
    assert "│" in joined
    assert "╎" not in joined


def test_non_identifying_relation_is_dashed_line():
    lines = _lines("erDiagram\nA ||..o{ B : has\n")
    joined = "\n".join(lines)
    assert "╎" in joined


def test_relationship_never_draws_an_arrowhead():
    lines = _lines("erDiagram\nA ||--o{ B : has\n")
    joined = "\n".join(lines)
    for glyph in ("▲", "▼", "◀", "▶"):
        assert glyph not in joined


# --------------------------------------------------------------------------
# Full topology: a small multi-entity chain
# --------------------------------------------------------------------------


def test_multi_entity_chain_topology():
    src = "erDiagram\nA ||--o{ B : ab\nB ||--o{ C : bc\n"
    lines = _lines(src)
    assert _has_box_glyphs(lines)
    for name in "ABC":
        assert any(name == line.strip("│ ") for line in lines)
    a_row, _ = _row_col(lines, "A")
    b_row, _ = _row_col(lines, "B")
    c_row, _ = _row_col(lines, "C")
    assert a_row < b_row < c_row  # linear TB chain, declaration order


# --------------------------------------------------------------------------
# Golden corpus: mermaid docs' classic order example
# --------------------------------------------------------------------------


def test_order_example_golden_topology():
    src = (
        "erDiagram\n"
        "    CUSTOMER ||--o{ ORDER : places\n"
        "    ORDER ||--|{ LINE-ITEM : contains\n"
        "    CUSTOMER }|..|{ DELIVERY-ADDRESS : uses\n"
        "\n"
        "    CUSTOMER {\n"
        "        string name\n"
        "        string custNumber\n"
        "        string sector\n"
        "    }\n"
        "    ORDER {\n"
        "        int orderNumber\n"
        "        string deliveryAddress\n"
        "    }\n"
        "    LINE-ITEM {\n"
        "        string productCode\n"
        "        int quantity\n"
        "        float pricePerUnit\n"
        "    }\n"
    )
    lines = _lines(src)
    assert _has_box_glyphs(lines)
    joined = "\n".join(lines)

    for name in ("CUSTOMER", "ORDER", "LINE-ITEM", "DELIVERY-ADDRESS"):
        assert name in joined

    # DELIVERY-ADDRESS never got a block -> plain box; the other three did.
    da_row, da_col = _row_col(lines, "DELIVERY-ADDRESS")
    assert lines[da_row][da_col - 2] == "│"  # ` DELIVERY-ADDRESS ` inside a border

    for attr in ("string name", "string custNumber", "string sector"):
        assert attr in joined
    for attr in ("int orderNumber", "string deliveryAddress"):
        assert attr in joined
    for attr in ("string productCode", "int quantity", "float pricePerUnit"):
        assert attr in joined

    assert "places" in joined
    assert "contains" in joined
    assert "uses" in joined

    # Non-identifying relation (CUSTOMER }|..|{ DELIVERY-ADDRESS) is dashed.
    assert "╎" in joined

    cust_row, _ = _row_col(lines, "CUSTOMER")
    order_row, _ = _row_col(lines, "ORDER")
    line_item_row, _ = _row_col(lines, "LINE-ITEM")
    assert cust_row < order_row < line_item_row


# --------------------------------------------------------------------------
# Degradation: malformed input, empty body, literal-glyph sanitization
# --------------------------------------------------------------------------


def test_non_er_diagram_source_degrades_to_raw_echo():
    src = "graph TD\nA-->B\n"
    lines = _lines(src)
    assert lines == ["graph TD", "A-->B"]
    assert not _has_box_glyphs(lines)


def test_header_only_empty_body_degrades_to_raw_echo():
    lines = _lines("erDiagram\n")
    assert lines == ["erDiagram"]
    assert not _has_box_glyphs(lines)


def test_malformed_input_with_literal_box_glyph_is_sanitized():
    src = "not an er diagram\nhas a \u2500 literal glyph\n"
    lines = _lines(src)
    assert lines == ["not an er diagram", "has a ? literal glyph"]
    assert not _has_box_glyphs(lines)


def test_render_er_never_raises_on_garbage():
    for garbage in (
        "",
        "\n\n\n",
        "erDiagram\nFOO {{{\n",
        "erDiagram\n}}}}\n",
        "erDiagram\nA ||-- B\n",  # missing right cardinality pair
        'erDiagram\nA { string "unterminated PK\n',
    ):
        render_er(garbage, 80)  # must not raise
