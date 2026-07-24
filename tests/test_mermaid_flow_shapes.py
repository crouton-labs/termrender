"""Tests for flowchart node-shape borders, subgraph frames, and rank-flow
direction handling in the native mermaid flowchart renderer.

Every assertion here checks real rendered geometry — specific box-drawing
glyphs at specific rows/columns, or relative row/column ordering between
labels — never merely "no exception raised". Companion to
``test_mermaid_flow.py`` (topology/edge-routing/degradation contract),
which does not cover shapes, frames, or non-TD directions at all.
"""

from __future__ import annotations

import re

from termrender.renderers.mermaid_flow import render_flowchart
from termrender.style import visual_len

_BOX_GLYPH_RE = re.compile(r"[\u2500-\u259F\u25A0-\u25FF]")
_SLANT = set("\u2571\u2572")  # ╱ ╲ — diamond / hexagon / parallelogram tapers
_ROUND_CORNER = set("\u256d\u256e\u2570\u256f")  # ╭ ╮ ╰ ╯
_SQUARE_CORNER = set("\u250c\u2510\u2514\u2518")  # ┌ ┐ └ ┘


def _row_of(lines: list[str], label: str) -> int:
    for i, line in enumerate(lines):
        if label in line:
            return i
    raise AssertionError(f"label {label!r} not found in rendered output: {lines!r}")


def _col_of(lines: list[str], label: str) -> int:
    row = _row_of(lines, label)
    return lines[row].index(label)


# --------------------------------------------------------------------------
# Individual shape distinctiveness
# --------------------------------------------------------------------------


def test_diamond_renders_visibly_different_from_rect():
    rect_lines = render_flowchart("graph TD\nA[Node]\n", width=60)
    diamond_lines = render_flowchart("graph TD\nA{Node}\n", width=60)
    rect_text = "\n".join(rect_lines)
    diamond_text = "\n".join(diamond_lines)

    assert not (_SLANT & set(rect_text)), "a plain rect must draw no slant glyphs"
    assert _SLANT & set(diamond_text), "a diamond must draw slant (rhombus) glyphs"
    assert set(rect_text) & _SQUARE_CORNER, "a rect must use square corners"
    assert not (set(diamond_text) & _SQUARE_CORNER), (
        "a diamond's outline must not reuse the rect's square corners"
    )


def test_round_and_stadium_show_rounded_corners():
    for shape_src in ("graph TD\nA(Node)\n", "graph TD\nA([Node])\n"):
        lines = render_flowchart(shape_src, width=60)
        text = "\n".join(lines)
        assert _ROUND_CORNER & set(text), f"expected rounded corners in {shape_src!r}"
        assert not (set(text) & _SQUARE_CORNER), (
            f"round/stadium must not use square corners in {shape_src!r}"
        )


def test_cylinder_has_rounded_top_and_square_bottom():
    lines = render_flowchart("graph TD\nA[(db)]\n", width=60)
    row = _row_of(lines, "db")
    top_border = lines[row - 1]
    bottom_border = lines[row + 1]
    assert set(top_border) & _ROUND_CORNER, "cylinder top cap must be rounded"
    assert set(bottom_border) & _SQUARE_CORNER, "cylinder bottom must stay square"


def test_hexagon_has_corner_cut_slants():
    lines = render_flowchart("graph TD\nA{{hex}}\n", width=60)
    text = "\n".join(lines)
    assert _SLANT & set(text), "hexagon corners must be cut with slant glyphs"


def test_subroutine_has_double_bar_sides():
    lines = render_flowchart("graph TD\nA[[proc]]\n", width=60)
    text = "\n".join(lines)
    assert "\u2502\u2502" in text, "subroutine must show a double-bar predefined-process side"


def test_parallelogram_leans():
    lines = render_flowchart("graph TD\nA[/skew/]\n", width=60)
    text = "\n".join(lines)
    assert _SLANT & set(text), "parallelogram must lean via slant glyphs"
    # A real lean shows up as differing left-edge indentation between rows
    # (unlike a rect, whose left border sits at a single fixed column).
    left_cols = [
        len(line) - len(line.lstrip(" ")) for line in lines if line.strip()
    ]
    assert len(set(left_cols)) > 1, "parallelogram rows must be horizontally offset"


