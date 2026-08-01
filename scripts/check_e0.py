#!/usr/bin/env python3
"""Run the E0.1–E0.6 unit suite and emit a machine-readable summary."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.utils.serialization import dump_json

E0_TESTS = [
    "tests/unit/test_e0_weights.py",
    "tests/unit/test_e0_p2_debt.py",
    "tests/unit/test_e0_timing_leakage.py",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/audits"))
    args = parser.parse_args(argv)

    command = [sys.executable, "-m", "pytest", *E0_TESTS]
    completed = subprocess.run(
        command,
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    passed = completed.returncode == 0
    report = {
        "suite": "E0",
        "passed": passed,
        "returncode": completed.returncode,
        "tests": E0_TESTS,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
        "components": {
            "E0.1_hand_weights": passed,
            "E0.2_ipw_monte_carlo": passed,
            "E0.3_p2_uniqueness": passed,
            "E0.4_debt_prefix": passed,
            "E0.5_window_timing": passed,
            "E0.6_q_leakage_scan": passed,
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "e0_unit_check.json"
    dump_json(report, out)
    print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)
    print(f"report={out}")
    print(f"e0_overall={'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
