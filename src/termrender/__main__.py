"""CLI entry point for termrender — frozen agent-oriented API contract."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, NoReturn

from termrender import render, render_with_map, TerminalError, DirectiveError

_MISSING = object()

# Exit codes
EXIT_OK = 0
EXIT_INPUT = 1    # bad invocation, missing required, not-in-tmux, tmux-missing, pane-gone
EXIT_SYNTAX = 2   # directive syntax / nesting error, pre-check failure
EXIT_TERMINAL = 3 # terminal capability error

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("termrender")
except Exception:
    __version__ = "dev"


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------

_ROOT_HELP = f"""\
termrender {__version__}

Render directive-flavored markdown as rich ANSI terminal output.

Concepts
  doc     a markdown document rendered to ANSI
  pane    a tmux side-pane displaying a rendered document

Subtrees
  doc     render, check, or watch a markdown document  | use when working with document content
  pane    manage a tmux side-pane renderer              | use when managing a persistent display pane

Globals
  -h      print -h for any node or leaf

I/O contract: flags and positional args on input, ANSI on stdout for doc render,
JSON on stdout for all other leaves. Errors are JSON on stdout, exit non-zero.
Exit 0 on success, 1 input error, 2 syntax/nesting error, 3 terminal capability error.

Stable error codes: bad_invocation bad_input syntax_error nesting_error
                    terminal_error not_in_tmux tmux_missing pane_gone internal
"""

_DOC_HELP = """\
termrender doc — document rendering commands.
A document is a markdown source string rendered to ANSI terminal output.

Branches
  render  render markdown to ANSI and print to stdout   | use when producing output for display
  check   validate directive syntax without rendering    | use when validating before rendering
  watch   live-render a file, updating on every save     | use when monitoring a file interactively