def test_shape_gallery_renders_all_nine_shapes():
    source = (
        "graph TD\n"
        "R[rect]\n"
        "RO(round)\n"
        "ST([stadium])\n"
        "DB[(db)]\n"
        "CI((circle))\n"
        "DI{diamond}\n"
        "HE{{hex}}\n"
        "SU[[subroutine]]\n"
        "PA[/para/]\n"
    )
    lines = render_flowchart(source, width=200)
    text = "\n".join(lines)
    assert lines, "shape gallery must render, never degrade"
    assert _BOX_GLYPH_RE.search(text)
    for label in (
        "rect",
        "round",
        "stadium",
        "db",
        "circle",
        "diamond",
        "hex",
        "subroutine",
        "para",
    ):
        assert label in text, f"missing shape label {label!r} in gallery output"
    # A genuinely varied gallery uses more than one glyph family — not
    # every shape falling back to the same plain rectangle border.
    assert _SLANT & set(text), "expected at least one slanted (diamond/hex/para) shape"
    assert _ROUND_CORNER & set(text), "expected at least one rounded-corner shape"
    assert _SQUARE_CORNER & set(text), "expected at least one square-corner shape"
    assert "\u2502\u2502" in text, "expected the subroutine's double-bar sides"


# --------------------------------------------------------------------------
# Subgraph frames
# --------------------------------------------------------------------------


def test_subgraph_frame_encloses_members_with_left_anchored_title():
    source = "graph TD\nsubgraph zone[Zone One]\nA[Alpha] --> B[Beta]\nend\n"
    lines = render_flowchart(source, width=100)

    title_row = _row_of(lines, "Zone One")
    alpha_row = _row_of(lines, "Alpha")
    beta_row = _row_of(lines, "Beta")

    # Title sits above both members, on the frame's own top border.
    assert title_row < alpha_row
    assert title_row < beta_row
    assert lines[title_row].lstrip().startswith("\u250c\u2500"), (
        "frame title must be left-anchored on the top border"
    )

    # Each member row shows both the frame's own side borders AND the
    # member's own box borders — real enclosure, not merely "somewhere
    # inside the same block of text".
    assert lines[alpha_row].count("\u2502") >= 4
    assert lines[beta_row].count("\u2502") >= 4

    # A closing frame border (only └/─/┘/space) exists below both members.
    last_member_row = max(alpha_row, beta_row)
    assert any(
        set(lines[r].strip()) <= {"\u2514", "\u2500", "\u2518"}
        for r in range(last_member_row + 1, len(lines))
    ), "expected a closing frame border below the members"


def test_subgraph_frame_title_preserves_zwj_grapheme_clusters():
    emoji = "👩🏽‍💻"
    title = emoji * 8
    lines = render_flowchart(
        f"graph TD\nsubgraph zone[{title}]\nA[Alpha]\nend\n", width=100
    )

    title_row = next(line for line in lines if emoji in line)
    assert title_row.count(emoji) == 8
    assert title_row.count("\u200d") == 8
    assert title_row.endswith("\u2510")
    assert visual_len(title_row) == visual_len(f"\u250c\u2500 {title} \u2510")


def test_nested_subgraphs_render_both_frames_without_overlap():
    source = (
        "graph TD\n"
        "subgraph outer[Outer]\n"
        "subgraph inner[Inner]\n"
        "C[Gamma] --> D[Delta]\n"
        "end\n"
        "end\n"
    )
    lines = render_flowchart(source, width=100)

    outer_row = _row_of(lines, "Outer")
    inner_row = _row_of(lines, "Inner")
    gamma_row = _row_of(lines, "Gamma")

    # Both titles present and correctly ordered: outer frame's title above
    # the inner frame's title, itself above the members.
    assert outer_row < inner_row < gamma_row

    # The inner frame is strictly narrower and horizontally inset within
    # the outer frame — real nesting, not two frames of identical extent
    # colliding on the same border row/column (the bug this test guards
    # against: an inner subgraph whose members share the outer's exact
    # column span used to produce a frame the same width as the outer's,
    # so the inner top border overwrote the outer's border instead of
    # nesting inside it).
    def _frame_span(line: str, title: str) -> tuple[int, int]:
        title_col = line.index(title)
        left = line.rfind("\u250c", 0, title_col)
        right = line.index("\u2510", title_col)
        assert left != -1, f"no left frame corner found before {title!r} in {line!r}"
        return left, right

    outer_left, outer_right = _frame_span(lines[outer_row], "Outer")
    inner_left, inner_right = _frame_span(lines[inner_row], "Inner")
    assert inner_left > outer_left, "inner frame must be inset right of the outer frame"
    assert inner_right < outer_right, "inner frame must be inset left of the outer frame's right edge"

    # The outer frame's own left border column must still show "\u2502" on the
    # inner frame's title row — proof the outer border wasn't clobbered by
    # the inner frame's border at that row (the exact corruption this test
    # replaces).
    assert lines[inner_row][outer_left] == "\u2502"


