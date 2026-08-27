"""Command-line interface for A Stock Selector."""

import argparse
from collections.abc import Sequence

from stock_selector import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="A Stock Selector")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("version", help="Show the A Stock Selector version.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "version":
        print(f"A Stock Selector {__version__}")
    else:
        parser.print_help()
    return 0
