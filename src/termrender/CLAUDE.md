# termrender/src/termrender

## Layout: two-pass order is mandatory

`layout.py` runs `resolve_width()` then `resolve_height()` — this order is load-bearing. Height resolution calls `wrap_text(text, width)`, so every block must have `.width` set first. Reversing the order causes `block.width = None`, which silently falls back to `width = 1` (layout.py:77), drastically underestimating all heights.

## Mermaid: subprocess runs in layout, not in the renderer

`layout.py:119–134` runs `mermaid-ascii` and caches the result in `block.attrs["_rendered"]`. The `mermaid` renderer (renderers/mermaid.py) reads this cache key; if it's absent, it runs the subprocess again. A failed layout subprocess (tool missing, timeout) silently stores the raw source diagram in `_rendered`, so the renderer falls back to printing source — no error is raised. Both sites have a 30s timeout.

`layout.py` imports `fix_mermaid_encoding` from `renderers/mermaid.py` — the only reverse dependency from layout into renderers. Reorganizing `renderers/` must account for this import. The two subprocess call sites differ: layout uses `check=True` (non-zero exit raises `CalledProcessError` → caught → raw source fallback); the renderer omits `check` (non-zero exit silently reads `stdout`, which may be empty or partial). See `renderers/CLAUDE.md` for encoding-fix details.

## Directive nesting: depth counter, not stack entries

The parser tracks nested directives of the same type with a `depth` integer inside the top stack entry, not separate stack entries (parser.py:241–306). A closer `:::` only pops the stack when `depth == 1`; otherwise it decrements depth and treats the closer as body content. Consequence: innermost closers appear verbatim in the body of the parent and are re-parsed on the recursive `parse()` call at line 351.

Max recursion depth is 50; exceeding it raises `ValueError`, not `DirectiveError`. Both the render path and `--check` path in `__main__.py` catch `ValueError` and map it to exit code 2 (`EXIT_SYNTAX`).

## `--check` validates parse only, not layout

`__main__.py` `--check` calls `parse()` directly and exits — it never runs `layout.py`. Layout-time failures (mermaid subprocess missing, column percent overflow, `resolve_width`/`resolve_height` exceptions) pass `--check` cleanly but crash at render time. Use `--check` to catch directive syntax errors, not to guarantee a successful render.

## `_ambiguous_width` is global mutable state; `TERMRENDER_CJK` makes it permanent

`style.set_ambiguous_width(n)` (style.py:21–23) changes East Asian ambiguous-width measurement for the entire process with no reset function. The CLI `--cjk` flag sets `os.environ["TERMRENDER_CJK"]` rather than calling the function directly, so it persists for the entire process. `__init__.py:30–31` calls `set_ambiguous_width(2)` on every `render()` call when the env var is set — but since there's no reset, a single call in any render context permanently widens ambiguous-width for all subsequent renders in the same process. Affects `visual_len()` and therefore all wrapping and column math.

## Column width: explicit widths exceeding available space truncate auto-columns to 1

`layout.py:30–63`: explicit column widths (percent or absolute) are allocated first; remaining space is split among auto-width columns with `max(remaining, 0)`. Two columns each claiming 80% of a 100px terminal leaves auto-width columns with width 1 — no error, no proportional scaling.

## Height calculations with hidden assumptions

- **QUOTE** (layout.py:138): height gets `+1` only when the `author` or `by` attr is set. Using any other key (`attribution`, `source`) silently omits the extra line — the renderer's attribution line is clipped.
- **TABLE** (layout.py:117): `height = len(rows) + 4` where `rows` includes the header row. The code comment mis-describes this as 5 structural parts; `rows[0]` is the header. Adding a footer or subtitle row needs `+5`, not `+4+1`.
- **LIST_ITEM** (layout.py:107): text wraps at `max(width - 2, 1)`, hardcoding a 2-column indent. If the renderer changes the indent width, layout height and actual render height diverge silently.

## Character offset tracking across wrapped lines

`text.py:32–33`: after rendering each wrapped line, the offset advances by the line's length and then skips one character if the next character in the original plain text is a space (the space `wrap_text` consumed). If wrapping preserves trailing spaces, this skip is wrong and subsequent span styling shifts by one character.

## `wrap_text` measures in characters, not visual columns

`style.py:195–241`: all line-length comparisons inside `wrap_text` use `len()` (character count), not `visual_len()`. A 2-column-wide CJK character is counted as 1 column-unit, so wrapped lines silently overflow their allocated width by one cell per wide character. This affects every block type that calls `wrap_text`.

## Unknown directive names silently become PANEL

`parser.py:339`: `_DIRECTIVE_TO_BLOCK.get(name, BlockType.PANEL)` — any unrecognized `:::name` becomes a bordered PANEL block with no error or warning. Typos in directive names (e.g. `:::callOut`) produce visible output that looks correct but lacks the expected behavior (callout type, icon, color).

## `--tmux`: exit code reflects pane creation, auto-sizing runs a full render, tempfiles leak

`__main__.py:229`: after `tmux split-window` succeeds the parent exits `EXIT_OK` immediately — the pane renders asynchronously. Render errors surface only inside the pane. `--check` is silently dropped with `--tmux` (exit at line 229 precedes the `--check` branch at line 231). Tempfile cleanup is embedded as `... | less -R; rm -f <tmpfile>` (line 214); `less` killed abnormally (SIGKILL, closed session) leaks `/tmp/termrender-*.md`.

When `--width` is omitted, `--tmux` calls `render(source, width=80, color=False)` (lines 177–185) to measure content width — mermaid subprocesses fire and `TERMRENDER_CJK` mutations apply here. Any exception silently falls back to `pane_width=80`. The pane is capped to `tmux #{pane_width} - 10`; if the tmux query fails, no cap is applied. Minimum enforced pane width is 20.

## `_EMOJI_WIDE_RANGES` must stay sorted by codepoint

`_char_width()` (style.py:144) exits the range scan early on `cp < lo`, assuming all ranges are in ascending codepoint order. Adding a new range out of order causes the early exit to skip ranges with higher `lo` values, silently misclassifying those codepoints as 1-wide.