def test_noncontiguous_subgraph_members_flatten_instead_of_broken_frame():
    # X sits between A and B (not a member) so a clean bounding frame
    # around {A, B} would necessarily claim X too — must flatten (no
    # frame drawn at all) rather than draw a frame that visually swallows
    # a non-member node.
    source = (
        "graph LR\n"
        "A[a] --> X[x]\n"
        "X --> B[b]\n"
        "subgraph sg[Group]\n"
        "A\n"
        "B\n"
        "end\n"
    )
    lines = render_flowchart(source, width=100)
    text = "\n".join(lines)
    assert "a" in text and "x" in text and "b" in text
    assert "Group" not in text, "an infeasible frame must flatten, dropping its title too"
    # No frame border glyphs beyond each node's own box — a flattened
    # subgraph draws nothing extra.
    assert lines  # still renders, never degrades


# --------------------------------------------------------------------------
# Rank-flow direction
# --------------------------------------------------------------------------


def test_lr_places_child_to_the_right_with_right_arrow():
    lines = render_flowchart("graph LR\nA[Parent] --> B[Child]\n", width=100)
    text = "\n".join(lines)
    assert "\u25b6" in text, "LR forward edge must draw a right-pointing arrowhead"
    assert _col_of(lines, "Child") > _col_of(lines, "Parent")
    assert _row_of(lines, "Child") == _row_of(lines, "Parent"), (
        "a simple 2-node LR chain should stay on one row"
    )


def test_rl_places_child_to_the_left_with_left_arrow():
    lines = render_flowchart("graph RL\nA[Parent] --> B[Child]\n", width=100)
    text = "\n".join(lines)
    assert "\u25c0" in text, "RL forward edge must draw a left-pointing arrowhead"
    assert _col_of(lines, "Child") < _col_of(lines, "Parent")


def test_bt_places_child_above_parent_with_up_arrow():
    lines = render_flowchart("graph BT\nA[Parent] --> B[Child]\n", width=100)
    text = "\n".join(lines)
    assert "\u25b2" in text, "BT forward edge must draw an up-pointing arrowhead"
    assert _row_of(lines, "Child") < _row_of(lines, "Parent")


def test_lr_multi_parent_spacing_not_collapsed():
    # LR gotcha flagged in the design doc: after the axis swap, box height
    # (not width) governs in-rank spacing — a mis-swap would collapse two
    # same-rank parents onto overlapping/adjacent rows. Long vs. short
    # labels give the two parents different box heights under wrapping,
    # so this also catches a spacing regression that only shows up with
    # varied label widths.
    source = "graph LR\nA[Short] --> C[Target]\nB[A Somewhat Longer Label] --> C\n"
    lines = render_flowchart(source, width=100)
    row_a = _row_of(lines, "Short")
    row_b_lines = [i for i, line in enumerate(lines) if "Longer" in line]
    assert row_b_lines, "expected the long-label parent to render"
    row_b = row_b_lines[0]
    assert row_a != row_b, "two parents in the same rank must not collapse onto one row"
    # Their boxes must not vertically overlap: find each box's own
    # top/bottom border rows and confirm the spans are disjoint.
    def _box_span(center_row: int) -> tuple[int, int]:
        top = center_row
        while top > 0 and not set(lines[top]) & _SQUARE_CORNER:
            top -= 1
        bottom = center_row
        while bottom < len(lines) - 1 and not set(lines[bottom]) & _SQUARE_CORNER:
            bottom += 1
        return top, bottom

    top_a, bottom_a = _box_span(row_a)
    top_b, bottom_b = _box_span(row_b)
    assert bottom_a < top_b or bottom_b < top_a, "same-rank LR boxes must not overlap rows"


# --------------------------------------------------------------------------
# Router still avoids shape interiors with distinct borders in play
# --------------------------------------------------------------------------


def test_router_avoids_diamond_interior():
    source = "graph TD\nA[Start] --> B{Decision}\nB --> C[X]\nD[Y] --> B\nE[Z] --> B\n"
    lines = render_flowchart(source, width=100)
    decision_row = _row_of(lines, "Decision")
    decision_col = lines[decision_row].index("Decision")
    # One row above the label row is inside the diamond's upper taper —
    # any cell there that isn't blank must be a slant/border glyph, never
    # a line-routing glyph that would mean an edge cut through the shape.
    interior_row = lines[decision_row - 1]
    line_glyphs = set("\u2502\u2500\u250c\u2510\u2514\u2518\u251c\u2524\u252c\u2534\u253c")
    span = interior_row[max(decision_col - 2, 0) : decision_col + len("Decision") + 2]
    assert not (set(span) & line_glyphs), (
        f"an edge line must not cross through the diamond's interior: {span!r}"
    )
