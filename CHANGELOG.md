# CHANGELOG


## v4.3.0 (2026-07-06)

### Features

- Add flowchart renderer data model
  ([`cf3caef`](https://github.com/crouton-labs/termrender/commit/cf3caef28411d2ace3f71c63f218af52ba460da0))

- Wire sequence renderer and add native mindmap/journey/timeline renderers
  ([`120b51c`](https://github.com/crouton-labs/termrender/commit/120b51cddf58cd91ee948706c143c84ca42c7e9f))

- mermaid.py dispatch now routes sequenceDiagram to the finished mermaid_sequence.render_sequence,
  and mindmap/journey/timeline to new native renderers, leaving flowchart/graph/class/state/ER on
  the vendored Go binary path unchanged. - New shared mermaid_prelude.strip_prelude_lines skips
  leading %% comments, %%{init}%% directives, and --- YAML frontmatter before sniffing a diagram's
  type keyword, fixing valid diagrams with those preludes mis-routing to the binary fallback.
  mermaid_sequence.py's own header guard uses the same helper. - mermaid_mindmap.py:
  indentation-based mindmap source maps directly onto tree.py's shape; strips the mindmap header,
  ::icon()/:::class decoration, and node-shape delimiters down to label text. - mermaid_journey.py:
  section/task outline mapped onto tree.py, tasks rendered as depth-1 children with a star rating
  and actor list. - mermaid_timeline.py: sections rendered as separate timeline.py sub-timelines,
  with period-less continuation lines correctly attaching to the previous row instead of repeating
  the date. - Dispatch integration tests for every new route plus all three prelude forms; parse +
  golden-output render tests per new module. - CLAUDE.md updated to describe the current
  dispatch/prelude state.

Full suite: 230 -> 292 tests, all green.


## v4.2.0 (2026-07-06)

### Bug Fixes

- **mermaid-sequence**: Reject dash-adjacent punctuation as part of an id
  ([`612f36d`](https://github.com/crouton-labs/termrender/commit/612f36d14d68e6c51f4ac6d16f0ae837e44ddd01))

Reviewer found: near-miss arrow syntax with no sequence-diagram equivalent (e.g. flowchart-only
  `A-.->B`, or garbage like `A==>>B`) was silently absorbed into the source id ("A-.") instead of
  degrading to a plain line, because the arrow regex's identifier token was \S+/\S+? (anything
  non-space) and would backtrack through dash/dot punctuation until some later '>' happened to
  complete a valid-looking arrow.

Fix: identifiers now exclude '-' (plus ':', '+', whitespace) — dash is reserved for the arrow
  itself, so an id is the maximal run up to the first dash, eliminating the backtracking ambiguity
  entirely. Also documents the pre-existing (accepted, mirrors wrap_text()'s CJK bug elsewhere in
  termrender) character-index vs visual-width limitation in the module docstring, per independent
  review (non-blocking, not fixed here — same class of fix as the documented wrap_text() constraint,
  out of proportion for a renderer not yet wired into the dispatcher).

Adds 2 regression tests for the repro cases. 191 tests pass (full suite, up from 189).

### Features

- Add native ASCII sequence-diagram renderer for mermaid
  ([`ad63977`](https://github.com/crouton-labs/termrender/commit/ad639774edcbcd744ba7f2183c4f5d8c83630af0))

Standalone module (src/termrender/renderers/mermaid_sequence.py) exposing render_sequence(source,
  width) -> list[str]. Not wired into the mermaid.py dispatcher yet (a later integration phase owns
  that).

Layout: participant boxes across the top/bottom, vertical lifelines, messages as horizontal arrows
  in declaration order, self-messages as a loop-back. Column spacing is a 1D constraint pass driven
  by participant label widths and the messages crossing each gap (no 2D layout search needed since
  message order already fixes the vertical axis).

Grammar: participant/actor with 'as' aliases plus implicit participants from first use; all 8 arrow
  forms (->, -->, ->>, -->>, -x, --x, -), --)) with distinct line style (solid/dashed) and arrowhead
  glyph per marker; Note over/left of/right of; autonumber (start/step); loop/alt/opt/par/
  critical/break/rect/box render as labeled separator bands (else/and/ option as mid-band
  separators); activate/deactivate (including the +/- arrow shorthand) and <br/> are tolerated and
  flattened; any other unrecognized or malformed line (stray else/end, unknown directives) degrades
  to a plain text line rather than raising.

Tests: tests/test_mermaid_sequence.py, 40 cases covering golden output, all arrow variants, aliases,
  implicit participant ordering, notes, autonumber, block nesting, degradation paths, and the
  no-trailing-whitespace contract. Full suite (189 tests) still green.


## v4.1.1 (2026-07-06)

### Bug Fixes

- **mermaid**: Honor inline title on pie header line
  ([`37b4c37`](https://github.com/crouton-labs/termrender/commit/37b4c37581046d7a9b327f0e06f3ea5a5ca921d3))


## v4.1.0 (2026-07-06)

### Features

- **renderers**: Dispatch mermaid by type; native pie and gantt renderers
  ([`08decd1`](https://github.com/crouton-labs/termrender/commit/08decd191c7b17680a8785037b87807d18959de5))

mermaid.py becomes a first-line type dispatcher: pie and gantt now get dedicated native Python
  renderers instead of falling through to the vendored Go mermaid-ascii binary (which just echoed
  them as plaintext). Every other type's degradation is unchanged byte-for-byte, including
  flowchart/graph routing to the Go binary.

- mermaid_pie.py: parses the pie grammar and renders a labeled horizontal bar chart with
  percentages, reusing charts.py's render_bar. - mermaid_gantt.py: parses the core gantt grammar
  (dateFormat, sections, tasks with dates/durations/after-deps) and renders section-grouped rows
  with time-span bars scaled to the overall date range. Malformed lines and unresolvable tasks
  degrade gracefully instead of crashing. - layout.py's height pass now shares the same
  render_mermaid_lines dispatch mermaid.py uses, removing a duplicated subprocess call.

Tests: parser/layout coverage for both new renderers plus dispatcher routing tests
  (test_mermaid_pie.py, test_mermaid_gantt.py, test_mermaid_dispatch.py).


## v4.0.0 (2026-07-06)

### Features

- **mermaid**: Also route ```mermaid fences through the mermaid renderer
  ([`99a8017`](https://github.com/crouton-labs/termrender/commit/99a801783d719125505eef2dc1194e2e418ed025))

BREAKING CHANGE: partially reverses 083f590. A fenced code block whose info string is `mermaid`
  (e.g. GFM ````mermaid```` fences used by GitHub and most docs/agents unaware of the :::mermaid
  directive) now renders as an ASCII mermaid diagram, same as :::mermaid. Any other language tag
  still falls through to a plain CODE block; the :::mermaid directive is unchanged.

Root-caused: the reported bug (fences render as raw source, not a diagram) was not a regression or
  missing binary — the vendored mermaid-ascii binary and subprocess pipeline both work correctly. It
  was 083f590's deliberate, documented breaking change dropping fence support. Human chose to extend
  support back to fences rather than close as working-as-intended.

### Breaking Changes

- **mermaid**: Partially reverses 083f590. A fenced code block whose info string is `mermaid` (e.g.
  GFM ````mermaid```` fences used by GitHub and most docs/agents unaware of the :::mermaid
  directive) now renders as an ASCII mermaid diagram, same as :::mermaid. Any other language tag
  still falls through to a plain CODE block; the :::mermaid directive is unchanged.


## v3.0.2 (2026-06-17)

### Bug Fixes

- **docs**: Correct nested-directive examples to increasing-colon rule
  ([`4332854`](https://github.com/crouton-labs/termrender/commit/4332854cc1bdab8122f7e022c2d79a69e2d8a719))

Every nested example in the README and the doc -h 'Document format' help predated 4a501d9 (require
  strictly more colons on outer fences) and fails `termrender doc check`: the flagship deploy panel,
  the Columns example, and the Nesting section all used equal colons. Rewrote them so each outer
  directive uses strictly more colons than the one nested inside (MyST-style), documented the rule
  in the intro + Nesting prose + the agent-facing doc help, and added the gotcha to src CLAUDE.md.
  Rendered output is unchanged (colon count is pure syntax). All 11 README markdown blocks now pass
  doc check.

- **mermaid**: Normalize flowchart node shapes to rectangles
  ([`8c45f7c`](https://github.com/crouton-labs/termrender/commit/8c45f7c20810a3960cb037831a7c5f152406b3f6))

mermaid-ascii (vendored, pinned master 6fffb8e) only parses [text] rectangle nodes; every other
  mermaid node shape leaked raw delimiters or the bare node id into the rendered box — B{Auth?}
  rendered the literal 'B{Auth?}', E[(Database)] rendered '(Database)'. The preprocessor only
  handled sequence diagrams; flowcharts passed through untouched.

Add a flowchart shape normalizer that rewrites rhombus {}, cylinder [()], circle (()), stadium ([]),
  hexagon {{}}, subroutine [[]], and parallelogram/trapezoid [/ /] nodes to id[label], preserving
  the label text. The backend draws a rectangle regardless, so only the text matters.

Node shapes remain unsupported on current upstream master (parseNode handles only rectangles; the 6
  commits since our pin are arrow-parsing only), so this is a permanent workaround, not a stopgap
  for a pin bump. Regression test + CLAUDE.md note added.


## v3.0.1 (2026-06-10)

### Bug Fixes

- Spawn tmux render pane via absolute termrender path, not bare PATH name
  ([`993c646`](https://github.com/crouton-labs/termrender/commit/993c6463afc64b94b6dbbdbe6e69f7652feac500))

The tmux pane command baked a bare `termrender` token into split-window/ respawn-pane, so the
  spawned pane resolved it via $PATH. A venv-only install (invoked by absolute path, not on PATH)
  produced a pane that died instantly and silently. Build the pane command from termrender's own
  absolute invocation (argv[0] when executable, else `python -m termrender`).


## v3.0.0 (2026-05-18)

### Chores

- Re-trigger release publish for v3.0.0
  ([`467c583`](https://github.com/crouton-labs/termrender/commit/467c58338de217a417530e0bc32ad0a6973012eb))

### Documentation

- **claude-md**: Update CLI invocations to v3 flag form, prune stale notes
  ([`1276bf8`](https://github.com/crouton-labs/termrender/commit/1276bf86261528a725f8a012e2105b359f085eca))

### Features

- **cli**: Switch input contract to flags + positional + stdin
  ([`38df421`](https://github.com/crouton-labs/termrender/commit/38df4218af8c26d469a442b87090ad268ae47b0e))

Drops JSON-on-stdin in favor of long-form flags, at most one positional, stdin for the markdown
  content blob, per cli-design v2. Output (ANSI for render, JSON elsewhere), errors, and exit codes
  are unchanged.

- doc render / doc check now read source from stdin - doc watch / pane open / pane update take path
  as positional - pane update gains --pane-id flag - --color is an enum (auto|on|off) replacing the
  prior bool|null - --watch is presence-only and defaults to false on pane open/update - Internal
  pane self-pipe rebuilds the new flag-form invocations


## v2.1.0 (2026-05-16)

### Documentation

- **claude-md**: Document mermaid-ascii vendoring and correct stale --maxWidth
  ([`643e25a`](https://github.com/crouton-labs/termrender/commit/643e25a791de1f32591b245dee064f290221cfc2))

Note _mermaid_bin resolution, the pinned master binary, the no-width-flag reality, and the back-edge
  panic in renderers/CLAUDE.md.

- **claude-md**: Note QUOTE +1 height only applies to author/by attrs
  ([`3184d43`](https://github.com/crouton-labs/termrender/commit/3184d43e7293af735b82d559bc3253d7542cbf85))

### Features

- **mermaid**: Vendor engine from upstream master, fix broken -w invocation
  ([`d801de5`](https://github.com/crouton-labs/termrender/commit/d801de5bb22ba5205fe52ef65e80eda96590be93))

mermaid-ascii has no -w/width flag and never has; layout.py and mermaid.py passed `-w <width>`, so
  every diagram exited non-zero and degraded to raw source text on the 1.2.0 wheel. Drop -w (call is
  now `-f - -y 1`).

Resolve the binary via new _mermaid_bin.mermaid_ascii_bin(): prefer vendored
  _bin/mermaid-ascii-<os>-<arch> (built from pinned upstream master 6fffb8e via
  scripts/build-mermaid-ascii.sh), else fall back to `mermaid-ascii` on PATH (PyPI wheel, capped at
  1.2.0). pyproject ships the binary via hatch artifacts and bumps the fallback dep to >=1.2.

Caveats: only darwin-arm64 is vendored (other platforms fall back to the older PyPI engine); a
  labeled back-edge in graph LR panics the binary on both 1.2.0 and master and degrades to source.
  mermaid-ascii has no width control, so wide diagrams overflow (renderer pads, never truncates).


## v2.0.0 (2026-05-16)

### Continuous Integration

- **publish**: Authenticate PyPI upload with API token
  ([`09e21c8`](https://github.com/crouton-labs/termrender/commit/09e21c8f58529f8c9ba9a383c24563e6ebaba2f3))

Trusted publishing has failed on every release since v0.8.0 (invalid-publisher: OIDC claims for
  crouton-labs/termrender had no matching PyPI publisher), so 0.9.0-1.0.1 were tagged but never
  reached PyPI. Switch the publish job to token auth via the pypi-environment secret PYPI_API_TOKEN
  and drop the now-unused id-token permission.

### Features

- **cli**: Redesign CLI to agent-oriented JSON-stdin contract
  ([`ef70751`](https://github.com/crouton-labs/termrender/commit/ef7075103bc49d13cbd6bebdd01841454e5950ff))

Restructure the CLI as a noun-verb tree consumed by programs/agents: `termrender doc
  {render,check,watch}` and `termrender pane {open,update}`. All parameters arrive as a single JSON
  object on stdin; no flags except -h. Errors are structured JSON {error,message,next} on stdout
  with stable codes and non-zero exit. `doc check` emits {ok,errors[]} JSON on stdout (was "ok" on
  stderr). Per-node -h is a spec (input/output schema + Effects), not examples. The library render()
  API is unchanged; rendered ANSI output for doc render/doc watch is intentionally preserved as the
  product.

BREAKING CHANGE: the flag/positional CLI surface is removed. `termrender FILE`, -w/--width,
  --no-color, --check, --cjk, --tmux, --pane, --tmux-new-window, --watch, and -V/--version no longer
  exist. Callers must invoke a subcommand and pass parameters as a JSON object on stdin. Version is
  shown in root -h.

### Breaking Changes

- **cli**: The flag/positional CLI surface is removed. `termrender FILE`, -w/--width, --no-color,
  --check, --cjk, --tmux, --pane, --tmux-new-window, --watch, and -V/--version no longer exist.
  Callers must invoke a subcommand and pass parameters as a JSON object on stdin. Version is shown
  in root -h.


## v1.0.1 (2026-04-28)

### Bug Fixes

- **parser**: Extract bullet text from paragraph children in loose lists
  ([`95f389b`](https://github.com/crouton-labs/termrender/commit/95f389b808d89195a8b9dd957d7949328a8859e8))

Mistune wraps list_item content in block_text for tight lists and in paragraph for loose lists. Only
  block_text was being extracted into item spans, so loose-list bullets rendered with empty text —
  the renderer's `if not block.text` short-circuit dropped the paragraph child entirely.


## v1.0.0 (2026-04-27)

### Documentation

- **claude-md**: Tighten root and src CLAUDE.md
  ([`7fe01ec`](https://github.com/crouton-labs/termrender/commit/7fe01ec2da0c7a0c1aa0f4eccf9b958496562be8))

### Features

- **mermaid**: Switch to :::mermaid directive, drop backtick fence forms
  ([`083f590`](https://github.com/crouton-labs/termrender/commit/083f5900b4b516f9df599dd08129afee34310e3d))

BREAKING CHANGE: ```mermaid fenced code blocks are no longer rendered as mermaid diagrams — they now
  render as plain code blocks. Mermaid diagrams must use the new :::mermaid directive. The
  MyST-style ```{name} backtick directive form is also removed; backtick fences now always produce a
  code block, regardless of the language tag. Every directive uses ::: exclusively.

### Breaking Changes

- **mermaid**: ```mermaid fenced code blocks are no longer rendered as mermaid diagrams — they now
  render as plain code blocks. Mermaid diagrams must use the new :::mermaid directive. The
  MyST-style ```{name} backtick directive form is also removed; backtick fences now always produce a
  code block, regardless of the language tag. Every directive uses ::: exclusively.


## v0.9.1 (2026-04-25)

### Bug Fixes

- **timeline**: Wrap event text instead of truncating with ellipsis
  ([`5af0e04`](https://github.com/crouton-labs/termrender/commit/5af0e04c3256075a2016e2cf8ae3d44e9e78c8fc))

Long event entries previously got clipped with `…` when they exceeded event_w. Now they wrap across
  multiple lines, with continuation lines indented under the bullet and prefixed by the accent bar.
  Layout height sums per-entry wrapped line counts so the block reserves the right space.


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
