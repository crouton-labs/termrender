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
    # The rank-band gap widens to fit the label in full (see
    # mermaid_flow_layout._rank_gap_overrides) — a 2-char label needs a
    # taller gap than the base _ROW_GAP alone provides.
    assert _lines("graph TD\nA-->|hi|B\n") == [
        "┌───┐",
        "│ A │",
        "└───┘",
        "  │",
        " hi",
        "  │",
        "  │",
        "┌─▼─┐",
        "│ B │",
        "└───┘",
    ]


def test_inline_label_golden():
    # Same rank-band widening as above, scaled to the longer "go now" label.
    assert _lines("graph TD\nA -- go now --> B\n") == [
        "┌───┐",
        "│ A │",
        "└───┘",
        "  │",
        "  │",
        "  │",
        "go now",
        "  │",
        "  │",
        "  │",
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
# Cycle with a labeled back-edge — the exact case that panics the Go binary
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
    # back-edge's destination) — the exact shape the Go binary panics on.
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
    source = "graph TD\nA[This is quite a very long label indeed]-->B[short]\n"
    assert _lines(source, width=20) == [
        "┌──────────────────────┐",
        "│ This is quite a very │",
        "│  long label indeed   │",
        "└──────────────────────┘",
        "            │",
        "            │",
        "        ┌───▼───┐",
        "        │ short │",
        "        └───────┘",
    ]


# --------------------------------------------------------------------------
# Degradation contract — malformed input and empty-body headed diagram
# --------------------------------------------------------------------------


def test_malformed_input_echoes_with_no_box_glyphs():
    lines = _lines("not a diagram\njust some text\n")
    assert lines == ["not a diagram", "just some text"]
    assert not _BOX_GLYPH_RE.search("\n".join(lines))


def test_empty_body_headed_diagram_echoes_with_no_box_glyphs():
    lines = _lines("graph TD\n%% just a comment, no nodes\n")
    assert lines == ["graph TD", "%% just a comment, no nodes"]
    assert not _BOX_GLYPH_RE.search("\n".join(lines))