Document format
  Directive-flavored markdown. Triple-colon blocks carry attributes in {} and
  nest by COLON COUNT: an outer block needs strictly MORE colons than the block
  nested inside it (::::columns wraps :::col), and each block closes with a bare
  run of its own colon count on its own line. Plain markdown (headings, **bold**,
  *italic*, `code`, bullet/numbered lists) works everywhere, including inside
  directives. Write structure, not box-drawing — layout, padding, and guide
  lines are computed.

  :::panel{title="" color=""}            bordered box; color e.g. green|cyan|red
  ::::columns / :::col{width="N%"}       side-by-side; col widths sum to 100%
  :::tree{color=""}                      indentation → Unicode guide lines;
                                         [x]=done [!]=warning status markers
  :::callout{type=""}                     admonition; type success|warning|error|info
  :::divider{label=""}                    labeled horizontal rule
  :::code{lang=""}                        syntax-highlighted block (``` fences also work)
  :::quote{author=""}                     attributed block quote
  :::mermaid                             flowchart → ASCII (``` mermaid fences also work)
  ```text A → B → C                     three-stage Unicode-arrow process → diagram
"""

_DOC_RENDER_HELP = """\
termrender doc render: render a markdown document to ANSI and write to stdout.

Input
  stdin              required. Markdown source to render. Pipe via: cat file.md | termrender doc render
  --width N          optional int. Output width in columns. Omit for auto-detect from terminal.
  --color auto|on|off  optional. Force color on/off, or auto-detect (default auto).
  --cjk              optional boolean. When present, treat ambiguous-width Unicode as double-width.
  --line-map         optional boolean. When present, output JSON instead of raw ANSI:
                     {lines: string[], rows: (int|null)[], blocks: {type,start,end}[],
                      spans: ([start,end]|null)[]}
                     lines are the rendered ANSI rows; rows[i] is the index into blocks
                     of the top-level source block that produced lines[i] (null for the
                     separator rows between blocks); blocks carry 1-indexed inclusive
                     source-line bounds (start/end may be null when unmappable);
                     spans[i] is the finest known 1-indexed inclusive source range for
                     lines[i] — list-item, table-row, or code-line granularity where
                     available, else the whole block (null for separators/unmapped).

Output (stdout, ANSI)
  The rendered ANSI string. This leaf outputs ANSI, not JSON, on success —
  unless --line-map is present, in which case it outputs the JSON object above.

Effects
  None. Read-only.
"""

_DOC_CHECK_HELP = """\
termrender doc check: validate directive syntax without rendering.

Input
  stdin   required. Markdown source to validate. Pipe via: cat file.md | termrender doc check
  --cjk   optional boolean. When present, treat ambiguous-width Unicode as double-width.

Output (stdout, JSON)
  ok      bool. True when source is valid.
  errors  object[]. Each: {kind: "syntax"|"nesting", message: string}. Empty when ok is true.

Effects
  None. Read-only. Exit 0 when ok, 2 when not ok.
"""

_DOC_WATCH_HELP = """\
termrender doc watch: live-render a file in the controlling terminal, updating on every save.

WARNING: takes over the controlling terminal until quit (q or Ctrl-C).
Intended for human interactive use or as the process inside a tmux pane.

Input
  PATH               positional, required. File path to watch and re-render on change.
  --color auto|on|off  optional. Force color on/off, or auto-detect (default auto).
  --cjk              optional boolean. When present, treat ambiguous-width Unicode as double-width.

Output (stdout, ANSI)
  Renders directly to the controlling terminal. No JSON output.

Effects
  Takes over the controlling terminal until quit. Exit 0 on quit.
"""

_PANE_HELP = """\
termrender pane — tmux pane management commands.
A pane is a persistent tmux split showing a live-rendered document.

Branches
  open    spawn a new tmux pane rendering a file    | use when starting a new side-pane display
  update  respawn an existing pane with new content  | use when pointing an existing pane at new content
"""

_PANE_OPEN_HELP = """\
termrender pane open: spawn a tmux pane rendering a file. Returns immediately.
Requires: running inside an active tmux session.

Input
  PATH               positional, required. File to render in the pane.
  --width N          optional int. Pane width in columns. Omit for auto-size from window.
  --color auto|on|off  optional. Force color on/off, or auto-detect (default auto).
  --cjk              optional boolean. When present, treat ambiguous-width Unicode as double-width.
  --watch            optional boolean. When present, live-update the pane on file save (default false).
  --window split|new   optional. Split current pane or open a new tmux window (default split).

Output (stdout, JSON)
  pane_id   string. Tmux pane id. Use with termrender pane update.

Effects
  Spawns a detached tmux pane (split or new window) running the renderer.
  The pane lives until closed by the user or the process terminates.
"""

_PANE_UPDATE_HELP = """\
termrender pane update: respawn an existing tmux pane with new content. Pane id is unchanged.
Requires: running inside an active tmux session.

Input
  PATH               positional, required. New file to render in the pane.
  --pane-id ID       required. Tmux pane id to update (e.g. "%23").
  --width N          optional int. Override pane width in columns. Omit to read from pane.
  --color auto|on|off  optional. Force color on/off, or auto-detect (default auto).
  --cjk              optional boolean. When present, treat ambiguous-width Unicode as double-width.
  --watch            optional boolean. When present, live-update the pane on file save (default false).

Output (stdout, JSON)
  pane_id   string. Same pane id as --pane-id input.

Effects
  Replaces the process in the target pane.
"""


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def _json_error(
    error: str,
    message: str,
    *,
    received: Any = _MISSING,
    field: str | None = None,
    next_: str,
    code: int = EXIT_INPUT,
) -> NoReturn:
    obj: dict[str, Any] = {"error": error, "message": message}
    if received is not _MISSING:
        obj["received"] = received
    if field is not None:
        obj["field"] = field
    obj["next"] = next_
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()
    sys.exit(code)


def _resolve_color(color_flag: str) -> bool:
    """Convert --color enum value to bool. 'auto' → TTY/env detection."""
    if color_flag == "on":
        return True
    if color_flag == "off":
        return False
    # 'auto'
    if os.environ.get("TERMRENDER_COLOR") == "1":
        return True
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _read_stdin_source(leaf_path: str) -> str:
    """Read source markdown from stdin. Error if stdin is a TTY (no piped content)."""
    if sys.stdin.isatty():
        _json_error(
            "bad_invocation",
            f"termrender {leaf_path} requires markdown source on stdin but stdin is a terminal",
            received="(tty)",
            next_=f"pipe markdown source: cat file.md | termrender {leaf_path}",
        )
    return sys.stdin.read()


# ---------------------------------------------------------------------------
# Argparse subclass — emits bad_invocation JSON instead of printing to stderr
# ---------------------------------------------------------------------------

class _StrictParser(argparse.ArgumentParser):
    """ArgumentParser that emits structured bad_invocation JSON on error."""

    def error(self, message: str) -> NoReturn:  # type: ignore[override]
        argv_tail = sys.argv[1:]
        _json_error(
            "bad_invocation",
            f"argument error: {message}",
            received=" ".join(argv_tail),
            next_="run with -h for the input schema",
        )

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:  # type: ignore[override]
        if status != 0 and message:
            _json_error(
                "bad_invocation",
                message.strip(),
                received=" ".join(sys.argv[1:]),
                next_="run with -h for the input schema",
            )
        sys.exit(status)


def _make_leaf_parser(prog: str) -> _StrictParser:
    return _StrictParser(prog=prog, add_help=False)


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def _cmd_doc_render(args: argparse.Namespace) -> None:
    source = _read_stdin_source("doc render")
    width: int | None = args.width
    color = _resolve_color(args.color)
    cjk: bool = args.cjk

    if cjk:
        os.environ["TERMRENDER_CJK"] = "1"

    try:
        if args.line_map:
            output = json.dumps(render_with_map(source, width=width, color=color)) + "\n"
        else:
            output = render(source, width=width, color=color)
    except TerminalError as e:
        _json_error(
            "terminal_error",
            f"terminal does not support required capabilities: {e}",
            next_="use a terminal that supports Unicode, or pass --color off",
            code=EXIT_TERMINAL,
        )
    except DirectiveError as e:
        _json_error(
            "syntax_error",
            f"directive syntax error: {e}",
            next_="fix the malformed/unclosed directive in source, or call termrender doc check first",
            code=EXIT_SYNTAX,
        )
    except ValueError as e:
        _json_error(
            "nesting_error",
            f"directive nesting error: {e}",
            next_="ensure outer fences use strictly more colons than inner fences",
            code=EXIT_SYNTAX,
        )
    except Exception as e:
        _json_error(
            "internal",
            f"unexpected render error: {e}",
            next_="report this as a bug with the source that triggered it",
            code=EXIT_INPUT,
        )

    sys.stdout.write(output)
    sys.stdout.flush()


def _cmd_doc_check(args: argparse.Namespace) -> None:
    source = _read_stdin_source("doc check")
    cjk: bool = args.cjk

    if cjk:
        os.environ["TERMRENDER_CJK"] = "1"

    from termrender.parser import parse

    errors: list[dict[str, str]] = []
    ok = True
    try:
        parse(source)
    except DirectiveError as e:
        ok = False
        errors.append({"kind": "syntax", "message": str(e)})
    except ValueError as e:
        ok = False
        errors.append({"kind": "nesting", "message": str(e)})

    sys.stdout.write(json.dumps({"ok": ok, "errors": errors}) + "\n")
    sys.stdout.flush()
    sys.exit(EXIT_OK if ok else EXIT_SYNTAX)


def _cmd_doc_watch(args: argparse.Namespace) -> None:
    path: str = args.path
    color = _resolve_color(args.color)
    cjk: bool = args.cjk

    if cjk:
        os.environ["TERMRENDER_CJK"] = "1"

    _watch_loop(path, color=color)
    sys.exit(EXIT_OK)


def _termrender_invocation() -> str:
    """Shell-quoted command prefix that invokes *this* termrender.

    A tmux pane spawned via split-window/respawn-pane resolves a bare
    ``termrender`` token through ``$PATH``. When termrender lives only inside a
    managed venv (e.g. invoked by absolute path), that bare name is not on PATH
    and the spawned pane dies instantly and silently. Prefer the absolute path
    of the running entrypoint (argv[0]) so the pane invokes the same binary;
    fall back to ``python -m termrender`` when argv[0] is not a usable
    executable.
    """
    import shlex

    argv0 = sys.argv[0] if sys.argv else ""
    if argv0:
        entry = Path(argv0).resolve()
        if entry.is_file() and os.access(entry, os.X_OK):
            return shlex.quote(str(entry))
    return f"{shlex.quote(sys.executable)} -m termrender"


def _build_pane_cmd(
    *,
    watch: bool,
    path: str,
    cjk: bool,
    pane_width: int | None,
    tmpfile: str | None,
) -> str:
    """Build the tmux pane command string using the new flag-form CLI."""
    import shlex

    cjk_flag = " --cjk" if cjk else ""
    termrender = _termrender_invocation()

    if watch:
        # doc watch reads path as positional; use -- to guard against flag-looking paths
        cmd = f"{termrender} doc watch --color on{cjk_flag} -- {shlex.quote(path)}"
    else:
        effective_path = tmpfile if tmpfile else path
        width_flag = f" --width {pane_width}" if pane_width is not None else ""
        # doc render reads stdin — cat the file into it
        cmd = (
            f"cat {shlex.quote(effective_path)}"
            f" | {termrender} doc render --color on{width_flag}{cjk_flag}"
            f" | less -R; rm -f {shlex.quote(effective_path)}"
        )
    return cmd


def _cmd_pane_open(args: argparse.Namespace) -> None:
    import subprocess
    import tempfile

    path: str = args.path
    width: int | None = args.width
    color = _resolve_color(args.color)
    cjk: bool = args.cjk
    watch: bool = args.watch
    window: str = args.window

    if not os.environ.get("TMUX"):
        _json_error(
            "not_in_tmux",
            "not inside a tmux session",
            next_="run inside a tmux session before calling termrender pane open",
            code=EXIT_INPUT,
        )

    try:
        with open(path) as f:
            source = f.read()
    except OSError as e:
        _json_error(
            "bad_input",
            f"cannot read file: {e}",
            field="path",
            next_=f"ensure the file exists and is readable: {path}",
        )

    # Syntax pre-check
    try:
        from termrender.parser import parse as _parse
        _parse(source)
    except DirectiveError as e:
        _json_error(
            "syntax_error",
            f"directive syntax error: {e}",
            next_="fix the syntax error in the file before opening a pane",
            code=EXIT_SYNTAX,
        )
    except ValueError as e:
        _json_error(
            "nesting_error",
            f"directive nesting error: {e}",
            next_="fix the nesting error in the file before opening a pane",
            code=EXIT_SYNTAX,
        )

    # Determine pane width
    if window == "new":
        pane_width = None
    elif width is not None:
        pane_width = max(width, 40)
    else:
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{window_width}"],
                capture_output=True, text=True, check=True,
            )
            window_width = int(result.stdout.strip())
            if window_width >= 140:
                pane_width = 80
            elif window_width >= 100:
                pane_width = window_width // 2
            else:
                pane_width = max(window_width - 2 - 50, 40)
        except Exception:
            pane_width = 80
        pane_width = max(pane_width, 40)

    if watch:
        tmpfile = None
    else:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", prefix="termrender-", delete=False,
        ) as f:
            f.write(source)
            tmpfile = f.name

    pane_cmd = _build_pane_cmd(
        watch=watch,
        path=path,
        cjk=cjk,
        pane_width=pane_width,
        tmpfile=tmpfile,
    )

    try:
        if window == "new":
            result = subprocess.run(
                ["tmux", "new-window", "-P", "-F", "#{pane_id}", pane_cmd],
                check=True, capture_output=True, text=True,
            )
            pane_id = result.stdout.strip()
        else:
            split_args = ["tmux", "split-window", "-h", "-f"]
            if pane_width is not None:
                split_args += ["-l", str(pane_width)]
            split_args += ["-P", "-F", "#{pane_id}", pane_cmd]
            result = subprocess.run(split_args, check=True, capture_output=True, text=True)
            pane_id = result.stdout.strip()
    except FileNotFoundError:
        if tmpfile:
            try:
                os.unlink(tmpfile)
            except OSError:
                pass
        _json_error(
            "tmux_missing",
            "tmux executable not found",
            next_="install tmux and ensure it is on PATH",
            code=EXIT_INPUT,
        )
    except subprocess.CalledProcessError as e:
        if tmpfile:
            try:
                os.unlink(tmpfile)
            except OSError:
                pass
        _json_error(
            "internal",
            f"tmux command failed: {e}",
            next_="check that tmux is running and has space for a new pane",
            code=EXIT_INPUT,
        )

    sys.stdout.write(json.dumps({"pane_id": pane_id}) + "\n")
    sys.stdout.flush()


def _cmd_pane_update(args: argparse.Namespace) -> None:
    import subprocess
    import tempfile

    pane_id: str = args.pane_id
    path: str = args.path
    width: int | None = args.width
    color = _resolve_color(args.color)
    cjk: bool = args.cjk
    watch: bool = args.watch

    try:
        with open(path) as f:
            source = f.read()
    except OSError as e:
        _json_error(
            "bad_input",
            f"cannot read file: {e}",
            field="path",
            next_=f"ensure the file exists and is readable: {path}",
        )

    # Syntax pre-check
    try:
        from termrender.parser import parse as _parse
        _parse(source)
    except DirectiveError as e:
        _json_error(
            "syntax_error",
            f"directive syntax error: {e}",
            next_="fix the syntax error in the file before updating the pane",
            code=EXIT_SYNTAX,
        )
    except ValueError as e:
        _json_error(
            "nesting_error",
            f"directive nesting error: {e}",
            next_="fix the nesting error in the file before updating the pane",
            code=EXIT_SYNTAX,
        )

    # Determine pane width
    if width is not None:
        pane_width = max(width, 20)
    else:
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "-t", pane_id, "#{pane_width}"],
                capture_output=True, text=True, check=True,
            )
            pane_width = int(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
            _json_error(
                "pane_gone",
                f"could not query tmux pane {pane_id!r}",
                received=pane_id,
                field="pane_id",
                next_="the pane may have been closed; spawn a fresh one with termrender pane open",
                code=EXIT_INPUT,
            )
        pane_width = max(pane_width, 20)

    if watch:
        tmpfile = None
    else:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", prefix="termrender-", delete=False,
        ) as f:
            f.write(source)
            tmpfile = f.name

    pane_cmd = _build_pane_cmd(
        watch=watch,
        path=path,
        cjk=cjk,
        pane_width=pane_width,
        tmpfile=tmpfile,
    )

    try:
        subprocess.run(
            ["tmux", "respawn-pane", "-k", "-t", pane_id, pane_cmd],
            check=True,
        )
    except FileNotFoundError:
        if tmpfile:
            try:
                os.unlink(tmpfile)
            except OSError:
                pass
        _json_error(
            "tmux_missing",
            "tmux executable not found",
            next_="install tmux and ensure it is on PATH",
            code=EXIT_INPUT,
        )
    except subprocess.CalledProcessError:
        if tmpfile:
            try:
                os.unlink(tmpfile)
            except OSError:
                pass
        _json_error(
            "pane_gone",
            f"failed to respawn tmux pane {pane_id!r} — it may have been closed",
            received=pane_id,
            field="pane_id",
            next_="spawn a fresh pane with termrender pane open",
            code=EXIT_INPUT,
        )

    sys.stdout.write(json.dumps({"pane_id": pane_id}) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Watch loop (unchanged)
# ---------------------------------------------------------------------------

def _watch_loop(file_path: str, *, color: bool, poll_interval: float = 0.2) -> None:
    import time
    import shutil as _shutil
    import select

    interactive = sys.stdin.isatty()
    old_term = None
    if interactive:
        try:
            import termios
            import tty
            old_term = termios.tcgetattr(sys.stdin.fileno())
        except Exception:
            interactive = False

    rendered: list[str] = []
    scroll = 0
    first_render = True
    last_mtime: float | None = None
    last_size: tuple[int, int] = (0, 0)

    def _render_source() -> list[str]:
        try:
            with open(file_path) as f:
                source = f.read()
        except FileNotFoundError:
            return [f"termrender: file not found: {file_path}"]
        except OSError as e:
            return [f"termrender: cannot read {file_path}: {e}"]
        try:
            body = render(source, width=None, color=color)
        except DirectiveError as e:
            body = f"termrender: syntax error: {e}"
        except TerminalError as e:
            body = f"termrender: terminal error: {e}"
        except ValueError as e:
            body = f"termrender: nesting error: {e}"
        except Exception as e:
            body = f"termrender: render error: {e}"
        return body.split("\n")

    def _status(view_h: int) -> str:
        total = len(rendered)
        if total <= view_h:
            pos = "all"
        else:
            pos = f"{scroll + 1}-{min(scroll + view_h, total)}/{total}"
        keys = (
            "↑↓/wheel scroll · g/G top/bottom · q quit"
            if interactive
            else "Ctrl+C to exit"
        )
        return f"watching {os.path.basename(file_path)} — {keys}  [{pos}]"

    def _draw() -> None:
        nonlocal scroll
        size = _shutil.get_terminal_size()
        view_h = max(1, size.lines - 1)
        max_scroll = max(0, len(rendered) - view_h)
        scroll = min(max(scroll, 0), max_scroll)
        window = rendered[scroll:scroll + view_h]
        window += [""] * (view_h - len(window))
        status = _status(view_h)
        if color:
            status = f"\033[2m{status}\033[0m"
        sys.stdout.write(
            "\033[?25l\033[2J\033[H"
            + "\n".join(window)
            + f"\033[{size.lines};1H"
            + status
        )
        sys.stdout.flush()

    def _consume(buf: str, view_h: int) -> tuple[str, bool, bool]:
        nonlocal scroll
        page = max(1, view_h - 1)
        i, n, moved = 0, len(buf), False
        while i < n:
            c = buf[i]
            if c == "q" or c == "\x03":
                return "", True, moved
            if c == "\x1b":
                if i + 1 >= n:
                    break
                if buf[i + 1] != "[":
                    i += 1
                    continue
                j = i + 2
                if j < n and buf[j] == "<":
                    k = j + 1
                    while k < n and buf[k] not in ("M", "m"):
                        k += 1
                    if k >= n:
                        break
                    try:
                        btn = int(buf[j + 1:k].split(";")[0])
                    except ValueError:
                        btn = -1
                    if buf[k] == "M":
                        if btn == 64:
                            scroll -= 3; moved = True
                        elif btn == 65:
                            scroll += 3; moved = True
                    i = k + 1
                    continue
                k = j
                while k < n and not ("\x40" <= buf[k] <= "\x7e"):
                    k += 1
                if k >= n:
                    break
                seq = buf[i:k + 1]
                if seq == "\x1b[A":
                    scroll -= 1; moved = True
                elif seq == "\x1b[B":
                    scroll += 1; moved = True
                elif seq == "\x1b[5~":
                    scroll -= page; moved = True
                elif seq == "\x1b[6~":
                    scroll += page; moved = True
                elif seq == "\x1b[H":
                    scroll = 0; moved = True
                elif seq == "\x1b[F":
                    scroll = 1 << 30; moved = True
                i = k + 1
                continue
            if c == "k":
                scroll -= 1; moved = True
            elif c == "j":
                scroll += 1; moved = True
            elif c == "g":
                scroll = 0; moved = True
            elif c == "G":
                scroll = 1 << 30; moved = True
            elif c in (" ", "f", "d"):
                scroll += page; moved = True
            elif c in ("b", "u"):
                scroll -= page; moved = True
            i += 1
        return buf[i:], False, moved

    sys.stdout.write("\033[?1049h")
    if interactive:
        sys.stdout.write("\033[?1000h\033[?1006h")
        tty.setcbreak(sys.stdin.fileno())
    sys.stdout.flush()

    buf = ""
    try:
        while True:
            try:
                mtime = os.path.getmtime(file_path)
            except FileNotFoundError:
                mtime = None
            size = _shutil.get_terminal_size()
            size_tuple = (size.columns, size.lines)
            view_h = max(1, size.lines - 1)

            dirty = False
            if mtime != last_mtime or size_tuple != last_size:
                pinned = (not first_render) and scroll >= max(0, len(rendered) - view_h)
                rendered[:] = _render_source()
                last_mtime, last_size = mtime, size_tuple
                if first_render:
                    scroll = 0
                    first_render = False
                elif pinned:
                    scroll = max(0, len(rendered) - view_h)
                dirty = True

            if dirty:
                _draw()

            if not interactive:
                time.sleep(poll_interval)
                continue

            if select.select([sys.stdin], [], [], poll_interval)[0]:
                chunk = os.read(sys.stdin.fileno(), 4096).decode("utf-8", "replace")
                if chunk:
                    buf, quit_, moved = _consume(buf + chunk, view_h)
                    if quit_:
                        break
                    if moved:
                        _draw()
    except KeyboardInterrupt:
        pass
    finally:
        if interactive:
            sys.stdout.write("\033[?1000l\033[?1006l")
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_term)
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Leaf parser factories
# ---------------------------------------------------------------------------

def _parser_doc_render() -> _StrictParser:
    p = _make_leaf_parser("termrender doc render")
    p.add_argument("--width", type=int, default=None, metavar="N")
    p.add_argument("--color", choices=["auto", "on", "off"], default="auto")
    p.add_argument("--cjk", action="store_true", default=False)
    p.add_argument("--line-map", dest="line_map", action="store_true", default=False)
    return p


def _parser_doc_check() -> _StrictParser:
    p = _make_leaf_parser("termrender doc check")
    p.add_argument("--cjk", action="store_true", default=False)
    return p


def _parser_doc_watch() -> _StrictParser:
    p = _make_leaf_parser("termrender doc watch")
    p.add_argument("path", metavar="PATH")
    p.add_argument("--color", choices=["auto", "on", "off"], default="auto")
    p.add_argument("--cjk", action="store_true", default=False)
    return p


def _parser_pane_open() -> _StrictParser:
    p = _make_leaf_parser("termrender pane open")
    p.add_argument("path", metavar="PATH")
    p.add_argument("--width", type=int, default=None, metavar="N")
    p.add_argument("--color", choices=["auto", "on", "off"], default="auto")
    p.add_argument("--cjk", action="store_true", default=False)
    p.add_argument("--watch", action="store_true", default=False)
    p.add_argument("--window", choices=["split", "new"], default="split")
    return p


def _parser_pane_update() -> _StrictParser:
    p = _make_leaf_parser("termrender pane update")
    p.add_argument("path", metavar="PATH")
    p.add_argument("--pane-id", dest="pane_id", required=True, metavar="ID")
    p.add_argument("--width", type=int, default=None, metavar="N")
    p.add_argument("--color", choices=["auto", "on", "off"], default="auto")
    p.add_argument("--cjk", action="store_true", default=False)
    p.add_argument("--watch", action="store_true", default=False)
    return p


def _print_help(text: str) -> NoReturn:
    sys.stdout.write(text)
    sys.stdout.flush()
    sys.exit(EXIT_OK)


def _bad_invocation(message: str) -> NoReturn:
    _json_error(
        "bad_invocation",
        message,
        received=" ".join(sys.argv[1:]),
        next_="run with -h for the input schema",
    )


# ---------------------------------------------------------------------------
# Main entry point — manual dispatch
# ---------------------------------------------------------------------------

def main() -> None:
    argv = sys.argv[1:]

    if not argv:
        sys.stdout.write(_ROOT_HELP)
        sys.stdout.flush()
        sys.exit(EXIT_INPUT)

    if argv[0] in ("-h", "--help"):
        _print_help(_ROOT_HELP)

    branch = argv[0]
    rest = argv[1:]

    if branch == "doc":
        if not rest or rest[0] in ("-h", "--help"):
            _print_help(_DOC_HELP)
        leaf = rest[0]
        leaf_argv = rest[1:]

        if leaf == "render":
            if "-h" in leaf_argv or "--help" in leaf_argv:
                _print_help(_DOC_RENDER_HELP)
            p = _parser_doc_render()
            args = p.parse_args(leaf_argv)
            _cmd_doc_render(args)

        elif leaf == "check":
            if "-h" in leaf_argv or "--help" in leaf_argv:
                _print_help(_DOC_CHECK_HELP)
            p = _parser_doc_check()
            args = p.parse_args(leaf_argv)
            _cmd_doc_check(args)

        elif leaf == "watch":
            if "-h" in leaf_argv or "--help" in leaf_argv:
                _print_help(_DOC_WATCH_HELP)
            p = _parser_doc_watch()
            args = p.parse_args(leaf_argv)
            _cmd_doc_watch(args)

        else:
            _bad_invocation(f"unknown doc subcommand: {leaf!r}")

    elif branch == "pane":
        if not rest or rest[0] in ("-h", "--help"):
            _print_help(_PANE_HELP)
        leaf = rest[0]
        leaf_argv = rest[1:]

        if leaf == "open":
            if "-h" in leaf_argv or "--help" in leaf_argv:
                _print_help(_PANE_OPEN_HELP)
            p = _parser_pane_open()
            args = p.parse_args(leaf_argv)
            _cmd_pane_open(args)

        elif leaf == "update":
            if "-h" in leaf_argv or "--help" in leaf_argv:
                _print_help(_PANE_UPDATE_HELP)
            p = _parser_pane_update()
            args = p.parse_args(leaf_argv)
            _cmd_pane_update(args)

        else:
            _bad_invocation(f"unknown pane subcommand: {leaf!r}")

    else:
        _bad_invocation(f"unknown branch: {branch!r}")


if __name__ == "__main__":
    main()
