#!/usr/bin/env python3
"""Pre-E1 Seal smoke entry point."""
from __future__ import annotations

import sys

from p10_smoke import main


if __name__ == "__main__":
    raise SystemExit(main(["--run-prefix", "PRE_E1_SMOKE", *sys.argv[1:]]))
