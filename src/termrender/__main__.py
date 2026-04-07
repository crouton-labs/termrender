"""CLI entry point for termrender."""

import argparse
import os
import sys

from termrender import render, TerminalError, DirectiveError

# Exit codes — agents can branch on these without parsing stderr.
EXIT_OK = 0
EXIT_INPUT = 1       # no input, bad file, usage error
EXIT_SYNTAX = 2      # directive syntax error (malformed/unclosed/stray)
EXIT_TERMINAL = 3    # terminal does not support required capabilities

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("termrender")
except Exception:
    __version__ = "dev"

_EPILOG = """\
directives (close each with :::):
  :::panel{title="T" color="c"}     Bordered box
      attrs: title (string), color (red|green|yellow|blue|magenta|cyan|white|gray)
  :::columns                         Side-by-side column layout container
    :::col{width="50%"}              Column within :::columns
        attrs: width (percent string, e.g. "40%")
  :::tree{color="c"}                 Tree with Unicode guide lines
      attrs: color (same palette as panel). Body: indented lines = nesting.
  :::callout{type="info"}            Callout box with status icon
      attrs: type (info|warning|error|success)
  :::quote{author="A"}               Styled block quote
      attrs: author or by (string)
  :::code{lang="python"}             Code block with syntax highlighting
      attrs: lang (any Pygments lexer name)
  :::divider{label="L"}              Horizontal rule (self-closing, no :::)
      attrs: label (centered text)
  ```mermaid ... ```                  Mermaid diagram (via mermaid-ascii)

nesting:
  Directives nest arbitrarily. Every opener needs a matching :::
  except :::divider which is self-closing.

  :::panel{title="Outer"}
  :::callout{type="info"}
  Nested content here.
  :::
  :::

markup:
  # heading    **bold**    *italic*    `code`
  - bullet     1. numbered    ```lang fenced code
  | col | col | (GFM tables)

colors:
  red, green, yellow, blue, magenta, cyan, white, gray

environment:
  NO_COLOR           Disable all ANSI color codes
  TERM=dumb          Unsupported — exits with code 3
  TERMRENDER_CJK=1   Treat ambiguous-width Unicode as double-width

exit codes:
  0  success
  1  input error (no input, bad file)
  2  syntax error (malformed directive)
  3  terminal capability error

examples:
  termrender doc.md                Render a file
  termrender doc.md -w 100         Render at 100 columns
  termrender --check doc.md        Validate syntax without rendering
  cat doc.md | termrender          Render from stdin
  echo '# Hello' | termrender     Quick inline render

  termrender --tmux doc.md            Render in a new tmux side pane
  termrender --watch doc.md           Live-render in current terminal
  termrender --tmux --watch doc.md    Live-render in a new tmux side pane
  termrender <<'EOF'
  :::panel{title="Status" color="green"}
  - All systems operational
  - Last deploy: 2 hours ago
  :::
  EOF
"""


def _error(msg: str, *, fix: str | None = None, hint: str | None = None,
           code: int = EXIT_INPUT) -> None:
    """Print a structured error to stderr and exit."""
    print(f"termrender: {msg}", file=sys.stderr)
    if fix:
        print(f"  Fix: {fix}", file=sys.stderr)
    if hint:
        print(f"  Hint: {hint}", file=sys.stderr)
    sys.exit(code)


