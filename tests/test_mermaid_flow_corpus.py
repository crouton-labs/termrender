"""Golden-output corpus for the native mermaid flowchart renderer.

Companion to ``test_mermaid_flow.py`` (topology/edge-routing/degradation)
and ``test_mermaid_flow_shapes.py`` (shape/frame/direction geometry
properties). Those two assert *properties* of the rendered output — real
but tolerant of incidental layout drift. This module pins the **exact**
rendered lines for a curated, representative set of inputs so a future
regression shows up as a visible diff in a human-readable golden string,
not merely as "some property broke".

Coverage span (see the module for the full enumerated list, matching the
flowchart renderer's requirements doc "Golden-output test corpus" section):
each of the 9 node shapes, each edge style (solid/dotted/thick, headless,
bidirectional), both label forms, ``&`` fan-out, a multi-parent DAG, a
cycle with a labeled back-edge (the case that panics the vendored Go
binary), LR vs TD of the same graph, a subgraph and a nested subgraph, a
long label against a tight width budget, and the two degradation paths
(malformed input, empty-body headed diagram).

Where geometry is genuinely stable (small, deterministic graphs — no
crossing-minimization ambiguity), the golden is the full exact line list.
Where a case is inherently noisier (fan-out ordering, dense multi-edge
layouts) the corpus still pins the exact golden here because
``render_flowchart`` is a pure, deterministic function of its input (no
randomness anywhere in the parser/adapter/router) — golden strings were
captured directly from the renderer's own output and are re-verified by
these tests on every run, exactly like a snapshot test.
"""

from __future__ import annotations

import re

from termrender.renderers.mermaid_flow import render_flowchart
from termrender.style import visual_len

_BOX_GLYPH_RE = re.compile(r"[\u2500-\u259F\u25A0-\u25FF]")


def _lines(source: str, width: int = 60) -> list[str]:
    return render_flowchart(source, width)


# --------------------------------------------------------------------------
# Node shapes — one small graph per shape, exact golden
# --------------------------------------------------------------------------


def test_shape_rect_golden():
    assert _lines("graph TD\nA[rect]\n") == [
        "┌──────┐",
        "│ rect │",
        "└──────┘",
    ]


def test_shape_round_golden():
    assert _lines("graph TD\nA(round)\n") == [
        "╭───────╮",
        "│ round │",
        "╰───────╯",
    ]


def test_shape_stadium_golden():
    assert _lines("graph TD\nA([stadium])\n") == [
        "╭─────────╮",
        "│ stadium │",
        "╰─────────╯",
    ]


def test_shape_cylinder_golden():
    assert _lines("graph TD\nA[(db)]\n") == [
        "╭────╮",
        "│ db │",
        "└────┘",
    ]


def test_shape_circle_golden():
    assert _lines("graph TD\nA((circle))\n") == [
        "╭────────────╮",
        "│   circle   │",
        "╰────────────╯",
    ]


def test_shape_diamond_golden():
    assert _lines("graph TD\nA{diamond}\n") == [
        "  ╱     ╲",
        " ╱       ╲",
        "│ diamond │",
        " ╲       ╱",
        "  ╲     ╱",
    ]


def test_shape_hexagon_golden():
    assert _lines("graph TD\nA{{hex}}\n") == [
        " ╱─────╲",
        "│  hex  │",
        " ╲─────╱",
    ]


def test_shape_subroutine_golden():
    assert _lines("graph TD\nA[[sub]]\n") == [
        "┌───────┐",
        "││ sub ││",
        "└───────┘",
    ]


def test_shape_parallelogram_golden():
    assert _lines("graph TD\nA[/para/]\n") == [
        "  ╱──────╱",
        " ╱ para ╱",
        "╱──────╱",
    ]


# --------------------------------------------------------------------------
# Edge styles — solid/dotted/thick, headless, bidirectional
# --------------------------------------------------------------------------


def test_edge_style_solid_arrow_golden():
    assert _lines("graph TD\nA-->B\n") == [
        "┌───┐",
        "│ A │",
        "└───┘",
        "  │",
        "  │",
        "┌─▼─┐",
        "│ B │",
        "└───┘",
    ]


