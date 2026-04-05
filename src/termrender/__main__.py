"""CLI entry point for termrender."""

import argparse
import sys

from termrender import render, TerminalError


def main():
    parser = argparse.ArgumentParser(
        prog="termrender",
        description="Render Markdown to ANSI terminal output",
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="Markdown file to render (reads stdin if omitted)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="Terminal width in columns (auto-detected if omitted)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color output",
    )
    args = parser.parse_args()

    source = args.file.read()

    try:
        output = render(source, width=args.width, color=not args.no_color)
    except TerminalError as e:
        print(f"termrender: {e}", file=sys.stderr)
        sys.exit(1)

    sys.stdout.write(output)


if __name__ == "__main__":
    main()
