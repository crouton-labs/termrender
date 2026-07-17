"""Regression tests for native Mermaid ``gitGraph`` rendering."""

from termrender.renderers.mermaid import render_mermaid_lines


def test_gitgraph_renders_commit_ids_and_tags_as_a_commit_graph():
    source = """gitGraph
    commit id: "9573dac base"
    commit id: "image/version cleanup"
    commit id: "REPLACE tooling"
    commit id: "b5dc36e one-tag image swap" tag: "origin integration"
    commit id: "17 WFP commits"
    commit id: "d40f0f4 reviewed head" tag: "local WFP"
"""

    output = "\n".join(render_mermaid_lines(source, 80))

    assert "●─ 9573dac base" in output
    assert "b5dc36e one-tag image swap  [origin integration]" in output
    assert "d40f0f4 reviewed head  [local WFP]" in output
    assert "commit id:" not in output
    assert "│" in output


def test_gitgraph_shows_branch_and_merge_lanes():
    source = """gitGraph
    commit id: "root"
    branch feature
    checkout feature
    commit id: "work"
    checkout main
    merge feature id: "merge work"
"""

    output = "\n".join(render_mermaid_lines(source, 80))

    assert "├─ feature" in output
    assert "│  ●─ work" in output
    assert "●  ╲─ merge work" in output