def test_edge_style_solid_headless_golden():
    assert _lines("graph TD\nA---B\n") == [
        "┌───┐",
        "│ A │",
        "└───┘",
        "  │",
        "  │",
        "┌───┐",
        "│ B │",
        "└───┘",
    ]


def test_edge_style_dotted_arrow_golden():
    assert _lines("graph TD\nA-.->B\n") == [
        "┌───┐",
        "│ A │",
        "└───┘",
        "  ╎",
        "  ╎",
        "┌─▼─┐",
        "│ B │",
        "└───┘",
    ]


def test_edge_style_thick_arrow_golden():
    assert _lines("graph TD\nA==>B\n") == [
        "┌───┐",
        "│ A │",
        "└───┘",
        "  ┃",
        "  ┃",
        "┌─▼─┐",
        "│ B │",
        "└───┘",
    ]


def test_edge_style_bidirectional_golden():
    assert _lines("graph TD\nA<-->B\n") == [
        "┌───┐",
        "│ A │",
        "└─▲─┘",
        "  │",
        "  │",
        "┌─▼─┐",
        "│ B │",
        "└───┘",
    ]


# --------------------------------------------------------------------------
# Edge labels — |label| and inline `-- text -->` forms
# --------------------------------------------------------------------------


def test_pipe_label_golden():
    # The rank-band gap widens past the unlabeled _ROW_GAP to a small
    # constant (see mermaid_flow_layout._LABELED_ROW_GAP) so the label gets
    # its own clear row — the constant does not scale with the label's
    # text length.
    assert _lines("graph TD\nA-->|hi|B\n") == [
        "┌───┐",
        "│ A │",
        "└───┘",
        "  │",
        " hi",
        "  │",
        "┌─▼─┐",
        "│ B │",
        "└───┘",
    ]


def test_inline_label_golden():
    # Same constant rank-band gap as above — "go now" is longer than "hi"
    # but the vertical gap stays the same _LABELED_ROW_GAP; only the
    # label's own row is wider.
    assert _lines("graph TD\nA -- go now --> B\n") == [
        "┌───┐",
        "│ A │",
        "└───┘",
        "  │",
        "go now",
        "  │",
        "┌─▼─┐",
        "│ B │",
        "└───┘",
    ]


# --------------------------------------------------------------------------
# `&` fan-out — A & B --> C & D expands to four edges
# --------------------------------------------------------------------------


def test_fan_out_golden():
    assert _lines("graph TD\nA & B --> C & D\n") == [
        "┌───┐   ┌───┐",
        "│ B │   │ A │",
        "└───┘   └───┘",
        "  ├───────┤",
        "  │       │",
        "┌─▼─┐   ┌─▼─┐",
        "│ C │   │ D │",
        "└───┘   └───┘",
    ]


# --------------------------------------------------------------------------
# Multi-parent DAG — two parents, one shared child, both edges attach
# --------------------------------------------------------------------------


def test_multi_parent_dag_golden():
    assert _lines("graph TD\nA-->C\nB-->C\n") == [
        "┌───┐   ┌───┐",
        "│ B │   │ A │",
        "└───┘   └───┘",
        "  └───┬───┘",
        "      │",
        "    ┌─▼─┐",
        "    │ C │",
        "    └───┘",
    ]


# --------------------------------------------------------------------------
# Cycle with a labeled back-edge — a known-tricky layout case for the renderer
# --------------------------------------------------------------------------


def test_labeled_back_edge_cycle_golden():
    lines = _lines("graph TD\nA-->B\nB-->C\nC-->|retry|A\n")
    assert lines == [
        "    ┌───┐",
        "    │ A ◀─┐",
        "    └───┘ │",
        "  ┌───┘   │",
        "  │       │",
        "┌─▼─┐     │",
        "│ B │   retry",
        "└───┘     │",
        "  └───┐   │",
        "      │   │",
        "    ┌─▼─┐ │",
        "    │ C │─┘",
        "    └───┘",
    ]
    text = "\n".join(lines)
    # Belt-and-suspenders topology assertions alongside the golden: every
    # box present, the label present, and an arrowhead landing on A (the
    # back-edge's destination) — the layout shape this case must produce.
    for label in ("A", "B", "C"):
        assert label in text
    assert "retry" in text
    assert "\u25c0" in text  # ◀ arrowhead into A


