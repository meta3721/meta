"""Shared CLI flag helpers for long-running experiment scripts."""

from __future__ import annotations

import argparse
from pathlib import Path


def add_common_run_flags(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Attach constitution-required long-task flags."""
    parser.add_argument(
        "--dry-run", action="store_true", help="Plan only; do not write results."
    )
    parser.add_argument(
        "--resume", action="store_true", help="Resume if checkpoint+config hash match."
    )
    parser.add_argument(
        "--max-workers", type=int, default=1, help="Parallel worker processes."
    )
    parser.add_argument(
        "--fail-fast", action="store_true", help="Stop on first failure."
    )
    parser.add_argument("--device", type=str, default="cpu", help="cpu | cuda | cuda:N")
    parser.add_argument("--seed", type=int, default=None, help="Master seed override.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/runs"),
        help="Root directory for run outputs.",
    )
    return parser


def build_common_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    return add_common_run_flags(parser)
