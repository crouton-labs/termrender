from termrender import render


def test_leading_frontmatter_renders_as_metadata_box():
    source = """---
title: Example
tags:
  - alpha
  - beta
---

# Heading
"""

    output = render(source, width=40, color=False)

    assert output.startswith("┌─ metadata ")
    assert "│ title: Example" in output
    assert "│   - alpha" in output
    assert "│   - beta" in output
    assert "---" not in output
    assert "\nHeading" in output
