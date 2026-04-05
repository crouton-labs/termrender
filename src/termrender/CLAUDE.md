# termrender/src/termrender

## Layout: two-pass order is mandatory

`layout.py` runs `resolve_width()` then `resolve_height()` — this order is load-bearing. Height resolution calls `wrap_text(text, width)`, so every block must have `.width` set first. Reversing the order causes `block.width = None`, which silently falls back to `width = 1` (layout.py:76), drastically underestimating all heights.

## Mermaid: subprocess runs in layout, not in the renderer

`layout.py:118–134` runs `mermaid-ascii` and caches the result in `block.attrs["_rendered"]`. The `mermaid` renderer (renderers/mermaid.py) reads this cache key; if it's absent, it runs the subprocess again. A failed layout subprocess (tool missing, timeout) silently stores the raw source diagram in `_rendered`, so the renderer falls back to printing source — no error is raised. Both sites have a 30s timeout.

## Directive nesting: depth counter, not stack entries

The parser tracks nested directives of the same type with a `depth` integer inside the top stack entry, not separate stack entries (parser.py:241–306). A closer `:::` only pops the stack when `depth == 1`; otherwise it decrements depth and treats the closer as body content. Consequence: innermost closers appear verbatim in the body of the parent and are re-parsed on the recursive `parse()` call at line 351.

Max recursion depth is 50; exceeding it raises `ValueError`, not `DirectiveError`. The CLI (\_\_main\_\_.py:106) only catches `DirectiveError`, so deeply nested documents crash with an unhandled exception.

## `_ambiguous_width` is global mutable state

`style.set_ambiguous_width(n)` (style.py:21–23) changes how East Asian ambiguous-width characters are measured for the entire process. There is no reset function. Calling it in one render context affects all subsequent renders. Affects `visual_len()` and therefore all wrapping and column math.

## Column width: explicit widths exceeding available space truncate auto-columns to 1

`layout.py:30–63`: explicit column widths (percent or absolute) are allocated first; remaining space is split among auto-width columns with `max(remaining, 0)`. Two columns each claiming 80% of a 100px terminal leaves auto-width columns with width 1 — no error, no proportional scaling.

## Character offset tracking across wrapped lines

`text.py:32–33`: after rendering each wrapped line, the offset advances by the line's length and then skips one character if the next character in the original plain text is a space (the space `wrap_text` consumed). If wrapping preserves trailing spaces, this skip is wrong and subsequent span styling shifts by one character.

## `"•"` bullet visual width vs `len()`

`text.py:115–143`: list indentation uses `len(prefix)` (byte length) not `visual_len()`. The bullet "•" is 1 byte but 1 column wide — currently safe. If the bullet is ever changed to a 2-column-wide character, continuation lines misalign by 1 column.

## `wrap_text` measures in characters, not visual columns

`style.py:195–241`: all line-length comparisons inside `wrap_text` use `len()` (character count), not `visual_len()`. A 2-column-wide CJK character is counted as 1 column-unit, so wrapped lines silently overflow their allocated width by one cell per wide character. This affects every block type that calls `wrap_text`.

## Unknown directive names silently become PANEL

`parser.py:339`: `_DIRECTIVE_TO_BLOCK.get(name, BlockType.PANEL)` — any unrecognized `:::name` becomes a bordered PANEL block with no error or warning. Typos in directive names (e.g. `:::callOut`) produce visible output that looks correct but lacks the expected behavior (callout type, icon, color).

## `TERMRENDER_CJK` env var is the only public trigger for ambiguous-width

`__init__.py:30–31` calls `set_ambiguous_width(2)` on every `render()` call when `TERMRENDER_CJK` is set. The CLI `--cjk` flag sets `os.environ["TERMRENDER_CJK"]` (not the function directly), so it persists for the entire process. In multi-render programmatic usage, setting this env var before the first `render()` permanently widens ambiguous-width for all subsequent renders in the same process (no reset path — see `_ambiguous_width` note above).
