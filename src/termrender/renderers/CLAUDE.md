# Renderers

## Renderer signature convention
Two signatures exist — not enforced by typing, but the dispatcher expects them:
- **Leaf renderers** (`divider.py`, `tree.py`): `render(block, color) -> list[str]`
- **Container renderers** (`panel.py`, `quote.py`, `code.py`, `columns.py`): `render(block, color, render_child) -> list[str]`

`render_child` is the engine's dispatch function; call it to recurse into child blocks rather than calling sibling renderers directly.

## `render_box` — width is total, not content
`borders.py:render_box(content_lines, width, ...)` — `width` is the **full** box width including the two `│` border columns. Content width is `width - 2*border_v - 2` (border + 1-space padding each side). Passing inner/content width here produces double-shrinkage.

Used by `panel.py` and `code.py` (with `dim=True`).

## EAW-dynamic guide characters in `tree.py`
`_guide_chars()` is called at render time (not module init) because `visual_len("├── ")` differs under East Asian Width ambiguous=2 mode. Under that setting `"│"` is width 2 while `"─"` is width 1, so the four guide prefixes have inconsistent visual widths. `_guide_chars()` normalizes all four to the visual width of `"├── "` at runtime, picking up whatever EAW setting is active. The same EAW issue drives the dynamic `border_v`/`dash_v` math in `render_box`.

## `tree.py` — source goes in `attrs["source"]`, indent is auto-detected
Tree content comes from `block.attrs["source"]` (a raw multi-line string), not `block.text` or `block.children`. `_detect_indent` sniffs indent size from the source and clamps to 2 or 4 — 3-space or 6-space indentation silently misparses. `[x]` and `[!]` status markers in labels are replaced with styled Unicode symbols; `**bold**` and `*italic*` inline markdown is also parsed.

## `quote.py` — dual attribution keys
Attribution line is rendered for `block.attrs["author"]` **or** `block.attrs["by"]`; `"author"` takes precedence. Missing both suppresses the attribution line entirely.

## `panel.py` — callouts delegate through a proxy Block
`render_callout` patches `title`, `color`, and `type=BlockType.PANEL` into a new `Block` instance and calls `render()` on it. The original block is not mutated. The callout type string (`"info"`, `"warning"`, `"error"`, `"success"`) is only used to look up `_CALLOUT_MAP`; an unknown type falls back to blue `ℹ`.
