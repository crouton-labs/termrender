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

## `mermaid.py` — first-line type dispatcher, not a single renderer

`mermaid.py`'s `render(block, color)` (leaf signature, no `render_child` — the parent `CLAUDE.md` incorrectly lists mermaid as a Container renderer) is a thin wrapper: it reads `block.attrs["_rendered"]` if layout already precomputed it, else calls `render_mermaid_lines(source, width)`, then pads every line to `block.width` with `visual_ljust`. All the type-routing logic lives in `render_mermaid_lines`, shared with `layout.py`'s height pass (see below) so there is exactly one dispatch path, not two.

**Dispatch is by first real line, case-insensitive** (`_first_line_type`), after skipping any prelude via `mermaid_prelude.strip_prelude_lines` (see below): `pie`, `gantt`, `sequenceDiagram`, `mindmap`, `journey`, and `timeline` route to native Python renderers (`mermaid_pie.py`, `mermaid_gantt.py`, `mermaid_sequence.py`, `mermaid_mindmap.py`, `mermaid_journey.py`, `mermaid_timeline.py`). Every other type — `graph`/`flowchart`, `classDiagram`, `stateDiagram`, `erDiagram`, … — routes to `_render_via_binary`, the pre-existing single path through the vendored Go `mermaid-ascii` binary. **Only the six listed types have native renderers; every other type's degradation is byte-for-byte what it was before this dispatcher existed** — do not add a bordered fallback panel for them, since crouter's attach viewer detects render failure by the *absence* of box-drawing glyphs in the output, and a decorative border would defeat that.

**`mermaid_prelude.py`** — a tiny shared module (no dependency on `Block` or the rest of the pipeline) implementing `strip_prelude_lines(lines)`, used by both `mermaid.py`'s dispatch sniff and `mermaid_sequence.py`'s own header check. It skips leading blank lines, `%%` line comments, `%%{init: ...}%%` directives, and `---`-delimited YAML frontmatter, permissively: an unterminated frontmatter block or directive is left alone rather than eating real content. Prelude stripping is for *sniffing/validating the type line only* — the per-type body parsers still receive the full untouched source; `mermaid_sequence.py`'s `_parse` already tolerates arbitrary prelude lines before its header (they fail every line pattern and are skipped via its `seen_header` gate), and `mermaid_pie.py`/`mermaid_gantt.py`/the mindmap/journey/timeline parsers likewise just skip lines that don't match their grammar — a frontmatter `title: X` line could in principle collide with a `title` grammar rule, but this is accepted as the same class of pragmatic-parsing tradeoff as any other unrecognized line, not something the prelude skip needs to prevent.

**`_render_via_binary`** (used for flowchart/graph/class/state/ER/everything-without-a-native-renderer): normalizes via `preprocess_mermaid_for_ascii`, shells out with `check=True`, and undoes the Latin-1 double-encoding via `fix_mermaid_encoding` (`mermaid-ascii` misreads UTF-8 input as Latin-1 and re-encodes, corrupting multi-byte characters — e.g. `→` becomes `â\x86\x92`; `text.encode("latin-1").decode("utf-8")` reverses it, and on failure silently returns the corrupted string). Any failure — `CalledProcessError` (including a non-zero exit, now actually checked via `check=True`), missing binary, or timeout — degrades to the raw source text. A labeled back-edge (`X -->|lbl| Y` in `graph LR`) panics the binary on both the PyPI 1.2.0 wheel and vendored master; the resulting non-zero exit degrades the same way. Note `preprocess_mermaid_for_ascii` has its own independent first-line sniff (not `mermaid_prelude`-aware) to decide sequence-vs-flowchart-vs-other normalization — a prelude ahead of `graph`/`flowchart`/`sequenceDiagram` here means no shape/arrow normalization runs, an existing (unfixed) limitation of the binary path, orthogonal to dispatch routing.

