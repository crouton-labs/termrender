---
kind: knowledge
when-and-why-to-read: When changing or publishing termrender, this knowledge
  should be read because a green PyPI release alone does not put the renderer
  fix into the product surfaces users run.
system-prompt-visibility: content
file-read-visibility: none
origin:
  created: 2026-07-25T01:17:22.493Z
  cwd: /Users/silasrhyneer/Code/cli/crouter
  node: 3zl47w7d-mrznzuss-0d6c2d50
---

## Release handoff

- Humanloop is termrender's sole org-wide binding. It pins an exact PyPI version in `/Users/silasrhyneer/Code/cli/humanloop/src/render/version.ts` and owns the managed renderer venv; other products consume termrender through Humanloop rather than installing it directly.
- After a termrender release is published, continue the delivery chain by bumping Humanloop's `TERMRENDER_VERSION`, verifying its managed-renderer path, and publishing Humanloop. Then follow `crtr memory read humanloop` for the verified downstream consumer chain; do not stop at the termrender publish or assume a local editable/pipx install updated consumers.
