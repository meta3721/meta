#!/usr/bin/env python3
"""P10-R1 smoke entry point.

This stable name is intentionally a thin wrapper around the revised smoke
implementation so the exact command required by the audit instruction stays
available while P10's original command remains backward compatible.
"""

from p10_smoke import main


if __name__ == "__main__":
    raise SystemExit(main())
