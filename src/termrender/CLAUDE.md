# termrender/src/termrender

## Layout: two-pass order is mandatory

`layout.py` runs `resolve_width()` then `resolve_height()` — this order is load-bearing. Height resolution calls `wrap_text(text, width)`, so every block must have `.width` set first. Reversing the order causes `block.width = None`, which silently falls back to `width = 1` (layout.py:77), drastically underestimating all heights.

## Mermaid: subprocess runs in layout, not in the renderer

`layout.py:119–134` runs `mermaid-ascii` and caches the result in `block.attrs["_rendered"]`. The `mermaid` renderer (renderers/mermaid.py) reads this cache key; if it's absent, it runs the subprocess again. A failed layout subprocess (tool missing, timeout) silently stores the raw source diagram in `_rendered`, so the renderer falls back to printing source — no error is raised. Both sites have a 30s timeout.

`layout.py` imports `fix_mermaid_encoding` and `preprocess_mermaid_for_ascii` from `renderers/mermaid.py` — the only reverse dependency from layout into renderers. Reorganizing `renderers/` must account for these imports. The two subprocess call sites differ: layout uses `check=True` (non-zero exit raises `CalledProcessError` → caught → raw source fallback); the renderer omits `check` (non-zero exit silently reads `stdout`, which may be empty or partial). See `renderers/CLAUDE.md` for encoding-fix details.

`preprocess_mermaid_for_ascii` rewrites sequence diagrams into the subset `mermaid-ascii` parses (it only supports `->>` / `-->>` arrows, `participant`, and self-loops). `Note over|left of|right of X[,Y]: msg` becomes a self-loop `X->>X: 📝 msg`; `->`, `-x`, `--x`, `-)`, `--)`, and bare `-->` are mapped to `->>`/`-->>`; block keywords (`loop`/`alt`/`opt`/`par`/`critical`/`break`/`rect`/`activate`/`deactivate`/`autonumber`/`else`/`and`/`end`) are dropped so the inner arrow lines still render; `<br/>` is flattened to ` / `. Non-sequence diagrams (`flowchart`, `graph`, etc.) pass through unchanged. Semantics are lossy by design — `-x` (fail arrow) renders as a plain arrow, and block scoping is lost — but the flow diagram renders instead of silently degrading to raw source.

## Directive nesting: outer must have more colons than inner

The parser handles two directive syntaxes through different passes: colon directives (`:::name`) are extracted in pass 1 via regex in `_split_directives`, while backtick fence directives (`` ```{name} ``) are resolved in pass 2 via mistune's AST walk in `_convert_ast`. Both paths funnel through `_directive_to_block` for block construction.

For colon directives, closers are paired strictly by colon count. A closer whose colon count differs from the open directive's colon count is treated as body content; the recursive `parse()` call inside `_directive_to_block` re-parses it as an inner directive. This matches the standard rule used by MyST, Pandoc fenced divs, markdown-it-container, and CommonMark fenced code blocks: outer fences must use strictly more colons than the inner fences they wrap, making opener/closer pairing unambiguous.

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

`__main__.py:357`: after `tmux split-window` succeeds the parent exits `EXIT_OK` immediately — the pane renders asynchronously. Render errors surface only inside the pane. `--check` is silently dropped with `--tmux` (exit at line 357 precedes the `--check` branch at line 368), even though `--tmux` now runs its own `parse()` call (lines 253–266) for fail-fast syntax validation before spawning the pane. The `--check` "ok" message and exit-code contract are not honoured.

Tempfile cleanup is embedded as `... | less -R; rm -f <tmpfile>` (line 339); `less` killed abnormally (SIGKILL, closed session) leaks `/tmp/termrender-*.md`. `--tmux --watch` skips tempfile creation entirely — the pane is pointed at the real file path, so no leak.

When `--width` is omitted, `--tmux` calls `render(source, width=80, color=False)` (lines 283–290) to measure content width — mermaid subprocesses fire and `TERMRENDER_CJK` mutations apply here. Any exception silently falls back to `pane_width=80`. The pane is capped to `tmux #{pane_width} - 10`; if the tmux query fails, no cap is applied. Minimum enforced pane width is 20.

## `--watch`: re-renders on resize as well as file change; errors are inline, not fatal

`_watch_loop` (lines 99–169) polls `os.path.getmtime` every 0.2 s and also re-renders when `shutil.get_terminal_size()` changes — so a terminal resize triggers a re-render even with no file edit. `width=None` is passed to `render()` each cycle, so auto-detection always uses current pane width.

The loop catches bare `Exception` (line 142) to keep the watcher alive across render errors; errors appear as a one-line message in the pane, not as an exit. `DirectiveError`, `TerminalError`, and `ValueError` (nesting depth) are each caught separately with distinct prefixes for that same reason — the watcher never exits on render failure, only on `KeyboardInterrupt`.

The alternate screen buffer (`\033[?1049h` / `\033[?1049l`) is entered on start and restored in a `finally` block, so Ctrl+C cleanly returns to the prior terminal state. `--watch` requires a FILE argument; stdin cannot be watched (polled by path, not fd).

## `TERMRENDER_COLOR=1` forces color when stdout is not a tty

`use_color` (lines 361–363 and 388–390) is `True` when stdout is a tty OR `TERMRENDER_COLOR == "1"`. The tmux pane command is prefixed with `TERMRENDER_COLOR=1` (lines 334, 337) so color survives the `| less -R` pipe. Setting this env var in scripts achieves the same effect — it overrides the tty check entirely.

## `_EMOJI_WIDE_RANGES` must stay sorted by codepoint

`_char_width()` (style.py:144) exits the range scan early on `cp < lo`, assuming all ranges are in ascending codepoint order. Adding a new range out of order causes the early exit to skip ranges with higher `lo` values, silently misclassifying those codepoints as 1-wide.
