# CHANGELOG


## v0.2.1 (2026-04-05)

### Bug Fixes

- **mermaid**: Undo double-encoded UTF-8 from mermaid-ascii output
  ([`9e0560c`](https://github.com/CaptainCrouton89/termrender/commit/9e0560ce46b6dc3f90d2d716a97780713e5e5e53))

mermaid-ascii misinterprets UTF-8 bytes as Latin-1 and re-encodes, corrupting multi-byte characters
  (e.g. → renders as â<U+0086><U+0092>). Apply latin-1 round-trip to recover original UTF-8 in both
  layout and renderer subprocess call sites.

### Documentation

- Add tmux pane lifecycle and --check interaction notes to CLAUDE.md
  ([`9400092`](https://github.com/CaptainCrouton89/termrender/commit/9400092e507d470acb97ac5a17b66fcf0e9aa2f6))


## v0.2.0 (2026-04-05)

### Bug Fixes

- Handle zero-width and emoji presentation chars in visual width calculation
  ([`d0bb8dc`](https://github.com/CaptainCrouton89/termrender/commit/d0bb8dcfa5ca0d2c16d78a1d7f81825231b9cb59))

_char_width now returns 0 for combining marks and format characters (ZWJ, variation selectors).
  visual_len handles VS16 emoji presentation sequences by promoting the preceding character to width
  2. Fixes panel border misalignment when content contains emoji or special Unicode.

- **docs**: Update README output examples to match actual rendered output
  ([`de6d0cc`](https://github.com/CaptainCrouton89/termrender/commit/de6d0ccfd8a60aca20f2b2659a313f8d8c87d853))

### Chores

- Add README, design specs, and project CLAUDE.md files
  ([`93ac358`](https://github.com/CaptainCrouton89/termrender/commit/93ac35857981c549797a9359573cacea1478b3ad))

- Derive version from git tags via hatch-vcs
  ([`33595a0`](https://github.com/CaptainCrouton89/termrender/commit/33595a0b64363e445b90c9df135a50a4652e2bae))

### Continuous Integration

- Auto-release and publish via conventional commits
  ([`80a456b`](https://github.com/CaptainCrouton89/termrender/commit/80a456b7301c57f2fd2b0cd30622b78f2d4b931e))

Replace manual GitHub release trigger with python-semantic-release. On push to main, conventional
  commits are analyzed to determine version bumps (feat→minor, fix→patch) and publish to PyPI
  automatically.

### Documentation

- Update README token count and expand CLAUDE.md implementation notes
  ([`1f70a53`](https://github.com/CaptainCrouton89/termrender/commit/1f70a5352cbced30219012dbede7040c6ac97457))

### Features

- Add CJK ambiguous-width support, strict directive parsing, and rendering fixes
  ([`c000883`](https://github.com/CaptainCrouton89/termrender/commit/c0008835d66b721b0a09c7a34dde11d08b3d3d94))

- Add emoji presentation and East Asian ambiguous-width character handling with --cjk flag and
  TERMRENDER_CJK env var - All renderers (borders, divider, quote, tree) now compute box-drawing
  character widths dynamically via visual_len - Parser raises DirectiveError on unclosed or stray
  ::: directives instead of silently degrading - Fix column width distribution to correctly account
  for inter-column gaps - Support 'author' as alias for 'by' attribute on quote blocks

- Add GFM table rendering with box-drawing borders
  ([`c3b61cd`](https://github.com/CaptainCrouton89/termrender/commit/c3b61cdd659fdb782089cbca2fd3f74b18486605))

Enable mistune table plugin, parse table AST into TABLE blocks, and render with box-drawing
  characters. Supports left/center/right column alignment, bold headers, auto-sized columns, and
  proportional overflow distribution.

- **cli**: Add --tmux pane output, --check validation, and structured error handling
  ([`36b52ee`](https://github.com/CaptainCrouton89/termrender/commit/36b52eed9701cd0acd363db2d0fa3d277244c8b0))

- --tmux renders in a new tmux side pane via split-window, piped through less -R - --check validates
  directive syntax without rendering (exit 0/2) - Structured _error() helper with fix/hint guidance
  on stderr - Named exit codes (EXIT_OK, EXIT_INPUT, EXIT_SYNTAX, EXIT_TERMINAL) - Expanded epilog
  with full directive reference, nesting examples, and env docs - Dynamic version from
  importlib.metadata (hatch-vcs) - Updated CLAUDE.md to document --check behavior and fix recursion
  depth note

- **cli**: Improve help output with examples, version flag, and tty detection
  ([`cb3e7e2`](https://github.com/CaptainCrouton89/termrender/commit/cb3e7e2752ae860e5c3cbd4c4f1627e925a9c431))

### Testing

- Add column alignment and visual width tests
  ([`f8b6099`](https://github.com/CaptainCrouton89/termrender/commit/f8b60998625977b10dd4697f8e772d80125cb9ce))

Covers showpiece rendering, column line width consistency, status marker visual widths (text vs
  emoji presentation), and panel border alignment.


## v0.1.0 (2026-04-04)
