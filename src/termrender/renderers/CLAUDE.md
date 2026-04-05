# Renderers

## Renderer signature convention
Two signatures exist — not enforced by typing, but the dispatcher expects them:
- **Leaf renderers** (`divider.py`, `tree.py`): `render(block, color) -> list[str]`
- **Container renderers** (`panel.py`, `quote.py`, `code.py`, `columns.py`): `render(block, color, render_child) -> list[str]`

`render_child` is the engine's dispatch function; call it to recurse into child blocks rather than calling sibling renderers directly.

## `render_box` — width is total, not content
`borders.py:render_box(content_lines, width, ...)` — `width` is the **full** box width including the two `│` border columns. Content width is `width - 2*border_v - 2` (border + 1-space padding each side). Passing inner/content width here produces double-shrinkage.

Used by `panel.py` and `code.py` (with `dim=True`).

If `content_lines` is empty, `render_box` inserts one blank interior line — output is always ≥ 3 lines (top border + 1 blank + bottom border). Callers computing expected height from content line count must add 3, not 2.

When `title` is provided, it is **left-anchored**, not centered: `┌─ TITLE ───┐`. The format is `"─ " + title + " "` flush-left, then fill dashes to `┐`. There is no API for a right-anchored or centered title.

## EAW-dynamic guide characters in `tree.py`
`_guide_chars()` is called at render time (not module init) because `visual_len("├── ")` differs under East Asian Width ambiguous=2 mode. Under that setting `"│"` is width 2 while `"─"` is width 1, so the four guide prefixes have inconsistent visual widths. `_guide_chars()` normalizes all four to the visual width of `"├── "` at runtime, picking up whatever EAW setting is active. The same EAW issue drives the dynamic `border_v`/`dash_v` math in `render_box`.

## `tree.py` — source goes in `attrs["source"]`, indent is auto-detected
Tree content comes from `block.attrs["source"]` (a raw multi-line string), not `block.text` or `block.children`. `_detect_indent` sniffs the first indented line: returns 2 for ≤2 spaces, the raw value for 3–4 spaces, and clamps to 4 for anything larger. A tree where the first sniffed indent is 5 or 6 spaces gets clamped to 4 — subsequent lines compute `depth = spaces // 4`, skipping depth levels silently (e.g. 6-space children land at depth 1, but 12-space grandchildren land at depth 3, not 2). `[x]` and `[!]` status markers in labels are replaced with styled Unicode symbols; `**bold**` and `*italic*` inline markdown is also parsed.

Depth-0 items (no leading spaces) render with no guide prefix at all — a flat source is a plain list, no tree lines.

`block.attrs["color"]` sets the guide-line color (the `├──` connectors); it is distinct from the `color: bool` render parameter and only styles guides, not labels.

## `divider.py` — always dim, no color path
`render()` hardcodes `dim=True`; there is no way to pass a custom color through the leaf signature. A colored divider requires a different renderer or direct `render_box` usage.

Optional centered label comes from `block.attrs["label"]` (not `block.text`). `visual_center(inner, w, "─")` handles the fill — the label is padded as `" {label} "` before centering, so the label always has at least one space of breathing room from the surrounding dashes.

## `quote.py` — dual attribution keys; EAW-sensitive bar width
Attribution line is rendered for `block.attrs["author"]` **or** `block.attrs["by"]`; `"author"` takes precedence. Missing both suppresses the attribution line entirely.

`bar_width = visual_len("│") + 1` — under EAW ambiguous=2, `"│"` is width 2 so `bar_width` becomes 3, shrinking `inner_w` by one extra column relative to default EAW. The bar itself is correct visually, but layout that pre-computes quote inner width assuming `bar_width == 2` will be off by 1 under EAW=2.

## `panel.py` — callouts delegate through a proxy Block
`render_callout` patches `title`, `color`, and `type=BlockType.PANEL` into a new `Block` instance and calls `render()` on it. The original block is not mutated. The callout type string (`"info"`, `"warning"`, `"error"`, `"success"`) is only used to look up `_CALLOUT_MAP`; an unknown type falls back to blue `ℹ`.

## `mermaid.py` — leaf signature (not container), encoding fix, no returncode check, no truncation

**Leaf signature, not container**: `render(block, color)` — no `render_child`. The parent `CLAUDE.md` incorrectly lists mermaid as a Container renderer.

**`fix_mermaid_encoding`**: `mermaid-ascii` misreads UTF-8 input as Latin-1 and re-encodes, corrupting multi-byte characters (e.g. `→` becomes `â\x86\x92`). The fix is `text.encode("latin-1").decode("utf-8")`; on failure it silently returns the corrupted string — callers cannot distinguish fixed vs. corrupt output.

**`except Exception` swallows everything**: timeout, missing tool, `MemoryError` — all fall back to `rendered = source` (the raw mermaid source text) silently. Returncode is also never checked; a non-zero exit still reads `result.stdout`, producing a blank-line block if stdout was empty. If both `_rendered` and `source` are absent, empty string is sent to `mermaid-ascii`.

**`visual_ljust` pads but never truncates**: every output line is padded to `block.width`. Lines wider than `block.width` overflow without clipping. If `mermaid-ascii` emits a diagram wider than the allocated block, it silently exceeds the layout boundary.

**Trailing blank line**: `rendered.split("\n")` on output ending with `\n` (typical subprocess output) produces a trailing empty string, which becomes a `block.width`-wide blank line appended to every mermaid block.

Layout pre-renders into `block.attrs["_rendered"]` (see `src/termrender/CLAUDE.md`); this renderer re-runs the subprocess only when that key is absent.
