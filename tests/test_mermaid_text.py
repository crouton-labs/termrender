"""Entity-code decoding in mermaid labels.

Regression: an author escaping ``<``/``>`` in a label (mermaid's documented
way to keep them out of the grammar) saw ``Record&lt;K, V&gt;`` drawn
verbatim inside the box instead of ``Record<K, V>``.
"""

from __future__ import annotations

from termrender.renderers.mermaid_flow_parser import parse
from termrender.renderers.mermaid_sequence import render_sequence
from termrender.renderers.mermaid_text import decode_entities


def _node(g, node_id):
    return next(n for n in g.nodes if n.id == node_id)


def test_decodes_html_and_hash_forms():
    assert decode_entities("Record&lt;K, V&gt;") == "Record<K, V>"
    assert decode_entities("a #quot;quoted#quot; word") == 'a "quoted" word'
    assert decode_entities("&#35; and #x2b;") == "# and +"


def test_leaves_incomplete_or_unknown_codes_alone():
    # No semicolon, no decode — unlike html.unescape, which yields "¶ms".
    assert decode_entities("&params") == "&params"
    assert decode_entities("R&D &nope; see lt;") == "R&D &nope; see lt;"


def test_node_and_edge_labels_decode():
    g = parse('flowchart LR\n  A["Record&lt;K, V&gt;"] -->|"a &amp; b"| B')
    assert _node(g, "A").label == "Record<K, V>"
    assert g.edges[0].label == "a & b"


def test_decoding_cannot_forge_structure():
    # A decoded arrow/separator inside a quoted label stays label text.
    g = parse('flowchart LR\n  A["x --&gt; y &amp; z"] --> B')
    assert _node(g, "A").label == "x --> y & z"
    assert {n.id for n in g.nodes} == {"A", "B"}


def test_sequence_participant_and_message_decode():
    lines = render_sequence(
        "sequenceDiagram\n  participant A as Map&lt;K,V&gt;\n  A->>A: get(#quot;k#quot;)",
        80,
    )
    joined = "\n".join(lines)
    assert "Map<K,V>" in joined
    assert 'get("k")' in joined