def test_labeled_back_edge_cycle_chained_form_golden():
    """Same cycle as `test_labeled_back_edge_cycle_golden`, but the two
    forward edges are written as one chained statement (`A-->B-->C`)
    instead of two separate lines — must render identically, proving the
    chained-edge parser fix preserves the pinned topology/layout."""
    lines = _lines("graph TD\nA-->B-->C\nC-->|retry|A\n")
    assert lines == [
        "    \u250c\u2500\u2500\u2500\u2510",
        "    \u2502 A \u25c0\u2500\u2510",
        "    \u2514\u2500\u2500\u2500\u2518 \u2502",
        "  \u250c\u2500\u2500\u2500\u2518   \u2502",
        "  \u2502       \u2502",
        "\u250c\u2500\u25bc\u2500\u2510     \u2502",
        "\u2502 B \u2502   retry",
        "\u2514\u2500\u2500\u2500\u2518     \u2502",
        "  \u2514\u2500\u2500\u2500\u2510   \u2502",
        "      \u2502   \u2502",
        "    \u250c\u2500\u25bc\u2500\u2510 \u2502",
        "    \u2502 C \u2502\u2500\u2518",
        "    \u2514\u2500\u2500\u2500\u2518",
    ]
    text = "\n".join(lines)
    for label in ("A", "B", "C"):
        assert label in text
    assert "retry" in text
    assert "\u25c0" in text


# --------------------------------------------------------------------------
# LR vs TD of the same graph
# --------------------------------------------------------------------------


def test_td_direction_golden():
    assert _lines("graph TD\nA-->B\nA-->C\n") == [
        "    ┌───┐",
        "    │ A │",
        "    └───┘",
        "  ┌───┴───┐",
        "  │       │",
        "┌─▼─┐   ┌─▼─┐",
        "│ B │   │ C │",
        "└───┘   └───┘",
    ]


def test_lr_direction_golden():
    assert _lines("graph LR\nA-->B\nA-->C\n") == [
        "       ┌───┐",
        "     ┌─▶ B │",
        "     │ └───┘",
        "┌───┐│",
        "│ A │┤",
        "└───┘│",
        "     │ ┌───┐",
        "     └─▶ C │",
        "       └───┘",
    ]


# --------------------------------------------------------------------------
# LR fan-out with 2 labeled edges — both labels must survive (regression:
# a shared exit anchor used to make the two edges' first segments tie for
# "longest straight run", so the second label silently overwrote nothing
# and just never appeared — see mermaid_flow_layout.py's
# _longest_segment/_allocate_edge_anchors docstrings)
# --------------------------------------------------------------------------


def test_lr_fan_out_with_labels_both_present_golden():
    lines = _lines(
        "flowchart LR\n"
        "    A{check} -->|yes| B[Approved]\n"
        "    A -->|no| C[Rejected]\n"
    )
    assert lines == [
        "              \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510",
        "           yes\u25b6 Approved \u2502",
        "  \u2571   \u2572    \u2502  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518",
        " \u2571     \u2572   \u2502",
        "\u2502 check \u2502\u2500\u2500\u2524",
        " \u2572     \u2571   \u2502",
        "  \u2572   \u2571    \u2502  \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510",
        "           no\u2500\u25b6 Rejected \u2502",
        "              \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518",
    ]
    text = "\n".join(lines)
    assert "yes" in text and "no" in text


# --------------------------------------------------------------------------
# Subgraph and nested subgraph
# --------------------------------------------------------------------------


def test_subgraph_frame_golden():
    assert _lines("graph TD\nsubgraph zone[Zone]\nA-->B\nend\n") == [
        "┌─ Zone ┐",
        "│       │",
        "│ ┌───┐ │",
        "│ │ A │ │",
        "│ └───┘ │",
        "│   │   │",
        "│   │   │",
        "│ ┌─▼─┐ │",
        "│ │ B │ │",
        "│ └───┘ │",
        "│       │",
        "└───────┘",
    ]


