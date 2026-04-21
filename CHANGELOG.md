# CHANGELOG


## v0.9.0 (2026-04-21)

### Bug Fixes

- **wrap**: Honor hard line breaks in wrap_text
  ([`a383f4d`](https://github.com/crouton-labs/termrender/commit/a383f4de66b3d8370bda500dd4c3771a591563aa))

Markdown hard breaks were parsed as \n spans but wrap_text only split on spaces, leaking raw \n into
  wrapped output. Inside panels and columns this broke border alignment because visual_ljust padded
  the string once, not per visual line.

wrap_text now recursively wraps each \n-separated segment; the text-renderer offset heuristic skips
  \n as well as space between lines. Layout height calcs pick up the extra lines automatically.

### Features

- **spacing**: Add blank lines between hard breaks and top-level blocks
  ([`7610189`](https://github.com/crouton-labs/termrender/commit/761018928504cf9626678fe46b5ee66d5e899d5d))

Hard line breaks now render a blank line between the two sides (parser emits \n\n so wrap_text
  naturally produces the gap), and DOCUMENT-level siblings are separated by a blank padded line so
  paragraphs, headings, and blocks no longer visually run together.


## v0.8.0 (2026-04-18)

### Features

- **mermaid**: Preprocess sequence diagrams for mermaid-ascii compatibility
  ([`a642576`](https://github.com/crouton-labs/termrender/commit/a642576d41d5dbde372d7de2ab47745296a78e32))

mermaid-ascii only parses ->> / -->> arrows, participants, and self-loops; every other common
  sequence-diagram construct made it fail and fall back to raw source. Rewrite Note lines into
  self-loops, map -> / -x / --x / -) / --) / -- > onto the supported arrow pair, drop block keywords
  (loop/alt/activate/ autonumber/end/…), and flatten <br/> to ' / '. Non-sequence diagrams pass
  through unchanged.


## v0.7.3 (2026-04-15)

### Bug Fixes

- **code**: Wrap long code lines to fit layout width
  ([`31c6e59`](https://github.com/crouton-labs/termrender/commit/31c6e595a438c4ced8c61fff679b59d4ae55f938))

Code blocks previously used raw line count for height and let render_box grow beyond the layout
  allocation. Now wraps source lines to the available content width in both layout and renderer.

- **parser**: Add directive trace and file-absolute line numbers to error messages
  ([`0f99ea0`](https://github.com/crouton-labs/termrender/commit/0f99ea0310116f8fa06e933cd26126246d7a3b43))

Stray-closer and unclosed-directive errors now print the full open/close trace and, when nested
  directives share a colon count, name the specific cause and suggest the fix. Recursive body
  parsing reports file-absolute line numbers via _line_offset threading through parse →
  _split_directives → _directive_to_block.


## v0.7.2 (2026-04-09)

### Bug Fixes

- **cli**: Default --tmux pane to 1/3 window width
  ([`d9c1bcc`](https://github.com/crouton-labs/termrender/commit/d9c1bccbe95a4e5cf1f975b82cbafde6d9d3807a))

Instead of preview-rendering at 80 cols to measure content width, default to (window_width - 2) // 3
  for a consistent 1/3 split.


## v0.7.1 (2026-04-08)

### Bug Fixes

- **cli**: Give --pane error paths actionable recovery guidance
  ([`f857c32`](https://github.com/crouton-labs/termrender/commit/f857c32c89afe32a3a668f03a3d570b0f14dae97))

The two --pane error paths now tell the agent how to recover instead of restating the problem.
  "Check that the pane id is valid" is a dead end for an agent — it needs either a command to list
  valid pane ids (tmux list-panes) or a fallback (spawn a fresh pane via --tmux).


## v0.7.0 (2026-04-08)

### Features

- **cli**: Add --pane for in-place tmux pane updates
  ([`4ab1d77`](https://github.com/crouton-labs/termrender/commit/4ab1d77b996aa356926407dcc11c1b408e68e0ee))

--tmux now prints the newly-created pane id to stdout (via split-window -P -F) so callers can
  capture it for subsequent updates. --pane <ID> targets an existing pane via tmux respawn-pane -k
  instead of spawning a new one — the existing process is killed and replaced with the new render.
  This lets agents synchronously re-render a doc on every edit without spawning fresh panes or
  relying on --watch polling.

Also in this commit: - Expand -h epilog to cover the 8 visualization directives (stat, bar,
  progress, gauge, diff, timeline, tasklist, inline badge) and rewrite the nesting note to describe
  the strict colon-count rule. The previous epilog only documented the base directives and said
  "every opener needs a matching :::", which contradicts the actual parser behavior. - Render
  tasklist checkboxes as filled/empty dots (● / ○ / ◐) instead of boxed glyphs (☑ / ☐ / ◐).


## v0.6.1 (2026-04-08)

### Bug Fixes

- **borders**: Grow render_box to fit overflowing content and titles
  ([`dc108c8`](https://github.com/crouton-labs/termrender/commit/dc108c8242763828245569f719abce64b26ddf5b))

mermaid-ascii's --maxWidth is non-strict, so a child mermaid block can return lines wider than the
  panel's allocated content area. Previously the side walls floated outward to accommodate the
  content while the top/bottom borders stayed at the requested width, leaving corner glyphs one
  column inside the side walls and producing a visibly jagged box.

render_box now measures the widest content line (and the title) and grows its effective width up
  front so all four borders land at the same column. Trade-off: the box may overflow its parent
  allocation, but the box itself is internally consistent.


## v0.6.0 (2026-04-07)

### Features

- Add diff, charts, stat, timeline, tasklist, and inline badges
  ([`e14f615`](https://github.com/crouton-labs/termrender/commit/e14f615ae8d0723405db61c79b0f858d7bf0f863))

New block-level directives: - :::diff — colored unified diff with +/- gutters - :::bar — multi-bar
  chart with sub-cell precision via eighth blocks - :::progress — single-line progress bar (auto
  color by ratio) - :::gauge — three-line meter (auto color by load threshold) - :::stat — KPI tile
  with label, value, trend arrow + delta, caption - :::timeline — vertical event list with bullet
  markers and connectors - :::tasklist — checkbox list (also auto-detected from any markdown list
  with [x]/[ ]/[!] markers)

New inline role: - :badge[text]{color=green} — colored pill, reuses new InlineSpan fg/bg fields so
  future inline roles drop in trivially.

Cross-cutting changes: - InlineSpan gained fg/bg fields; render_spans and span-slicers in text.py
  and table.py honor them. - _merge_plain_spans coalesces mistune's text fragments before role
  expansion (mistune splits on `[`, which would otherwise break :badge[...]). - _render_list_item
  now uses visual_len(prefix) so styled checkbox prefixes don't break indent math. - STAT joins
  PANEL/CALLOUT/CODE in the border-aware width path. - progress and gauge added to
  _SELF_CLOSING_DIRECTIVES (atomic, no body); stat requires an explicit closer so it can hold a
  caption.

63 new tests across six test files. All 94 tests pass.

- **cli**: Add --watch mode for live re-rendering
  ([`4223ad8`](https://github.com/crouton-labs/termrender/commit/4223ad86805b0b3ad45450bd7ca4441a668f0e23))

Re-renders the file whenever its mtime changes, with terminal-resize detection and inline error
  display so the watcher survives malformed input. Uses the alternate screen buffer so Ctrl+C
  cleanly restores the prior terminal state.

Composes with --tmux: --tmux --watch points the spawned pane at the real file path (skipping the
  tempfile path) so the live loop runs inside the side pane.

### Refactoring

- **parser**: Require strictly more colons on outer fences
  ([`4a501d9`](https://github.com/crouton-labs/termrender/commit/4a501d917db191f758874bb6c3d922c879a763be))

Drops the depth-counter that allowed `:::outer ... :::inner ... ::: ... :::` nesting with same colon
  counts. Termrender now matches the standard followed by MyST, Pandoc fenced divs,
  markdown-it-container, and CommonMark fenced code blocks: an opener can only nest inside another
  directive if its colon count is strictly less than the outer's.

A closer with a non-matching colon count is treated as body content and falls through to the
  recursive parse(), which is what makes nested directives work in the first place.

Fixtures in test_column_alignment.py rewritten to ascending colon counts (7/6/5/4/3 for the
  showpiece, 5/4/3 for columns_tree, 4/3 for panel_tree). test_same_colon_nesting_backward_compat
  deleted — its behavior is no longer supported.


## v0.5.0 (2026-04-06)

### Features

- **table**: Render horizontal separator lines between data rows
  ([`3e4c74a`](https://github.com/crouton-labs/termrender/commit/3e4c74a10d63470f2eb2ec096bb47cf41f0b7f70))


## v0.4.0 (2026-04-05)

### Features

- **parser**: Variable colon counts, backtick fence directives, and gloam-inspired theming
  ([`47fac7f`](https://github.com/crouton-labs/termrender/commit/47fac7fcf13d33e5d9986d3f9ca42ddaf5e7207d))

Parser changes: - Support 3+ colon openers/closers with stack-based matching - Backtick fence
  directive syntax (```{name}) via mistune AST interception - Option line stripping (:key: value)
  into directive attrs

CLI changes: - Syntax validation before tmux pane creation (no orphan panes on bad input) - TTY
  auto-detect for color (disabled when piping, forced in tmux subprocess)

Theming (gloam-inspired defaults): - Headings: depth-based colored fg + dim tinted bg
  (yellow→green→cyan→blue→magenta) - Inline code: cyan (aqua) - Panel borders: dim gray with yellow
  bold titles - Table borders: blue dim, headers: yellow bold on dim-blue bg - Background color
  support added to style()

24 new tests across two test files.


## v0.3.0 (2026-04-05)

### Documentation

- Update CLAUDE.md notes for mermaid, tmux, and layout
  ([`9e104d5`](https://github.com/crouton-labs/termrender/commit/9e104d5ee7bad9a57902e79586c02b0e8d80c589))

### Features

- **cli**: Auto-size tmux pane to fit rendered content
  ([`91f0414`](https://github.com/crouton-labs/termrender/commit/91f0414d0bf8bfbe4d7167159b928ed9c736db74))

- **mermaid**: Pass width and vertical padding to mermaid-ascii
  ([`96145c2`](https://github.com/crouton-labs/termrender/commit/96145c2789a52a4d94e9bc5f4adf7f3a88d8501f))

- **table**: Auto-wrap cell content when columns overflow
  ([`0fae56f`](https://github.com/crouton-labs/termrender/commit/0fae56f8f00260c3263671df9a63a5bea17820bb))

When a table exceeds available width, cells now wrap text within their proportionally-shrunk column
  widths instead of overflowing. Layout height calculation updated to account for multi-line cells.


## v0.2.1 (2026-04-05)

### Bug Fixes

- **mermaid**: Undo double-encoded UTF-8 from mermaid-ascii output
  ([`9e0560c`](https://github.com/crouton-labs/termrender/commit/9e0560ce46b6dc3f90d2d716a97780713e5e5e53))

mermaid-ascii misinterprets UTF-8 bytes as Latin-1 and re-encodes, corrupting multi-byte characters
  (e.g. → renders as â<U+0086><U+0092>). Apply latin-1 round-trip to recover original UTF-8 in both
  layout and renderer subprocess call sites.

### Documentation

- Add tmux pane lifecycle and --check interaction notes to CLAUDE.md
  ([`9400092`](https://github.com/crouton-labs/termrender/commit/9400092e507d470acb97ac5a17b66fcf0e9aa2f6))


## v0.2.0 (2026-04-05)

### Bug Fixes

- Handle zero-width and emoji presentation chars in visual width calculation
  ([`d0bb8dc`](https://github.com/crouton-labs/termrender/commit/d0bb8dcfa5ca0d2c16d78a1d7f81825231b9cb59))

_char_width now returns 0 for combining marks and format characters (ZWJ, variation selectors).
  visual_len handles VS16 emoji presentation sequences by promoting the preceding character to width
  2. Fixes panel border misalignment when content contains emoji or special Unicode.

- **docs**: Update README output examples to match actual rendered output
  ([`de6d0cc`](https://github.com/crouton-labs/termrender/commit/de6d0ccfd8a60aca20f2b2659a313f8d8c87d853))

### Chores

- Add README, design specs, and project CLAUDE.md files
  ([`93ac358`](https://github.com/crouton-labs/termrender/commit/93ac35857981c549797a9359573cacea1478b3ad))

- Derive version from git tags via hatch-vcs
  ([`33595a0`](https://github.com/crouton-labs/termrender/commit/33595a0b64363e445b90c9df135a50a4652e2bae))

### Continuous Integration

- Auto-release and publish via conventional commits
  ([`80a456b`](https://github.com/crouton-labs/termrender/commit/80a456b7301c57f2fd2b0cd30622b78f2d4b931e))

Replace manual GitHub release trigger with python-semantic-release. On push to main, conventional
  commits are analyzed to determine version bumps (feat→minor, fix→patch) and publish to PyPI
  automatically.

### Documentation

- Update README token count and expand CLAUDE.md implementation notes
  ([`1f70a53`](https://github.com/crouton-labs/termrender/commit/1f70a5352cbced30219012dbede7040c6ac97457))

### Features

- Add CJK ambiguous-width support, strict directive parsing, and rendering fixes
  ([`c000883`](https://github.com/crouton-labs/termrender/commit/c0008835d66b721b0a09c7a34dde11d08b3d3d94))

- Add emoji presentation and East Asian ambiguous-width character handling with --cjk flag and
  TERMRENDER_CJK env var - All renderers (borders, divider, quote, tree) now compute box-drawing
  character widths dynamically via visual_len - Parser raises DirectiveError on unclosed or stray
  ::: directives instead of silently degrading - Fix column width distribution to correctly account
  for inter-column gaps - Support 'author' as alias for 'by' attribute on quote blocks

- Add GFM table rendering with box-drawing borders
  ([`c3b61cd`](https://github.com/crouton-labs/termrender/commit/c3b61cdd659fdb782089cbca2fd3f74b18486605))

Enable mistune table plugin, parse table AST into TABLE blocks, and render with box-drawing
  characters. Supports left/center/right column alignment, bold headers, auto-sized columns, and
  proportional overflow distribution.

- **cli**: Add --tmux pane output, --check validation, and structured error handling
  ([`36b52ee`](https://github.com/crouton-labs/termrender/commit/36b52eed9701cd0acd363db2d0fa3d277244c8b0))

- --tmux renders in a new tmux side pane via split-window, piped through less -R - --check validates
  directive syntax without rendering (exit 0/2) - Structured _error() helper with fix/hint guidance
  on stderr - Named exit codes (EXIT_OK, EXIT_INPUT, EXIT_SYNTAX, EXIT_TERMINAL) - Expanded epilog
  with full directive reference, nesting examples, and env docs - Dynamic version from
  importlib.metadata (hatch-vcs) - Updated CLAUDE.md to document --check behavior and fix recursion
  depth note

- **cli**: Improve help output with examples, version flag, and tty detection
  ([`cb3e7e2`](https://github.com/crouton-labs/termrender/commit/cb3e7e2752ae860e5c3cbd4c4f1627e925a9c431))

### Testing

- Add column alignment and visual width tests
  ([`f8b6099`](https://github.com/crouton-labs/termrender/commit/f8b60998625977b10dd4697f8e772d80125cb9ce))

Covers showpiece rendering, column line width consistency, status marker visual widths (text vs
  emoji presentation), and panel border alignment.


## v0.1.0 (2026-04-04)
