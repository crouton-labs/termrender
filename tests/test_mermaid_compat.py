import unittest

from termrender.renderers.mermaid import preprocess_mermaid_for_ascii


class TestMermaidPreprocessor(unittest.TestCase):

    def test_unknown_diagram_types_pass_through(self):
        src = "pie\n    \"A\" : 40\n    \"B\" : 60"
        self.assertEqual(preprocess_mermaid_for_ascii(src), src)

    def test_flowchart_plain_edges_pass_through(self):
        src = "flowchart TD\n    A-->B\n    B-->C"
        self.assertEqual(preprocess_mermaid_for_ascii(src), src)

    # Regression: mermaid-ascii (pinned master 6fffb8e) only parses ``[text]``
    # rectangle nodes — every other mermaid node shape leaked its raw delimiters
    # or bare node id into the rendered box (``B{Auth?}`` rendered the literal
    # ``B{Auth?}``; ``E[(Database)]`` rendered ``(Database)``). Node shapes are
    # still unsupported upstream (parseNode only handles rectangles), so we
    # normalize every shape to ``id[label]`` on our side.
    def test_flowchart_node_shapes_normalized_to_rectangles(self):
        src = (
            "graph LR\n"
            "    A[Client] --> B{Auth?}\n"
            "    B -->|Yes| C[Handler]\n"
            "    C --> E[(Database)]\n"
            "    F((Circle)) --> G([Stadium])\n"
            "    G --> H{{Hex}}\n"
            "    H --> I[[Sub]]\n"
            "    I --> J[/Para/]"
        )
        out = preprocess_mermaid_for_ascii(src)
        self.assertIn("B[Auth?]", out)
        self.assertIn("E[Database]", out)
        self.assertIn("F[Circle]", out)
        self.assertIn("G[Stadium]", out)
        self.assertIn("H[Hex]", out)
        self.assertIn("I[Sub]", out)
        self.assertIn("J[Para]", out)
        # Rectangle nodes and edge labels are untouched.
        self.assertIn("A[Client]", out)
        self.assertIn("|Yes|", out)
        # No raw alternate delimiters survive.
        for leak in ("{Auth?}", "[(", "((", "))", "{{", "}}", "[[", "]]"):
            self.assertNotIn(leak, out)

    def test_note_over_becomes_self_loop(self):
        src = "sequenceDiagram\n    participant A\n    participant B\n    Note over A: hello"
        out = preprocess_mermaid_for_ascii(src)
        self.assertIn("A->>A: 📝 hello", out)
        self.assertNotIn("Note over", out)

    def test_note_over_multi_participant_picks_first(self):
        src = "sequenceDiagram\n    participant A\n    participant B\n    Note over A,B: shared"
        out = preprocess_mermaid_for_ascii(src)
        self.assertIn("A->>A: 📝 shared", out)

    def test_note_left_and_right_of(self):
        src = (
            "sequenceDiagram\n"
            "    participant X\n"
            "    Note left of X: L\n"
            "    Note right of X: R"
        )
        out = preprocess_mermaid_for_ascii(src)
        self.assertIn("X->>X: 📝 L", out)
        self.assertIn("X->>X: 📝 R", out)

    def test_br_tags_flattened_in_note(self):
        src = "sequenceDiagram\n    participant A\n    Note over A: line1<br/>line2"
        out = preprocess_mermaid_for_ascii(src)
        self.assertIn("A->>A: 📝 line1 / line2", out)

    def test_br_tags_flattened_in_arrow_message(self):
        src = "sequenceDiagram\n    participant A\n    participant B\n    A->>B: a<br/>b<br />c"
        out = preprocess_mermaid_for_ascii(src)
        self.assertIn("A->>B: a / b / c", out)

    def test_arrow_variants_rewritten(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    A-xB: fail\n"
            "    A--xB: dashed fail\n"
            "    A-)B: async\n"
            "    A--)B: dashed async\n"
            "    A->B: single\n"
            "    A-->B: dashed single\n"
        )
        out = preprocess_mermaid_for_ascii(src)
        self.assertNotIn("-x", out)
        self.assertNotIn("-)", out)
        # Each single-dash variant should be solid ->>
        self.assertIn("A->>B: fail", out)
        self.assertIn("A->>B: async", out)
        self.assertIn("A->>B: single", out)
        # Each double-dash variant should be dashed -->>
        self.assertIn("A-->>B: dashed fail", out)
        self.assertIn("A-->>B: dashed async", out)
        self.assertIn("A-->>B: dashed single", out)

    def test_existing_double_arrow_preserved(self):
        src = "sequenceDiagram\n    participant A\n    participant B\n    A->>B: x\n    A-->>B: y"
        out = preprocess_mermaid_for_ascii(src)
        self.assertIn("A->>B: x", out)
        self.assertIn("A-->>B: y", out)
        # Should not have inflated to ->>>
        self.assertNotIn("->>>", out)
        self.assertNotIn("-->>>", out)

    def test_block_keywords_dropped(self):
        src = (
            "sequenceDiagram\n"
            "    participant A\n"
            "    participant B\n"
            "    activate A\n"
            "    loop forever\n"
            "    A->>B: x\n"
            "    end\n"
            "    deactivate A\n"
            "    autonumber\n"
            "    alt happy\n"
            "    A->>B: y\n"
            "    else sad\n"
            "    A->>B: z\n"
            "    end\n"
        )
        out = preprocess_mermaid_for_ascii(src)
        for dropped in ("activate", "deactivate", "loop", "end", "alt ", "else ", "autonumber"):
            self.assertNotIn(dropped, out.lower())
        # But arrow lines survive
        self.assertIn("A->>B: x", out)
        self.assertIn("A->>B: y", out)
        self.assertIn("A->>B: z", out)

    def test_participant_aliases_with_parens_preserved(self):
        src = (
            "sequenceDiagram\n"
            "    participant C1 as Core (PID 92348)\n"
            "    participant C2 as Core (PID 93684)\n"
            "    C1->>C2: x"
        )
        out = preprocess_mermaid_for_ascii(src)
        self.assertIn("participant C1 as Core (PID 92348)", out)
        self.assertIn("participant C2 as Core (PID 93684)", out)


if __name__ == "__main__":
    unittest.main()