def test_nested_subgraph_golden():
    source = (
        "graph TD\n"
        "subgraph outer[Outer]\n"
        "subgraph inner[Inner]\n"
        "C-->D\n"
        "end\n"
        "end\n"
    )
    assert _lines(source) == [
        "┌─ Outer ────┐",
        "│            │",
        "│ ┌─ Inner ┐ │",
        "│ │        │ │",
        "│ │ ┌───┐  │ │",
        "│ │ │ C │  │ │",
        "│ │ └───┘  │ │",
        "│ │   │    │ │",
        "│ │   │    │ │",
        "│ │ ┌─▼─┐  │ │",
        "│ │ │ D │  │ │",
        "│ │ └───┘  │ │",
        "│ │        │ │",
        "│ └────────┘ │",
        "│            │",
        "└────────────┘",
    ]


# --------------------------------------------------------------------------
# Long label vs a tight width budget
# --------------------------------------------------------------------------


def test_long_label_vs_tight_width_golden():
    # The label's natural 20-cell wrap budget would render 24 cells wide;
    # the width-fitting loop narrows the budget until the diagram fits the
    # 20-cell request, without dropping a character of the label.
    source = "graph TD\nA[This is quite a very long label indeed]-->B[short]\n"
    assert _lines(source, width=20) == [
        "┌─────────────────┐",
        "│ This is quite a │",
        "│ very long label │",
        "│     indeed      │",
        "└─────────────────┘",
        "         │",
        "         │",
        "     ┌───▼───┐",
        "     │ short │",
        "     └───────┘",
    ]


def test_wide_lr_chain_fits_width_without_losing_content_or_direction():
    # A wide LR chain of long-labeled nodes wants 90 cells at its natural
    # label budget; it must compact into a narrower terminal by wrapping
    # labels harder, keeping every box, the LR direction, and every word.
    source = (
        "flowchart LR\n"
        "  A[Collect raw telemetry events] --> B[Normalize and enrich records]\n"
        "  B --> C[Detect anomalous behaviour patterns]\n"
        "  C --> D[Notify on-call responder team]\n"
    )
    labels = [
        "Collect raw telemetry events",
        "Normalize and enrich records",
        "Detect anomalous behaviour patterns",
        "Notify on-call responder team",
    ]
    words = [w for label in labels for w in label.split()]
    for width in (60, 120):
        lines = _lines(source, width=width)
        assert max(visual_len(line) for line in lines) <= width
        # Topology and content survive the compaction: four boxes, still on
        # one LR row (each box's top border on the same line as its
        # neighbours' would be for TB stacking, so count corners per line),
        # and every label word still present somewhere in the output.
        text = "".join(lines)
        assert text.count("┌") == 4
        assert max(line.count("┌") for line in lines) > 1, "LR row was rotated"
        squashed = re.sub(r"[^0-9A-Za-z-]+", "", text)
        for word in words:
            assert word in squashed


def test_wide_glyph_labels_fit_width_and_stay_inside_their_boxes():
    # Compaction is measured in display columns, not code points: CJK and
    # ZWJ emoji labels must wrap and draw by the cells they actually occupy
    # without splitting a grapheme cluster or losing its joiner.
    emoji = "👩🏽‍💻"
    source = (
        "flowchart LR\n"
        "  A[" + "\u754c" * 16 + emoji * 4 + "] --> B[" + emoji * 4 + "\u754c" * 16 + "]\n"
    )
    lines = _lines(source, width=60)
    text = "".join(lines)
    assert visual_len(emoji) == 2
    assert max(visual_len(line) for line in lines) <= 60
    border_w = {visual_len(line) for line in lines if "\u250c" in line}
    assert len(border_w) == 1
    assert all(visual_len(line) <= max(border_w) for line in lines)
    assert text.count("\u754c") == 32
    assert text.count(emoji) == 8
    assert text.count("\u200d") == 8


# --------------------------------------------------------------------------
# Degradation contract — malformed input and empty-body headed diagram
# --------------------------------------------------------------------------


def test_malformed_input_preserves_source_with_no_box_glyphs():
    lines = _lines("not a diagram\njust some text\n")
    assert lines == [
        "mermaid error: not a mermaid flowchart: source must start with "
        "'graph' or 'flowchart'",
        "not a diagram",
        "just some text",
    ]
    assert not _BOX_GLYPH_RE.search("\n".join(lines))


def test_empty_body_headed_diagram_echoes_with_no_box_glyphs():
    lines = _lines("graph TD\n%% just a comment, no nodes\n")
    assert lines == ["graph TD", "%% just a comment, no nodes"]
    assert not _BOX_GLYPH_RE.search("\n".join(lines))
