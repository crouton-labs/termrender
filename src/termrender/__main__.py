"""CLI entry point for termrender."""

import argparse
import sys

from termrender import render, TerminalError

__version__ = "0.1.0"

_EPILOG = """\
directives:
  :::panel{title="T" color="c"}   Bordered box with title and color
  :::columns                       Side-by-side column layout
    :::col{width="50%"}            Column within :::columns (width in %)
  :::tree{color="c"}               Tree with guide lines (indent = nesting)
  :::callout{type="info"}          Callout box (info, warning, error, success)
  :::quote{author="A"}             Styled block quote with attribution
  :::code{lang="python"}           Code block with syntax highlighting
  :::divider{label="L"}            Horizontal rule with optional label
  ```mermaid                       Mermaid flowchart (rendered via mermaid-ascii)

  Directives nest arbitrarily. Close with :::

markup:
  Standard markdown: # headings, **bold**, *italic*, `code`,
  - bullet lists, 1. numbered lists, ```lang fenced code blocks

environment:
  NO_COLOR        Set to any value to disable color output
  TERM=dumb       Raises an error (Unicode rendering not supported)

examples:
  termrender doc.md                Render a file to the terminal
  termrender doc.md --width 100    Render at 100 columns wide
  termrender doc.md --no-color     Render without ANSI colors
  cat doc.md | termrender          Render from stdin
  echo '# Hello' | termrender     Quick inline render

  termrender <<'EOF'               Render a panel with a list
  :::panel{title="Status" color="green"}
  - All systems operational
  - Last deploy: 2 hours ago
  :::
  EOF
"""


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
        help="markdown file to render (default: read from stdin)",
    )
    parser.add_argument(
        "-w", "--width",
        type=int,
        default=None,
        metavar="COLS",
        help="output width in columns (default: auto-detect terminal width)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="strip ANSI color codes from output (same as NO_COLOR=1)",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args()

    # Determine input source
    infile = args.file if args.file is not None else sys.stdin
    if infile is sys.stdin and sys.stdin.isatty():
        parser.print_help(sys.stderr)
        print("\ntermrender: no input (provide a file or pipe markdown to stdin)", file=sys.stderr)
        sys.exit(1)

    source = infile.read()

    try:
        output = render(source, width=args.width, color=not args.no_color)
    except TerminalError as e:
        print(f"termrender: error: {e}", file=sys.stderr)
        print("  Hint: use a terminal that supports Unicode, or set TERM appropriately.", file=sys.stderr)
        sys.exit(1)

    sys.stdout.write(output)


if __name__ == "__main__":
    main()
