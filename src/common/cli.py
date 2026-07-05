"""Shared CLI surface: every stage script accepts --config-dir, --limit, --dry-run."""

import argparse


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config-dir", default=None, help="configs/ directory (default: repo configs/)")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of items processed")
    parser.add_argument("--dry-run", action="store_true", help="report what would happen; write nothing")
    return parser
