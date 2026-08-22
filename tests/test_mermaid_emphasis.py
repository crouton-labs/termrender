"""Inline emphasis tags in mermaid labels.

Regression: a label using mermaid's own supported emphasis markup
(``A["what you author<br/><b>dialect</b>"]``) drew the tags verbatim inside
the box instead of bolding the text. The tags are markup, not content, so
they must become ANSI styling under ``--color on``, vanish entirely under
``--color off``, and \u2014 costing no display columns either way \u2014 never change
the box the label is sized into.
"""

from __future__ import annotations

from termrender.blocks import Block, BlockType
from termrender.renderers.mermaid import render as render_mermaid
from termrender.renderers.mermaid_flow import render_flowchart
from termrender.renderers.mermaid_flow_layout import _wrap_label
from termrender.renderers.mermaid_flow_parser import parse
from termrender.renderers.mermaid_text import apply_emphasis
from termrender.style import ANSI_RE, BOLD, ITALIC, RESET, active_sgr, visual_len

_SRC = 'flowchart LR\n  A["what you author<br/><b>dialect</b>"] --> B["jsx"]'


def _node(g, node_id):
    return next(n for n in g.nodes if n.id == node_id)


def _render(source: str, width: int, color: bool) -> list[str]:
    block = Block(type=BlockType.MERMAID, attrs={"source": source})
    block.width = width
    return render_mermaid(block, color)


def test_apply_emphasis_styles_the_supported_tags():
    assert apply_emphasis("<b>x</b>") == f"{BOLD}x{RESET}"
    assert apply_emphasis("<strong>x</strong>") == f"{BOLD}x{RESET}"
    assert apply_emphasis("<i>x</i>") == f"{ITALIC}x{RESET}"
    assert apply_emphasis("<EM>x</em>") == f"{ITALIC}x{RESET}"


def test_apply_emphasis_nests_and_self_closes():
    assert apply_emphasis("<b>a<i>b</i>c</b>") == (
        f"{BOLD}a{ITALIC}b{RESET}{BOLD}c{RESET}"
    )
    # Left open by the author, closed by us; a stray close is dropped.
    assert apply_emphasis("<b>a") == f"{BOLD}a{RESET}"
    assert apply_emphasis("a</b>") == "a"
    # An empty pair yields nothing at all, not a zero-width styled run.
    assert apply_emphasis("<b></b>") == ""


def test_apply_emphasis_leaves_other_markup_alone():
    # Not markup this renderer claims to understand.
    assert apply_emphasis("<span>x</span>") == "<span>x</span>"
    assert apply_emphasis("<br/>") == "<br/>"


def test_escaped_tags_stay_literal():
    # The author escaped the tag deliberately: emphasis runs before entity
    # decoding, so the decoded text is content, not markup.
    g = parse('flowchart LR\n  A["&lt;b&gt;escaped&lt;/b&gt;"] --> B')
    assert _node(g, "A").label == "<b>escaped</b>"


def test_node_and_edge_labels_style():
    g = parse('flowchart LR\n  A["<b>node</b>"] -->|"<i>edge</i>"| B')
    assert _node(g, "A").label == f"{BOLD}node{RESET}"
    assert g.edges[0].label == f"{ITALIC}edge{RESET}"


def test_tags_never_reach_the_screen_and_bold_does():
    on = "\n".join(_render(_SRC, 60, color=True))
    assert "<b>" not in on and "</b>" not in on
    assert f"{BOLD}dialect{RESET}" in on


def test_color_off_leaves_clean_unstyled_text():
    off = "\n".join(_render(_SRC, 60, color=False))
    assert "\x1b" not in off
    assert "<b>" not in off and "dialect" in off


def test_geometry_is_measured_from_the_visible_text():
    # `<b>dialect</b>` is 14 source characters and 7 visible ones: measuring
    # the styled string would widen every box holding an emphasized label.
    styled = _render(_SRC, 60, color=False)
    plain = _render(_SRC.replace("<b>", "").replace("</b>", ""), 60, color=False)
    assert styled == plain
    # ...and turning color on changes nothing but the escapes.
    on = _render(_SRC, 60, color=True)
    assert [ANSI_RE.sub("", line) for line in on] == styled


def test_emphasized_wide_glyphs_keep_their_columns():
    # A styled CJK label is the case where counting escapes as glyphs and
    # measuring cells wrong both show up at once.
    lines = render_flowchart('flowchart LR\n  A["日本語<b>太字</b>です"] --> B["x"]', 40)
    box = [line for line in lines if BOLD in line]
    assert box and f"{BOLD}太字{RESET}" in box[0]
    plain = render_flowchart('flowchart LR\n  A["日本語太字です"] --> B["x"]', 40)
    assert [ANSI_RE.sub("", line) for line in lines] == plain


def test_styling_survives_a_hard_word_break():
    # No space to wrap at, so the break lands mid-run: the tail line has to
    # re-open the style whose opening escape stayed on the head line, and
    # not one character may be lost to the break.
    label = "<b>Supercalifragilistic<i>expialidocious</i></b>"
    lines = _wrap_label(apply_emphasis(label), 18)
    assert len(lines) > 1
    assert "".join(ANSI_RE.sub("", line) for line in lines) == (
        "Supercalifragilisticexpialidocious"
    )
    assert all(line.startswith("\x1b") for line in lines), "every line re-opens"
    # ...and once drawn, no row leaves styling active to bleed onto a border.
    for row in render_flowchart(f'flowchart LR\n  A["{label}"] --> B["x"]', 30):
        assert active_sgr(row) == ""


def test_emphasized_edge_label_wraps_without_leaking():
    # Edge labels take the fit ladder's own wrap budget, a separate path
    # from a node label's.
    lines = render_flowchart(
        'flowchart LR\n  A -->|"<b>a rather long emphasized edge label</b>"| B',
        34,
    )
    joined = "\n".join(lines)
    assert "<b>" not in joined and BOLD in joined
    for row in lines:
        assert active_sgr(row) == ""


def test_styling_survives_wrapping():
    label = "<b>the renderer keeps emphasis alive across a wrap</b>"
    lines = render_flowchart(f'flowchart TD\n  A["{label}"] --> B["tail"]', 40)
    styled_rows = [line for line in lines if BOLD in line]
    assert len(styled_rows) >= 2, "label must wrap for this to test anything"
    for row in styled_rows:
        # Each row re-opens and closes its own styling, so no escape is
        # sliced across rows and none bleeds onto a border.
        assert active_sgr(row) == ""
        assert row.rstrip().endswith("\u2502")
    # Every row of the box is the same visible width as its border.
    border_w = visual_len(lines[0])
    assert all(visual_len(line) == border_w for line in styled_rows)
