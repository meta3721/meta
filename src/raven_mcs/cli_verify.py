"""Console script entry: `raven-verify`."""

from __future__ import annotations

from importlib.machinery import SourceFileLoader
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    mod = SourceFileLoader(
        "raven_mcs_verify_run",
        str(root / "scripts" / "verify_run.py"),
    ).load_module()
    raise SystemExit(mod.main())
