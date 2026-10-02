# Security policy

## Reporting a vulnerability

Please report security vulnerabilities privately, by email to **rhyneer.silas@gmail.com**. Do not open a public GitHub issue or pull request for a suspected vulnerability.

Include what you found, the version (`pip show termrender`) and platform, and the steps or a proof of concept that reproduce it.

Reports are read by a single maintainer, and no response time is guaranteed. Fix timelines depend on severity and on what the fix involves. Say in your report if you want credit in the fix.

## Supported versions

Fixes land on `main` and ship in the next published release of [`termrender`](https://pypi.org/project/termrender/) on PyPI. Only the latest published version is supported.

## What is in scope

The code in this repository: the `termrender` library and CLI. Of particular interest:

- Crafted markdown that makes termrender hang, exhaust memory, or run far longer than its input size warrants.
- Input that makes the output carry terminal escape sequences the document did not ask for.
- The `pane` and `watch` commands running a command or reading a file other than the one they were given.

termrender renders the documents you give it and, for `pane`, runs `tmux` with your user's permissions. That is what it is for, not a vulnerability.
