# Contributing to termrender

Issues and pull requests are welcome at [github.com/crouton-labs/termrender](https://github.com/crouton-labs/termrender).

## Before you start

- **Bugs:** open an issue with the termrender version (`pip show termrender`), your Python version and OS, and the markdown input that rendered wrongly, with the output you got and the output you expected. `termrender doc check` output helps when the problem is syntax.
- **Features and larger changes:** open an issue first, so the direction is agreed before you write the code.
- **Questions:** ask in [Discord](https://discord.gg/afwW4saEtr) or open an issue.
- **Security problems:** do not open a public issue. See [SECURITY.md](SECURITY.md).

## Set up

You need Python 3.10 or later (`requires-python` in `pyproject.toml`; the release workflow uses 3.12) and [uv](https://docs.astral.sh/uv/), whose `uv.lock` is committed.

```bash
git clone git@github.com:crouton-labs/termrender.git
cd termrender
uv sync
```

`uv sync` installs termrender in editable mode with the `dev` group (pytest). Run the CLI from the checkout with `uv run termrender doc render file.md`.

## Run the tests

```bash
uv run pytest
```

Tests live in [`tests/`](tests) and run against `src/` directly. There is no linter configured.

## Pull requests

- Branch from the current `main`, and keep one change per pull request.
- Describe what changed and why in the pull request body, and say how you tested it.
- Add or update a test for behavior you change. Update the [README](README.md) when you change a directive or a command.
- Read the `CLAUDE.md` files in [`src/termrender/`](src/termrender) and [`src/termrender/renderers/`](src/termrender/renderers) before you change layout, parsing or renderer code. They record constraints that are easy to break.
- Keep the history linear: rebase onto `main` rather than merging it into your branch.
- Commit messages are conventional commits (`fix(mermaid): ...`, `feat: ...`, `docs: ...`). A release workflow reads them on every push to `main`: `feat` makes a minor release and `fix` or `perf` a patch release. It sets the version and edits `CHANGELOG.md`, so do not change either.

## Repository layout

| Path | Contents |
|---|---|
| [`src/termrender/`](src/termrender) | The package: parser, layout, emit, and the `termrender` CLI in `__main__.py` |
| [`src/termrender/renderers/`](src/termrender/renderers) | One module per directive and per mermaid diagram type |
| [`tests/`](tests) | The pytest suite |
| [`assets/`](assets) | README images |

## License

termrender is licensed under MIT. By contributing, you agree that your contribution is licensed under the same terms.
