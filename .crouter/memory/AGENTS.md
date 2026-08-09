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

- Crouter is termrender's sole org-wide binding. It pins the exact PyPI release in `src/core/termrender/version.ts` and owns the managed renderer venv; product surfaces consume termrender through crouter rather than installing it directly.
- After publishing termrender, bump crouter's `TERMRENDER_VERSION`, verify the managed-renderer path, and publish crouter. Then bump `CRTR_VERSION` in Northlight's `apps/crouter-guest/build.env` and rebuild/roll the shared guest image used by both Blaxel and local Docker; do not stop at the PyPI release or assume a local install updated consumers.