def _watch_loop(file_path: str, *, color: bool, poll_interval: float = 0.2) -> None:
    """Re-render `file_path` whenever its mtime changes.

    Uses the alternate screen buffer so the prior terminal state is restored
    on exit. Width is re-detected from the current terminal each render so
    pane/window resizes are picked up automatically. Render errors are shown
    inline rather than crashing the watcher — fix the file and save again.
    """
    import time

    last_mtime: float | None = None
    last_size: tuple[int, int] = (0, 0)

    def _draw(body: str, status: str) -> None:
        # \033[?25l hide cursor, \033[2J clear, \033[H home
        sys.stdout.write("\033[?25l\033[2J\033[H")
        sys.stdout.write(body)
        if not body.endswith("\n"):
            sys.stdout.write("\n")
        # Status line at the bottom — dim if color is enabled
        if color:
            sys.stdout.write(f"\033[2m{status}\033[0m\n")
        else:
            sys.stdout.write(f"{status}\n")
        sys.stdout.flush()

    def _render_now() -> None:
        try:
            with open(file_path, "r") as f:
                source = f.read()
        except FileNotFoundError:
            body = f"termrender: file not found: {file_path}\n"
        except OSError as e:
            body = f"termrender: cannot read {file_path}: {e}\n"
        else:
            try:
                body = render(source, width=None, color=color)
            except DirectiveError as e:
                body = f"termrender: syntax error: {e}\n"
            except TerminalError as e:
                body = f"termrender: terminal error: {e}\n"
            except ValueError as e:
                body = f"termrender: nesting error: {e}\n"
            except Exception as e:  # noqa: BLE001 — keep watcher alive
                body = f"termrender: render error: {e}\n"
        _draw(body, f"watching {file_path} — Ctrl+C to exit")

    # Enter alternate screen buffer
    sys.stdout.write("\033[?1049h")
    sys.stdout.flush()
    try:
        while True:
            try:
                mtime = os.path.getmtime(file_path)
            except FileNotFoundError:
                mtime = None
            # Re-render on file change OR terminal resize
            import shutil as _shutil
            size = _shutil.get_terminal_size()
            size_tuple = (size.columns, size.lines)
            if mtime != last_mtime or size_tuple != last_size:
                last_mtime = mtime
                last_size = size_tuple
                _render_now()
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass
    finally:
        # Show cursor, leave alternate screen buffer
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="termrender",
        description="Render directive-flavored markdown as rich ANSI terminal output.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=argparse.FileType("r"),
        default=None,
        metavar="FILE",
        help="markdown file to render (default: stdin)",
    )
    parser.add_argument(
        "-w", "--width",
        type=int,
        default=None,
        metavar="COLS",
        help="output width in columns (default: auto-detect)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="strip ANSI codes (same as NO_COLOR=1)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate directive syntax without rendering (exit 0 if valid, 2 if errors)",
    )
    parser.add_argument(
        "--cjk",
        action="store_true",
        help="treat ambiguous-width Unicode as double-width (CJK terminals)",
    )
    parser.add_argument(
        "--tmux",
        action="store_true",
        help="open rendered output in a new tmux side pane (requires tmux)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="re-render whenever FILE changes on disk (requires a file argument)",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args()

    # --watch needs a real file path to poll; stdin can't be watched.
    if args.watch and args.file is None:
        _error(
            "--watch requires a FILE argument",
            fix="pass a markdown file path; stdin cannot be watched",
            hint="termrender --watch doc.md",
        )

    # Determine input source
    infile = args.file if args.file is not None else sys.stdin
    if infile is sys.stdin and sys.stdin.isatty():
        parser.print_help(sys.stderr)
        _error(
            "no input provided",
            fix="provide a FILE argument or pipe markdown to stdin",
            hint="termrender doc.md  OR  echo '# Hi' | termrender",
        )

    source = infile.read()

    if args.cjk:
        os.environ["TERMRENDER_CJK"] = "1"

    # --tmux: render in a new tmux side pane, sized to fit
    if args.tmux:
        # Validate syntax before creating pane — fail fast to caller's terminal
        try:
            from termrender.parser import parse as _parse
            _parse(source)
        except DirectiveError as e:
            _error(
                f"syntax error: {e}",
                fix="check directive openers have matching ::: closers and attribute syntax is key=\"value\"",
                code=EXIT_SYNTAX,
            )
        except ValueError as e:
            _error(
                f"nesting error: {e}",
                fix="reduce directive nesting depth (max 50 levels)",
                code=EXIT_SYNTAX,
            )

        import shlex
        import subprocess
        import tempfile

        if not os.environ.get("TMUX"):
            _error("not inside a tmux session",
                   fix="run inside tmux or omit --tmux")

        # Determine desired pane width
        if args.width:
            pane_width = args.width
        else:
            # Preview render to measure content width
            from termrender.style import visual_len
            try:
                preview = render(source, width=80, color=False)
                max_w = max(
                    (visual_len(line) for line in preview.split('\n') if line),
                    default=40,
                )
                pane_width = max(max_w, 40)
            except Exception:
                pane_width = 80

        # Cap to available tmux space (leave room for the source pane)
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{pane_width}"],
                capture_output=True, text=True, check=True,
            )
            available = int(result.stdout.strip())
            pane_width = min(pane_width, available - 10)
        except Exception:
            pass
        pane_width = max(pane_width, 20)  # absolute minimum

        # Watch mode points the new pane at the user's real file so edits
        # propagate; non-watch mode snapshots source into a tempfile.
        tmpfile: str | None = None
        if args.watch:
            # args.file is guaranteed non-None by the earlier --watch check.
            source_path = args.file.name
        else:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", prefix="termrender-", delete=False,
            ) as f:
                f.write(source)
                tmpfile = f.name
            source_path = tmpfile

        # Rebuild command without --tmux to avoid recursion
        cmd_parts = ["termrender", shlex.quote(source_path)]
        if args.no_color:
            cmd_parts.append("--no-color")
        if args.cjk:
            cmd_parts.append("--cjk")
        if args.watch:
            # No -w: watcher re-detects pane width per render so resizes
            # pick up automatically.
            cmd_parts.append("--watch")
        else:
            cmd_parts.extend(["-w", str(pane_width)])

        if args.watch:
            # Watch mode owns the pane (alternate screen buffer); no less,
            # no tempfile cleanup needed.
            pane_cmd = "TERMRENDER_COLOR=1 " + " ".join(cmd_parts)
        else:
            # TERMRENDER_COLOR=1 forces color on despite stdout piping to less
            pane_cmd = (
                "TERMRENDER_COLOR=1 " + " ".join(cmd_parts)
                + " | less -R; rm -f " + shlex.quote(source_path)
            )

        try:
            subprocess.run(
                ["tmux", "split-window", "-h", "-f", "-l", str(pane_width), pane_cmd],
                check=True,
            )
        except FileNotFoundError:
            if tmpfile:
                os.unlink(tmpfile)
            _error("tmux not found", fix="install tmux or omit --tmux")
        except subprocess.CalledProcessError:
            if tmpfile:
                os.unlink(tmpfile)
            _error("failed to create tmux pane",
                   hint="check that tmux is running and has space for a new pane")

        sys.exit(EXIT_OK)

    # --watch: live-render in the current terminal
    if args.watch:
        use_color = not args.no_color and (
            sys.stdout.isatty() or os.environ.get("TERMRENDER_COLOR") == "1"
        )
        _watch_loop(args.file.name, color=use_color)
        sys.exit(EXIT_OK)

    # --check: validate only, no rendering
    if args.check:
        try:
            from termrender.parser import parse
            parse(source)
        except DirectiveError as e:
            _error(
                f"syntax error: {e}",
                fix="check directive openers have matching ::: closers and attribute syntax is key=\"value\"",
                code=EXIT_SYNTAX,
            )
        except ValueError as e:
            _error(
                f"nesting error: {e}",
                fix="reduce directive nesting depth (max 50 levels)",
                code=EXIT_SYNTAX,
            )
        print("ok", file=sys.stderr)
        sys.exit(EXIT_OK)

    try:
        use_color = not args.no_color and (
            sys.stdout.isatty() or os.environ.get("TERMRENDER_COLOR") == "1"
        )
        output = render(source, width=args.width, color=use_color)
    except TerminalError as e:
        _error(
            f"terminal error: {e}",
            fix="use a terminal that supports Unicode, or unset TERM=dumb",
            hint="export TERM=xterm-256color",
            code=EXIT_TERMINAL,
        )
    except DirectiveError as e:
        _error(
            f"syntax error: {e}",
            fix="check directive openers have matching ::: closers and attribute syntax is key=\"value\"",
            hint="run: termrender --check <file> to validate before rendering",
            code=EXIT_SYNTAX,
        )
    except ValueError as e:
        _error(
            f"nesting error: {e}",
            fix="reduce directive nesting depth (max 50 levels)",
            code=EXIT_SYNTAX,
        )

    sys.stdout.write(output)


if __name__ == "__main__":
    main()