**`visual_ljust` pads but never truncates**: every output line (from any type — binary or native) is padded to `block.width` in the outer `render()`. Lines wider than `block.width` overflow without clipping. `mermaid-ascii` has no width-control flag (`--maxWidth`/`-w` do not exist — the call passes only `-f - -y 1`), so wide flowchart output silently exceeds the layout boundary; the native renderers respect `width` by construction (pie/gantt/timeline size their own bars to it; sequence/mindmap/journey have intrinsic width and may overflow, matching the binary path's contract) — see each renderer's own note below.

Layout (`layout.py::resolve_height`, `BlockType.MERMAID` branch) precomputes `block.attrs["_rendered"]` by calling the same `render_mermaid_lines`, so `mermaid.py`'s `render()` only recomputes when that key is absent (e.g. calling `render()` on a block that skipped the layout pass).

**Flowchart node shapes are normalized to rectangles**: `preprocess_mermaid_for_ascii` rewrites every non-rectangle flowchart node shape (`{rhombus}`, `[(cylinder)]`, `((circle))`, `([stadium])`, `{{hexagon}}`, `[[subroutine]]`, `[/parallelogram/]`) to the `id[label]` form via `_FLOWCHART_SHAPE_SUBS`, because mermaid-ascii's `parseNode` only recognizes `[text]` rectangles — other shapes otherwise leak raw delimiters or the bare node id into the box. This is a permanent workaround: node shapes are unsupported on current upstream master (pin `6fffb8e`) and the 6 newer master commits are arrow-parsing only, so don't expect a pin bump to remove the need. The backend draws a rectangle regardless, so only the label text matters.

**Binary resolution**: the executable comes from `_mermaid_bin.mermaid_ascii_bin()` — the vendored `_bin/mermaid-ascii-<os>-<arch>` (pinned upstream master `6fffb8e`, built via `scripts/build-mermaid-ascii.sh`) if present for the platform, else `mermaid-ascii` on PATH (the PyPI wheel, capped at 1.2.0).

## `mermaid_pie.py` — re-expressed as a bar chart, not a text circle

A text pie chart is worse than a labeled bar chart at the same information density (per the ratified plan), so `parse_pie` extracts `(title, items)` from the `pie [showData]` / `title …` / `"label" : value` grammar and `render` hands the items to `charts.py::render_bar` via a synthetic `Block(type=BlockType.BAR, ...)` — no duplicated bar-drawing logic. Each item's `unit` attr is set to the pre-formatted percentage string (e.g. `" (40.0%)"`) so `render_bar`'s existing value-formatting appends it for free. Called with `color=False` always — mermaid output is monochrome by design (the attach viewer relies on `--color on == --color off`). Unparseable/empty input degrades to the raw source lines, same contract as the binary path.

## `mermaid_gantt.py` — dates resolved via a running `last_end` cursor, not a strict grammar

`parse_gantt` handles `dateFormat` (translated to a `strptime` pattern via a token map: `YYYY`→`%Y`, `MM`→`%m`, etc.), `title`, `section`, and task lines split on the first `:` into a comma-separated token list. Each token is classified in order — status keyword (`done`/`active`/`crit`/`milestone`, ignored) → `after <id...>` dependency → duration (`\d+[dwhms]`) → date (via the resolved `strptime` format) → bare identifier — so token order in the source doesn't matter, only which shape each token matches.

**Missing start dates fall back to `last_end`**, a running cursor updated after every successfully-placed task (mirroring mermaid's own default-start-follows-previous-task semantics): a bare `Task2 :5d` with no date and no `after` picks up where the previous task left off; an `after <id>` referencing an id that was never seen falls back the same way rather than dropping the task. A task with no start anchor at all (first task in the diagram, no date, no `after`) is skipped — degrade, don't crash.

`render` scales every task's `(start, end)` into a ratio over the full `[min_start, max_end]` span and draws a `░`/`█` track via `_draw_span`; section names are their own row, un-indented, with all task rows below sharing one global label-column width for alignment across sections. Diagrams with zero resolved tasks (parse produced no sections) degrade to the raw source lines.

## `mermaid_sequence.py` — deterministic column layout, no graph-layout search

The one native renderer not built by reusing another primitive (there's no existing "sequence diagram" shape in termrender to reuse) — `render_sequence(source, width)` is a standalone module with its own parser (`_parse`, producing `Arrow`/`NoteEvent`/`BlockBoundary`/`PlainLabel` events) and its own column-layout pass (`_layout_columns`, a 1D constraint solve: message order already fixes the vertical axis, declaration order fixes the column axis, so gaps between adjacent columns are widened only enough for whatever message text crosses them). `width` is advisory-only and never wraps/truncates — sequence diagrams have intrinsic width and may overflow, same contract as the flowchart binary path. Parsing never raises except when the source isn't a sequence diagram at all (checked via `mermaid_prelude.strip_prelude_lines` against the first real line); every malformed/unrecognized construct within a real sequence diagram (a stray `else`/`end`, an unsupported arrow punctuation, a flowchart-only `-.->`) degrades to a plain text line instead. See the module's own docstring for the full grammar supported and known degradations (CJK column misalignment, `Note` multi-participant simplification, etc.).

## `mermaid_mindmap.py` — mindmap source is already `tree.py`'s shape

Mindmap is indentation-based exactly like `tree.py`'s input format, so `parse_mindmap` does no layout of its own: it drops the `mindmap` header line and `::icon(...)`/`:::className` decoration lines, strips each node's shape delimiters (`(())`, `{{}}`, `))((`, `)(`, `[]`, `()`, checked most-specific-first the same way `mermaid.py`'s `_FLOWCHART_SHAPE_SUBS` is ordered) down to label text, and preserves each surviving line's original leading whitespace verbatim — depth then falls out of `tree.py`'s own indentation auto-detection for free. `render` hands the transformed text to `tree.py::render` via a synthetic `Block(type=BlockType.TREE, ...)`, always `color=False`. A diagram with nothing left after stripping (blank, or header-only) degrades to the raw source lines.

## `mermaid_journey.py` — section/task outline mapped onto `tree.py`

A journey is a two-level outline (`section` → tasks), so `parse_journey` splits `name: score: actors` task lines (tolerating a missing/non-numeric score as `None` and missing actors as `[]`, never raising) into section buckets — a task before any `section` line lands in a leading unnamed bucket, matching `mermaid_gantt.py`'s same convention. `render` builds one synthetic indented-tree source string (section names at depth 0, `_format_task` output — `name  ★★★☆☆  (actors)`, stars clamped to the 0–5 range — as depth-1 children under a two-space indent) and renders it through `tree.py::render` via a synthetic `Block`, same pattern as mindmap. The diagram title (if any) is a plain line prepended above the tree, not part of it. Sections with no tasks are dropped; zero surviving sections degrades to the raw source lines.

## `mermaid_timeline.py` — sections rendered as separate `timeline.py` sub-timelines

`parse_timeline` handles `title`, `section`, and `period : event[ : event ...]` lines; a period-less line (blank before the first `:`) continues the *previous* row's period rather than introducing a new one — tracked via a `shows_date` flag so only the row that actually introduces a period (same-line or most recent prior line) prints it, everything else in that group prints a blank date column for alignment. `render` calls `timeline.py::render` once per section (each section's `entries` in a synthetic `Block(type=BlockType.TIMELINE, ...)`), inserting the section name as its own plain row above each sub-timeline and a blank separator row between sections — reuses the existing bullet/connector rendering rather than a bespoke one. A diagram with zero resolved entries degrades to the raw source lines.
