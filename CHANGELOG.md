# CHANGELOG


## v4.12.10 (2026-08-22)

### Bug Fixes

- **style**: End an emphasis run with SGR 22/23, never a full reset
  ([`779c604`](https://github.com/crouton-labs/termrender/commit/779c6044f83cf2f81002d4827762b8f2440b6694))

Closing a bold or italic run with SGR 0 also cleared the styling of whatever host embedded the
  output. crouter draws a mermaid diagram inside a chat-transcript region that carries its own
  foreground colour, so the reset landed mid-line and every cell after an emphasized word -- the
  label's padding and the box's right border -- lost that colour while the rest of the diagram kept
  it.

style.py now owns one SGR state model: `_fold_params` folds escapes down to the attributes in force
  (understanding the disable codes as well as reset), and `sgr_transition(current, wanted)` emits
  the escapes that move between two states, turning an attribute off with its own code (22 for
  bold/dim, 23 for italic) and falling back to a reset only for an attribute that has none. The
  mermaid label path, the flow canvas's cell-by-cell label writer, and `style()`'s own close all go
  through it, which also deletes their separate open/close logic. A run carrying a colour still
  closes with a reset: no code restores a colour this process never set.

Escapes cost no display columns, so geometry and `--color off` output are unchanged.


## v4.12.9 (2026-08-22)

### Bug Fixes

- **mermaid**: Render inline emphasis tags in labels as ANSI, not literal text
  ([`dcf5336`](https://github.com/crouton-labs/termrender/commit/dcf5336acaefbe09bbbff1440472b3764785df97))

A node or edge label using the mermaid dialect's own emphasis markup (`<b>`/`<strong>`,
  `<i>`/`<em>`) drew the tags verbatim inside the box: labels were normalized for entity codes and
  `<br/>` only, so the tags fell through as label text.

They now become ANSI SGR runs. `apply_emphasis` runs before entity decoding, so an author-escaped
  `&lt;b&gt;` still renders literally, and nothing outside those four tags is treated as markup.

Every geometry decision keeps measuring visible text: `styled_clusters` and `active_sgr` let the
  flow layout engine wrap, hard-break, center and write a styled label cell by cell without ever
  counting an escape toward a width or slicing one across a cell, and `_carry_sgr` re-opens a run
  that a line break strands. Layout therefore runs color-blind and `--color off` is exactly the same
  picture with the escapes dropped.


## v4.12.8 (2026-08-17)

### Bug Fixes

- **mermaid**: Treat unquoted pipe edge labels as label text, not statement structure
  ([`e210bbb`](https://github.com/crouton-labs/termrender/commit/e210bbb48b026610bcbe4511d7e0ca8f83ea4a31))

### Chores

- **memory**: Migrate memory stores to surfaces routing
  ([`5725d4e`](https://github.com/crouton-labs/termrender/commit/5725d4eab7832b2ee842a2f0a56927aad58a9c76))


## v4.12.7 (2026-08-09)

### Bug Fixes

- **mermaid**: Expose flowchart parse diagnostics
  ([`dd0ec4b`](https://github.com/crouton-labs/termrender/commit/dd0ec4b83fd9958f7238e0103a348358ac374f92))

- **mermaid**: Frames join crossing edges, lanes clear frames, diamond tips anchor arrowheads
  ([`15b33a2`](https://github.com/crouton-labs/termrender/commit/15b33a219b49fa0321c150585a1537d847f96677))

Three flowchart rendering defects, all in the layout engine's own geometry.

Subgraph frame borders now write through the same line bitmask the router draws edges with (no
  EdgeStyle of their own), so a cross-boundary edge crossing a frame resolves into a ┼/┬/├ junction
  instead of overwriting that stretch of border with a bare ─ or │. A frame is more lines on the one
  line plane, not a plane the router cannot see. Node boxes deliberately stay on set_char + reserve
  — an arrowhead is meant to land on a box border. The frame title's own cells drop their border
  bits, since the title genuinely interrupts the top run.

Back-edge lanes now measure past subgraph frames as well as node rects. A frame extends past its
  members by its own padding, so a lane parked at max(node far edge) + _LANE_MARGIN landed on the
  frame's border row/column.

Forward entry/exit anchors are shape-aware for the one shape whose outline does not reach the
  bounding-rect border cell: a diamond's tip in TB/BT, where the outermost taper row is two slant
  glyphs around a blank, reserved cell. The arrowhead used to float inside that notch (╱ ▼ ╲) with
  the line into it skipped as reserved; it now sits one cell out in the inter-rank gap (always
  clear, _ROW_GAP reserves two rows), pointing at the tip. A diamond whose slants do meet at the tip
  row, a diamond too small to taper, LR/RL diamonds, hexagons and parallelograms are all left
  exactly where they were — their tip cell is a real drawn border.

The drawing-time taper calculation, previously copied by hand into _draw_diamond and
  _diamond_straight_span and kept in sync by comment, is now one shared _drawn_diamond_taper the new
  anchor helper reads too.

Regression tests pin all three (each fails against the previous engine) plus a guard that
  hexagon/parallelogram arrowheads stay on their drawn borders.

- **mermaid**: Preserve sequence lifelines at messages
  ([`d46ddf7`](https://github.com/crouton-labs/termrender/commit/d46ddf7220170eae7011fffaac216afb0889405e))

### Documentation

- **memory**: Correct renderer release handoff
  ([`193e2f0`](https://github.com/crouton-labs/termrender/commit/193e2f0f80916d870c364a56d8d06551fa509ced))


## v4.12.6 (2026-07-31)

### Bug Fixes

- Render frontmatter as metadata
  ([`2b00468`](https://github.com/crouton-labs/termrender/commit/2b0046842c50d813f136d559b528b6c752f40c81))


## v4.12.5 (2026-07-30)

### Bug Fixes

- **mermaid**: Treat literal \n as a line break in labels
  ([`6608433`](https://github.com/crouton-labs/termrender/commit/660843363c720d44492a387aa6f9549b1c50093b))


## v4.12.4 (2026-07-29)

### Bug Fixes

- Decode HTML/mermaid entity codes in mermaid labels
  ([`ed96a9a`](https://github.com/crouton-labs/termrender/commit/ed96a9ad8a0fc53a2ddffd001f9f9b86a1705218))


## v4.12.3 (2026-07-25)

### Bug Fixes

- Wrap long mermaid edge labels instead of shredding node labels
  ([`60ee62c`](https://github.com/crouton-labs/termrender/commit/60ee62ca63decb58910e53d4f9b7e59325dff801))

A long edge label was never wrapped, so its text set a hard floor under an LR/RL flowchart's width
  (the label reads along the inter-rank gap). The width-fitting loop, which could only narrow *node*
  labels, then chased a width the edge label already owned — breaking every node label down to the
  6-cell floor, mid-word, while the diagram still overflowed anyway.

Edge labels now wrap through the same word-wrapper node labels use and are placed as a rectangular
  block of rows straddling the run they label. Fitting walks a ladder of (node-label, edge-label)
  budgets whose first rung is today's wrap-nothing layout, so any diagram that already fits renders
  byte-identically in one pass.

Also: when no clear block exists at a vertical segment's own column, the label now slides along its
  rows into clear space instead of writing straight through the boxes crossing that column.


## v4.12.2 (2026-07-25)

### Bug Fixes

- Accept subgraph direction statements
  ([`8ded657`](https://github.com/crouton-labs/termrender/commit/8ded657804952df7ee33e39eb02fca9cf81c8172))

### Documentation

- Record renderer release handoff
  ([`bb6d7f8`](https://github.com/crouton-labs/termrender/commit/bb6d7f8f989b4ad514f5ac98606bd4a20a5c30c4))


## v4.12.1 (2026-07-24)

### Bug Fixes

- **mermaid**: Fit flowchart layout to the requested terminal width
  ([`13296fc`](https://github.com/crouton-labs/termrender/commit/13296fc2220173f0e05ae16aa363493994d00735))

layout_flowgraph discarded its width argument and sized purely to content, so a wide LR flowchart
  with long labels (90 cells for a four-node chain) overflowed any narrower terminal.

It now fits width naturally: the layout is retried with progressively narrower node-label wrap
  budgets and the first result that fits is returned. Topology, the authored direction, and every
  character of content are preserved at every step — a diagram that cannot fit even at the narrowest
  budget renders at its narrowest achievable width rather than being clipped or rotated. The widest
  budget is tried first, so a diagram already inside the width costs one layout pass and renders at
  its natural proportions.

Wrapping moves onto a cell-measured _wrap_label so sizing and drawing agree in display columns, and
  box labels are written through the cell-advancing run writer — a CJK label now wraps by the
  columns it occupies instead of running past the border it was sized to sit inside.

State diagrams and the plain single-label boxes of class/ER diagrams inherit the fit; pre-formatted
  compartments still size to content.

- **mermaid**: Preserve grapheme labels
  ([`7a918ba`](https://github.com/crouton-labs/termrender/commit/7a918baaa4be975df49f6d0472fc2cf48a2c6fcf))


## v4.12.0 (2026-07-23)

### Features

- Leaf-granularity source spans in the line map
  ([`a99247c`](https://github.com/crouton-labs/termrender/commit/a99247cf42f7cfc253960d82d506cfa8835085b4))

render_with_map / doc render --line-map gain a spans field: per rendered row, the finest 1-indexed
  inclusive source range the renderer knows — one span per list item (nested items get their own),
  per table row (header included, adjacent chrome attached), and per fenced/indented code line;
  diagrams, paragraphs, and headings span their whole block. Existing lines/rows/blocks fields are
  unchanged, and the span-aware renderers share the plain render code path so output stays
  byte-identical.

Also stops the list source scanner at a base-indent marker of the other list type (ordered vs
  bullet), which previously over-consumed adjacent lists and pinned the second list's map to the
  range end.


## v4.11.0 (2026-07-23)

### Features

- Emit row-to-source line map via doc render --line-map
  ([`bbc30bf`](https://github.com/crouton-labs/termrender/commit/bbc30bfad4cf33657197995e711e787784be09d8))

render_with_map()/--line-map return {lines, rows, blocks}: rendered ANSI rows, a parallel
  row->top-level-block index map, and per-block 1-indexed inclusive source-line ranges (directives
  span opener..closer; markdown blocks are mapped by a type-directed scanner over the segment
  source). Feeds block-level anchor highlighting in humanloop's terminal review surface.

- Render mermaid git graphs
  ([`8437695`](https://github.com/crouton-labs/termrender/commit/84376953925383dd7d5e3bdb50b41f917fe028f1))

- Render terse Unicode arrow chains
  ([`26603cd`](https://github.com/crouton-labs/termrender/commit/26603cd0ffaec4e7ec3c00bd8526345b78a5f632))


## v4.10.7 (2026-07-10)

### Bug Fixes

- Honor <br/> line breaks and strip quoted-label quotes in flowchart labels
  ([`a05d8d2`](https://github.com/crouton-labs/termrender/commit/a05d8d22344c883d1ee01a0749ee7536e070892d))

- **mermaid-flow**: Parse multiline quoted labels
  ([`2832f3f`](https://github.com/crouton-labs/termrender/commit/2832f3fbcdaa4b6628588ce2120f932faef90073))


## v4.10.6 (2026-07-10)

### Bug Fixes

- **mermaid-flow**: Honor quotes in pipe edge labels so a literal | renders
  ([`dbf0e31`](https://github.com/crouton-labs/termrender/commit/dbf0e310b13d502625bf11e15c2bf683ff7242a4))

A quoted edge label (-->|"a | b"|) is valid mermaid.js — the pipe delimiter closes on the quote, not
  the first inner |. The plabel capture used [^|]*, so a | inside a quoted label ended the capture
  early, the edge failed to parse, and strict degradation raw-echoed the whole diagram (crtr then
  shows source instead of the picture). Widen the capture to accept a "..." quoted segment.
  Regression test added.

### Documentation

- **mermaid-flow**: State lane-routing invariants without old-behavior narration
  ([`6af57f1`](https://github.com/crouton-labs/termrender/commit/6af57f14d54bfa3d83d756232d8a187bb16a4d9e))


## v4.10.5 (2026-07-07)

### Bug Fixes

- **mermaid-flow**: Route back-edge labels clear of node boxes
  ([`54a0c31`](https://github.com/crouton-labs/termrender/commit/54a0c317f609c618bb2d6c8062eb65150f398f5b))

A back-edge's C-path lane column was sized from just its own two endpoints (src/dst), not every node
  in the graph, so its horizontal exit/entry legs — which travel along the source's/destination's
  own rank-band row, a row every rank-mate box also occupies — could run straight through (and its
  label land inside) whichever sibling boxes sat between the endpoint and the lane column.

- _lane_secondary_base now reaches past every placed node's far edge, not just the one back-edge's
  own src/dst boxes. - A back-edge's label always addresses its own dedicated lane (middle) segment
  directly, mirroring _forward_row_overrides' existing jog-segment addressing, instead of
  _longest_segment's raw-length heuristic — which could pick a crowded exit/entry leg over the
  genuinely open lane column whenever a source rank was wide. - Replaced the flat per-back-edge
  lane_counter increment with _lane_offsets: a precomputed, label-width-aware step (mirrors
  _rank_gap_overrides for the rank axis) so two labeled back-edges landing near each other get
  pushed apart enough for both labels to read with a clear buffer, not flush against each other's
  lane line. - The vertical-segment label-placement branch now prefers a buffered row (like the
  horizontal branch's _row_clear_span) before falling back to an unbuffered one, closing the same
  fused-against-a-foreign- line defect for lane labels that the prior session closed for jog labels.

Regression tests: an engine-level FlowGraph case (crowded source rank) in
  test_mermaid_flow_layout.py, and the exact classDiagram repro in test_mermaid_class.py — both
  assert the label doesn't overlap any node's box cells and fail against the pre-fix commit.


## v4.10.4 (2026-07-07)

### Bug Fixes

- **mermaid-flow**: Separate labels around crowded junctions
  ([`c089c6f`](https://github.com/crouton-labs/termrender/commit/c089c6fd42ef079a3e6d33b6d78f4978f12c9ccf))

Multiple labeled edges converging or diverging on one node (a stateDiagram/flowchart junction with
  several labeled transitions) used to collide: a Z-path's jog segment can be much shorter than its
  own label text, and every edge crossing the same two ranks shares one default jog row, so labels
  fused onto each other, fused onto a box border, or were silently dropped by the reserved-cell
  fallback.

- Widen a horizontal label's search window to the row's real clear span
  (_row_clear_span/_cell_blocks_label), not just its own short segment, treating sibling connector
  lines and already-placed labels as blocking alongside box borders. - Give each labeled forward
  edge crossing a shared inter-rank band its own jog row (_forward_row_overrides), with the band
  pre-widened by count (_rank_gap_overrides), instead of stacking every sibling on one row. - Clamp
  _label_positions to its [lo, hi] run so a vertical-segment search can no longer wander past its
  own span into blank rows below the whole diagram. - Exempt only genuine bend corners (not
  arrowhead-adjacent anchors) from the label placement buffer, and broaden _spread_group_anchors to
  treat a labeled edge as needing anchor spread, not just a marked one.

Regression tests added for the engine (multiple labeled edges converging/ diverging on one node) and
  the stateDiagram adversarial repro; smoke tests for a flowchart decision node's labeled
  fan-in/fan-out and a class diagram with multiple labeled UML relationships around one class.

### Testing

- **mermaid**: Rephrase native regression comments
  ([`011bcf2`](https://github.com/crouton-labs/termrender/commit/011bcf2f2fb3b50699a98d295f3b7371c2b92f9f))


## v4.10.3 (2026-07-07)

### Bug Fixes

- **mermaid**: Strict degradation — unrecognized syntax raw-echoes instead of half-rendering
  ([`904d1cc`](https://github.com/crouton-labs/termrender/commit/904d1ccaa5c012bbeefdc8f351fb25164b0c3778))

Enforce the native Mermaid degradation contract across flowchart, classDiagram, stateDiagram-v2, and
  erDiagram renderers: only well-formed presentational/accessibility directives are skipped, while
  unsupported statements, dangling connectors, stray closers, and unterminated structural blocks now
  fail parsing and raw-echo the entire original source.

Consolidate raw-echo glyph scrubbing in mermaid_degradation.py and update the dispatcher/renderers
  to import the shared helper so every degradation path removes box/geometric glyphs consistently.

Flip the parser-level tests that previously pinned best-effort recovery for malformed flowcharts to
  expect FlowchartError, and flip the state stray-close-brace render test to expect raw echo. Add
  regression coverage for the review repros, malformed directive-shaped lines, valid accessibility
  colon forms, and native rendering of valid presentational directives.

Refresh renderer docs and architecture metadata away from the removed Go/mermaid-ascii path, and add
  minimal pytest project config so the required exact 'uv run pytest' gate imports the src package
  in this repository.


## v4.10.2 (2026-07-07)

### Bug Fixes

- **mermaid-flow**: Split entry anchors and cjk labels
  ([`0d5160d`](https://github.com/crouton-labs/termrender/commit/0d5160d18f719f3045e552236e38b640ab967b13))


## v4.10.1 (2026-07-07)

### Bug Fixes

- **mermaid-flow**: Constant inter-layer gap regardless of node height
  ([`eb1726f`](https://github.com/crouton-labs/termrender/commit/eb1726fa4bd05a57d29026b10715edc067ac4113))

The rank-band gap override that widens spacing to fit a labeled edge scaled with visual_len(label)
  (the label's *text width*) even on TB/BT diagrams, where the label is drawn horizontally across a
  vertical connector and only ever needs one clear row, not one row per character. Since ER/class
  diagrams route almost every edge through a label (relationship text, cardinality), this made
  compartmented-node TB layouts burn ~15-17 blank connector rows per edge hop while 1-line-node
  flowcharts stayed compact — node height was a red herring; the real driver was label width feeding
  a row count.

_rank_gap_overrides is now direction-aware: LR/RL keeps the width-scaled gap (the transpose turns
  that native row-band into the final horizontal run the label reads along, so it genuinely needs
  the width). TB/BT gets a small constant, _LABELED_ROW_GAP=3, regardless of label length.

Updates the two TB labeled-edge goldens in test_mermaid_flow_corpus.py to the new compact spacing,
  and adds a regression test in test_mermaid_er.py pinning a row budget for compartmented entities
  so this doesn't regress.


## v4.10.0 (2026-07-07)

### Features

- **mermaid**: Native dispatch for flowchart/class/state/er, drop vendored Go binary
  ([`6935f30`](https://github.com/crouton-labs/termrender/commit/6935f30a1dccfefcc34344de02191f8481d53668))

Wire the four previously-unwired native renderers into mermaid.py's first-line dispatcher:
  flowchart/graph -> mermaid_flow.render_flowchart, classDiagram -> mermaid_class.render_class,
  stateDiagram/-v2 -> mermaid_state.render_state, erDiagram -> mermaid_er.render_er. Every mermaid
  type termrender renders is now native Python; no diagram type shells out anymore.

Unrecognized/exotic types (sankey, C4, gitgraph, block, packet, kanban, quadrantChart, ...) degrade
  in the dispatcher itself to a raw echo of the source with box-drawing/geometric glyphs stripped,
  preserving the contract the crouter attach viewer relies on to detect render failure by glyph
  absence.

Delete the vendored Go path entirely: src/termrender/_bin/ (binary), src/termrender/_mermaid_bin.py,
  scripts/build-mermaid-ascii.sh, the mermaid-ascii runtime dependency and hatch artifacts stanza in
  pyproject.toml (relocked via uv.lock), and scripts/mermaid_flow_parity.py (a standalone dev-only
  harness comparing native output against the now-deleted binary).

tests/test_mermaid_compat.py pinned Go-era preprocessing (preprocess_mermaid_for_ascii) that no
  longer exists; deleted wholesale since dispatch/prelude contracts it also touched already live in
  test_mermaid_dispatch.py. That file's routing tests are updated for the four newly-wired types and
  gain dispatch tests for the exotic raw-echo path (including a no-native-renderer-called assertion
  and a glyph-range sweep pinning the no-box-glyph contract).

Swept src/termrender/renderers/CLAUDE.md and README.md to current-state only; no remaining
  references to mermaid-ascii/_mermaid_bin/the Go binary anywhere in the tree.


## v4.9.1 (2026-07-07)

### Bug Fixes

- **mermaid-flow**: Stop dropping edge labels/markers on a shared exit anchor
  ([`552d3d3`](https://github.com/crouton-labs/termrender/commit/552d3d3deef061e23c5b894852ae024065366eb8))

When 2+ edges leave one node through the router's single fixed exit anchor (e.g. two forward edges
  in LR/RL, or a diamond node's right side), two defects followed:

- Label drop: the shared first segment of each edge's Z-path could tie in length with each edge's
  own distinguishing segment further along - routine in LR/RL, where a node's fan-out run and its
  branch runs often measure the same few cells. _longest_segment's old first-wins tie-break always
  picked that shared segment for both edges' labels, so the second label landed on cells the first
  already claimed and silently vanished. Fixed by breaking ties toward the *last* segment instead -
  the segment nearest each edge's own destination, which is never shared. TB is unaffected (its
  branch runs are typically much longer than the shared trunk, so no tie exists there to begin
  with).

- Marker drop: a source-side arrow-kind marker glyph (UML composition and aggregation diamonds)
  drawn at the shared anchor cell survived only for the last-drawn edge. Fixed via a new pre-pass,
  _allocate_edge_anchors, that spreads a group's exit points along the node's side - but only when
  2+ of that group's edges actually carry a source-side marker. Plain, markerless fan-outs (by far
  the common case) keep sharing one exit cell, since that's what makes draw_segment's junction
  bitmask resolve into a single clean tee rather than two disjoint stubs - spreading those would
  only change where the fan visually splits, not fix anything, and would break the existing
  trunk-then-tee golden output for every unlabeled fan-out/merge case.

Anchor spreading is shape-aware for NodeShape.DIAMOND (the only shape whose left/right sides aren't
  straight across their full bounding-rect span) so a spread point never lands in the diamond's
  tapered corner region.

Removes the "known limitation" paragraph from mermaid_class.py's docstring now that the
  composition/aggregation marker case it described is fixed.

Goldens touched: added test_lr_fan_out_with_labels_both_present_golden (new - pins the fixed LR
  output, previously buggy/missing) and test_two_source_side_markers_from_one_class_both_survive
  (new). No existing golden was changed - the fan-out/merge goldens (test_fan_out_golden,
  test_multi_parent_dag_golden, test_td_direction_golden, test_lr_direction_golden) are
  byte-for-byte unchanged because none of their edges carry a source-side marker, so the new
  anchor-spread never triggers for them.


## v4.9.0 (2026-07-07)

### Features

- **mermaid-er**: Native erDiagram renderer
  ([`caae993`](https://github.com/crouton-labs/termrender/commit/caae9930b6a996e33b401dc773c5a9aae01b1529))

Parses mermaid erDiagram source (entity attribute blocks with PK/FK/UK markers and quoted comments,
  bare entities, the full crow's-foot cardinality grammar in both writing directions, identifying/
  non-identifying relationship lines, entity/attribute aliasing and quoted names) into the shared
  FlowGraph model and hands it to the existing layout_flowgraph engine (compartmented boxes, edge
  labels). Never crashes: unparseable input degrades to a raw echo with no box-drawing glyphs,
  matching mermaid_class.py's contract.

Not wired into mermaid.py's dispatcher (later phase). Read-only against mermaid_flow*.py.


## v4.8.0 (2026-07-07)

### Features

- Native mermaid stateDiagram renderer on the flowchart engine
  ([`ff4fa87`](https://github.com/crouton-labs/termrender/commit/ff4fa87d275d0e18f64e386c16e13e237ad99923))

Adds src/termrender/renderers/mermaid_state.py exposing render_state(source, width) -> list[str] as
  a thin adapter: parses stateDiagram/stateDiagram-v2 grammar into the existing flowchart engine's
  own FlowGraph/FlowNode/FlowEdge/Subgraph model and renders through layout_flowgraph directly
  (grandalf layout, box rasterizer, orthogonal router, subgraph frames), reusing that engine's
  degradation contract unchanged.

Covers: A --> B / A --> B : event transitions; [*] as per-scope start/end pseudo-states (distinct
  compact glyph markers, shared across every [*] reference in one scope); state "Long name" as s1
  aliases; state X { ... } composite states as nested subgraph frames (a composite referenced
  directly by an external transition gets its own proxy box, since the engine has no edge-to-frame
  anchor); <<choice>> as a diamond, <<fork>>/<<join>> degrading to the engine's plain small rect;
  direction LR/TD/RL/BT; note left/right of X (inline and multi-line note/end note forms) attached
  via a headless dotted edge so text is never dropped; %% comments skipped anywhere including inside
  note blocks; -- / --- concurrency separators flattened.

Unwired: not imported by mermaid.py's dispatcher (later phase). Only touches new files; the
  flowchart engine files remain untouched (read-only, per a concurrent sibling's ownership).

tests/test_mermaid_state.py: 24 tests asserting real topology/geometry (row/column ordering, frame
  containment, distinct start/end glyphs, diamond-shape glyphs, label text) across a simple
  start/end machine, labeled transitions, aliases, choice/fork/join, composite + nested composite
  states, inline/multi-line notes, direction LR, comments, and the degradation contract
  (header-missing, zero-node, and crash-guard echo paths, each pinned to the same three-condition
  rule the flowchart engine's own tests already establish — best-effort recoverable body-level
  glitches, like a stray '}' or an unterminated composite/note, render real content rather than
  forcing an echo, matching mermaid_flow_parser.py's documented 'auto-closed rather than dropped' /
  'consumed silently, best-effort' policy).


## v4.7.0 (2026-07-07)

### Features

- **mermaid-class**: Native classDiagram renderer
  ([`32d6c8c`](https://github.com/crouton-labs/termrender/commit/32d6c8cda0e654120ac2647fe2613f2b06fbb07d))

render_class(source, width) -> list[str] in mermaid_class.py, unwired (not imported by mermaid.py's
  dispatcher). Standalone module matching mermaid_sequence.py/mermaid_flow.py's shape: own parser,
  own tests, no Block/pipeline dependency.

Parses classDiagram source (class blocks with member lines, member-association form, bare
  declarations, <<stereotype>> annotations, ~T~ generics, direction) into the shared
  FlowGraph/FlowNode/FlowEdge model and hands it to the flowchart engine's layout_flowgraph, using
  the new compartments and arrow-kind extensions. Covers all six UML relationship kinds
  (inheritance, composition, aggregation, association, dependency, realization) plus the two
  headless link forms, both marker-writing directions (<|-- / --|>), quoted cardinalities combined
  with edge labels, and never-crash raw-echo degradation (missing header, empty body, malformed
  input, literal box-glyph sanitization).

24 new golden/topology tests in tests/test_mermaid_class.py; full suite (503 tests) green.

- **mermaid-flow**: Support compartmented nodes and UML arrow-kind glyphs
  ([`2b1441c`](https://github.com/crouton-labs/termrender/commit/2b1441cd707621870651c0c391f603c60f8d3529))

Extend the flowchart engine with two opt-in, backward-compatible hooks so UML-flavored renderers
  (mermaid classDiagram) can reuse grandalf layout + rasterization + orthogonal routing without
  duplicating it:

- FlowNode.compartments: list[list[str]] | None draws a multi-line box with a horizontal separator
  row between compartments (UML name/ fields/methods bands) instead of the single wrapped label.
  None (the default) is byte-for-byte the original single-label path. -
  FlowEdge.dst_arrow_kind/src_arrow_kind (default "default") select an arrowhead glyph family
  independent of style/line weight: triangle_hollow (inheritance/realization), diamond_filled
  (composition), diamond_hollow (aggregation) — layered on top of the existing direction-computed
  \u25bc\u25b2\u25b6\u25c0 selection.

All 479 pre-existing tests pass unmodified; every new field defaults to the prior behavior.


## v4.6.3 (2026-07-07)

### Bug Fixes

- Commit uv.lock resolution for grandalf runtime dependency
  ([`0b2a39e`](https://github.com/crouton-labs/termrender/commit/0b2a39ee4440a907c309328920062e543fd5e47e))


## v4.6.2 (2026-07-07)

### Bug Fixes

- **mermaid-flow**: Preserve edge labels, render self-loops, sanitize degraded echo
  ([`263100f`](https://github.com/crouton-labs/termrender/commit/263100f16e1a7f0044497f2dedd0fd10f0831626))

- Router now draws all edge polylines+arrowheads first, then all edge labels last (reserving each
  label's cells, plus a margin), so a later edge's line can never silently erase an earlier edge's
  label and two labels sharing a lane render with visible separation instead of concatenating. -
  Rank-band gaps widen to fit an adjacent-rank edge's label in full (_rank_gap_overrides), fixing
  short LR/forward-adjacent labeled edges (e.g. "hello") that were previously clipped to a couple of
  characters. - Raw-echo degradation now strips any box-drawing/geometric glyph (\u2500-\u259f,
  \u25a0-\u25ff) present in the malformed source itself, so a degraded echo can never be misdetected
  as a successful render. - Hardened green-theatre tests: self-loop tests now assert real loop
  geometry (arrowhead + glyphs past the box border) instead of "non-empty output"; the
  edge-visibility test now inspects the guaranteed-clear inter-box gap instead of accepting
  box-border glyphs; cycle/labeled-back-edge/direction/never-raises tests gained genuine
  topology/degradation assertions in place of crash-only checks. - Updated the two corpus goldens
  (pipe-label, inline-label) whose rendered height changed under the new label-aware gap widening.


## v4.6.1 (2026-07-07)

### Bug Fixes

- **mermaid-flow**: Parse chained edges and bracket-aware tokenization
  ([`5040b96`](https://github.com/crouton-labs/termrender/commit/5040b967bbe75c70c6d03d57930742ba020e3333))

- Unify edge parsing behind one bracket-depth-aware connector scanner (_scan_connectors) shared with
  & fan-out splitting and ; statement splitting, replacing the single-connector _EDGE_RE. -
  CRITICAL: chained edge statements (A-->B-->C) now parse as a sequence of node groups separated by
  connectors, emitting one edge per adjacent triple instead of dropping the tail after the first
  connector. - MAJOR: connector-looking text inside [], (), {} labels (A[Go --> Fast]) is no longer
  mistaken for an edge connector. - MINOR: semicolons inside labels (A[Check; validate]) no longer
  split the statement.

Adds structural tests for 2/3-link chains, mixed-style chains, chain with inline label,
  connector-in-label for all three connector families, and semicolon-in-label. Adds a chained-form
  golden for the labeled back-edge cycle proving identical render to the separate-line form.

### Testing

- Add flowchart golden corpus and go-binary parity harness
  ([`2a5a00a`](https://github.com/crouton-labs/termrender/commit/2a5a00aba18195eac987bc8c202a80724d6e43c9))

- tests/test_mermaid_flow_corpus.py: 26 golden-output tests pinning exact render_flowchart() lines
  across all 9 node shapes, every edge style (solid/dotted/thick/headless/bidirectional), both label
  forms, & fan-out, a multi-parent DAG, a labeled-back-edge cycle (the case the vendored Go binary
  panics/mis-parses on), LR vs TD, subgraph + nested subgraph, a long label vs a tight width budget,
  and the two degradation paths. - scripts/mermaid_flow_parity.py: standalone parity harness (not a
  pytest dependency) that invokes the vendored Go binary the way termrender's real dispatch path
  does (preprocess_mermaid_for_ascii + fix_mermaid_encoding) and the native renderer side by side
  across 14 representative inputs, writing the comparison to the orchestrator's shared context dir.
  Confirms parity-or-better plus two Go failure modes the native renderer avoids: a self-loop panic
  (index out of range) and labeled-back-edge mis-parsing (label text swallowed into a phantom node
  instead of a back-edge). - fix: mermaid_flow.py's module docstring described a stale prior phase
  ("every shape renders as a plain rectangle", "subgraphs parse but aren't drawn as frames") — both
  are false now; corrected to describe actual current behavior (distinct shape borders, framed
  subgraphs with contiguous-membership flattening).

463 tests green (437 pre-existing + 26 new corpus).


## v4.6.0 (2026-07-06)

### Features

- Add flowchart node shapes, subgraph frames, and direction rendering
  ([`e872199`](https://github.com/crouton-labs/termrender/commit/e87219956294319feb0015d2cf4573b8cc60a0cb))

Applies and hardens the salvaged decoration work for the native mermaid flowchart renderer's layout
  engine:

- Nine distinct node-shape borders (rect, round, stadium, cylinder, circle, diamond, hexagon,
  subroutine, parallelogram), each reserving its full bounding box so the router treats every shape
  as impassable. - Subgraph enclosure frames (left-anchored title, nested, flatten when members
  aren't placed contiguously enough for a clean rect). - TB/BT/LR/RL direction handling via a
  post-layout coordinate transform.

Fixes found while hardening: - draw_frame now reserves the title text cells (not the whole border)
  so a cross-boundary edge crossing a frame's top border can no longer clobber a letter of the
  subgraph title. - Subgraph frame sizing is now computed bottom-up (_build_subgraph_frames): a
  parent subgraph's extent is built from its children's *padded frame rects* (when they get a frame)
  rather than raw member extents, so a nested subgraph whose members share the same column/row span
  as its parent no longer produces an identically-sized frame that overwrites the parent's border —
  nesting now always has real margin. - Corrected the module docstring's stale "every node renders
  as a plain rectangle, frames not yet wired" description to match the shipped shape/frame drawers.

Adds tests/test_mermaid_flow_shapes.py: real-geometry assertions for shape distinctness, a 9-shape
  gallery, subgraph frame containment, nested-frame non-overlap, non-contiguous-subgraph flatten,
  LR/RL/BT topology + arrowhead direction, LR same-rank spacing, and router avoidance of a diamond's
  interior. Full suite: 437 passed (422 existing + 15 new), no regressions.


## v4.5.0 (2026-07-06)

### Features

- Add flowchart edge router and public render_flowchart
  ([`a1b46cf`](https://github.com/crouton-labs/termrender/commit/a1b46cf11607ec6b31ea8fe1b4d90b11aafff10f))

- Replace the placeholder edge drawing in mermaid_flow_layout.py with the full orthogonal router:
  rank-relative endpoint anchors (forward/same-rank/ back-edge), L/Z staircase paths for forward
  edges, growing side-lane C-paths for back-edges so they never overlay forward edges, arrowheads
  chosen from final-segment direction, edge labels centered on the longest straight run (shifting
  off reserved cells), and self-loops modeled on the sequence renderer's self-message loop. - Add
  mermaid_flow.py exposing the public, pure, never-raising render_flowchart(source, width) ->
  list[str], wiring parse -> layout_flowgraph -> lines behind the three-case degradation contract
  (no header, zero nodes, unexpected layout exception -> raw echo). - Add
  tests/test_mermaid_flow.py: real end-to-end geometry/topology assertions, including the labeled
  back-edge cycle that panics the Go binary, multi-parent attachment, headless edges, and echo
  degradation.

Unwired: nothing imports mermaid_flow yet (later phase's cutover).


## v4.4.0 (2026-07-06)

### Features

- Add flowchart layout engine core (grandalf adapter + canvas rasterizer)
  ([`23e26e9`](https://github.com/crouton-labs/termrender/commit/23e26e9c3228bfac302c270b4c0c5ffe880bfc20))

- Add flowchart mermaid parser
  ([`c9c80c3`](https://github.com/crouton-labs/termrender/commit/c9c80c30ed638c3532ef9464ce1cb7f4af4fa3ce))


## v4.3.2 (2026-07-06)

### Bug Fixes

- **mermaid**: Strip %% comments/directives from journey/mindmap/timeline
  ([`d61f113`](https://github.com/crouton-labs/termrender/commit/d61f113cf750c9379f00825e2f6fc7b3898e7b8f))

The dispatcher (mermaid.py) only used strip_prelude_lines() for type sniffing, then passed the
  untouched original source to the native renderers, so a leading %%{init}%% directive or a mid-body
  %% comment leaked into rendered output as fake tree nodes, task rows, or timeline events in the
  journey/mindmap/timeline renderers.

- mermaid.py: pass prelude-stripped source to the three native renderers; the Go-binary fallback
  path keeps receiving the raw source untouched. - mermaid_journey.py, mermaid_mindmap.py,
  mermaid_timeline.py: skip %%-prefixed lines anywhere in the body, not just the leading prelude,
  mirroring mermaid_sequence.py's existing handling.

Adds regression tests pinning each confirmed repro to render nothing from the comment/directive.


## v4.3.1 (2026-07-06)

### Bug Fixes

- **mermaid-gantt**: Close remaining overflow and includes gaps from review
  ([`73a1354`](https://github.com/crouton-labs/termrender/commit/73a135465644073d58e293ed69e6ca968d4f5a05))

- _skip_excluded() and the implicit +1-day default end could still raise OverflowError past
  datetime.max; both call sites now catch it and degrade the whole diagram to source instead of
  crashing. - includes weekends was accepted but silently no-op'd (excludes weekends + includes
  weekends still rendered the excluded schedule); includes now only supports explicit YYYY-MM-DD
  dates and rejects weekends as _Unsupported rather than pretending to cancel the exclusion.

fix(mermaid-pie): reject invalid trailing header grammar

pie bogus (anything after pie/pie showData that isn't a valid inline title) was silently accepted
  and rendered a plausible chart; it now degrades the whole diagram to source, matching the
  strictness already applied to other invalid pie lines.

- **mermaid-gantt**: Implement excludes/includes, milestone, until; never-crash on bad
  dateFormat/overflow
  ([`e182ae1`](https://github.com/crouton-labs/termrender/commit/e182ae1346af7fa4a531ad0014878e06caf5304e))

Several valid Mermaid gantt constructs rendered false schedules, and malformed input could crash:

- A malformed dateFormat (e.g. YYYY-YYYY, whose translated strptime pattern has a duplicate capture
  group) raised re.error instead of being caught; the format is now validated by round-tripping a
  sample date and an invalid format degrades the whole diagram to source. - Huge numeric durations
  (e.g. 1000000000d) overflowed timedelta/datetime arithmetic; overflow is now caught and degrades
  the whole diagram. - excludes weekends / excludes <YYYY-MM-DD> and includes <YYYY-MM-DD> are now
  applied when resolving durations and auto-anchored start dates, instead of being ignored as
  decorative metadata. An excludes/includes form we don't implement (e.g. day names) degrades the
  whole diagram rather than rendering a false schedule. - milestone tasks are now tracked as
  point-in-time markers (rendered as a single diamond marker) instead of ordinary duration spans. -
  until <taskId> is now resolved to the referenced task's start date; an unknown reference degrades
  the whole diagram. - %% comments (whole-line and trailing inline) are stripped before
  tokenization, so a comment containing a colon can no longer be misparsed as a task.

- **mermaid-pie**: Degrade to source on invalid grammar, negative or overflowing values
  ([`765f613`](https://github.com/crouton-labs/termrender/commit/765f613d9e1b72ff79e8f0c32ac8d9f9cdceef69))

Native pie parsing previously treated any non-matching line as a silent ignorable and accepted
  negative slice values, so malformed input rendered a plausible-but-wrong partial chart instead of
  falling back to source. Arbitrarily long numeric literals could also reach charts._format_value()
  as float('inf') and raise OverflowError.

- Invalid grammar (anything beyond header/title/accTitle/accDescr/%% comments/slice lines) now
  discards the whole diagram and falls back to raw source, matching Mermaid's actual pie grammar. -
  Negative slice values are rejected the same way (Mermaid disallows them). - Non-finite values
  (from huge numeric literals) are rejected in parse_pie, and the summed total is re-checked in
  render() as a second guard, both falling back to source instead of crashing. - Slice labels now
  also accept single-quoted strings and escaped quotes inside double-quoted strings, per Mermaid's
  real string grammar.


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
