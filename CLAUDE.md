# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

termrender renders directive-flavored markdown to ANSI terminal output. LLM agents describe layout with `:::directives` (panels, columns, trees, callouts, etc.) and termrender produces styled terminal output. Public API: `from termrender import render`.

## Commands

```bash
# Install in dev mode
pip install -e .

# Run tests
pytest tests/
pytest tests/test_column_alignment.py::TestColumnAlignment::test_showpiece_renders_without_error

# Run the CLI
python -m termrender <file.md>
echo ':::panel{title="Hi"}\nHello\n:::' | python -m termrender

# Build
python -m build
```

No linter or formatter is configured.

## Architecture

Three-stage pipeline: **parse → layout → emit**.

1. **Parse** (`parser.py`) — Two-pass: regex extracts `:::directives` first, then mistune v3 processes markdown segments. Produces a tree of `Block` dataclasses (`blocks.py`).
2. **Layout** (`layout.py`) — Two-pass, order is load-bearing: `resolve_width()` top-down, then `resolve_height()` bottom-up. Width must resolve first because height calls `wrap_text(text, width)`.
3. **Emit** (`emit.py`) — Walks the block tree and dispatches to renderer functions in `renderers/`.

Entry points:
- **Library**: `__init__.py:render()` — parse → layout → emit
- **CLI**: `__main__.py:main()` — argparse with `--width`, `--no-color`, `--check`, `--cjk`, `--tmux`. Exit codes: 0=ok, 1=input, 2=syntax, 3=terminal.

### Renderers (`src/termrender/renderers/`)

Two signatures (not type-enforced):
- **Leaf**: `render(block, color) -> list[str]` — divider, tree
- **Container**: `render(block, color, render_child) -> list[str]` — panel, quote, code, columns, callout, table, text, mermaid

`borders.py` is a shared utility, not a renderer. Its `render_box(content_lines, width, ...)` takes **total** width (including borders), not content width.

### Style (`style.py`)

`visual_len()` measures display width accounting for ANSI escapes, emoji, CJK, and combining marks. `wrap_text()` uses `len()` internally (known bug: CJK overflow). `_ambiguous_width` is global mutable state with no reset path — set via `set_ambiguous_width()` or `TERMRENDER_CJK` env var.

## Conventions

- **Commits**: conventional commits (`feat:`, `fix:`, `chore:`, etc.). `feat` → minor, `fix`/`perf` → patch. Auto-released via python-semantic-release on main.
- **Version**: derived from git tags via hatch-vcs (no version in pyproject.toml).
- **Python**: 3.10+.

## Supplementary CLAUDE.md files

- `src/termrender/CLAUDE.md` — parser, layout, mermaid, nesting, and `--check`/`--tmux` implementation gotchas
- `src/termrender/renderers/CLAUDE.md` — renderer contracts, `render_box` width semantics, EAW edge cases

Read these before modifying layout, parsing, or renderer code.
