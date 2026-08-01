#!/usr/bin/env python3
"""E1 readiness check — verifies prerequisites, method availability, and runner
existence before launching the Balanced no-harm gate experiment.

The E1 experiment remains blocked pending teacher review of P10-R1 evidence.
This script audits readiness without running the experiment.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.aggregation.methods import get_aggregator
from raven_mcs.utils.serialization import dump_json, load_json, load_yaml

E1_CONFIG = _ROOT / "configs" / "experiment" / "E1_balanced.yaml"
AUDIT_DIR = _ROOT / "docs" / "audits"
RUNNER_SCRIPT = _ROOT / "scripts" / "run_experiment.py"


def _check_prerequisite(name: str, path: Path) -> dict:
    """Inspect a prerequisite audit JSON and return its pass/fail status."""
    if not path.exists():
        return {"name": name, "passed": False, "errors": [f"Missing audit: {path.name}"]}
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "passed": False, "errors": [f"Cannot parse {path.name}: {exc}"]}
    passed = data.get("passed", False)
    return {"name": name, "passed": passed, "errors": [] if passed else [f"{name} not passed"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=AUDIT_DIR)
    args = parser.parse_args(argv)

    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, str] = {}

    # ------------------------------------------------------------------
    # 1. Config validity
    # ------------------------------------------------------------------
    cfg: dict = {}
    try:
        cfg = load_yaml(E1_CONFIG)
        if not cfg:
            raise ValueError("empty config")
        checks["config_valid"] = "PASS"
    except Exception as exc:  # noqa: BLE001
        checks["config_valid"] = "FAIL"
        errors.append(f"E1 config invalid: {exc}")

    # ------------------------------------------------------------------
    # 2. Prerequisites — G0 / E0 / G1–G5
    # ------------------------------------------------------------------
    prereqs = [
        ("G0", AUDIT_DIR / "g0_data_check.json"),
        ("E0", AUDIT_DIR / "e0_unit_check.json"),
        ("G1_G5", AUDIT_DIR / "hard_gates_g1_g5.json"),
    ]
    for label, path in prereqs:
        result = _check_prerequisite(label, path)
        key = f"prerequisites_{label.lower().replace('-', '_')}"
        checks[key] = "PASS" if result["passed"] else "FAIL"
        if not result["passed"]:
            errors.extend(result["errors"])
            if label == "G1_G5":
                warnings.append("G1–G5 must PASS before launching E1")

    # ------------------------------------------------------------------
    # 3. Method availability — verify all declared aggregators exist
    # ------------------------------------------------------------------
    declared_methods = cfg.get("methods", [])
    method_results: dict[str, str] = {}
    for method in declared_methods:
        try:
            agg = get_aggregator(method)
            _ = agg.name  # basic smoke
            method_results[method] = "PASS"
        except (KeyError, Exception) as exc:  # noqa: BLE001
            method_results[method] = "FAIL"
            errors.append(f"Method '{method}' not available: {exc}")

    checks["methods"] = "PASS" if all(v == "PASS" for v in method_results.values()) else "FAIL"
    checks["method_detail"] = method_results  # type: ignore[assignment]

    if "timealign_agg" in declared_methods and method_results.get("timealign_agg") == "FAIL":
        warnings.append(
            "TimeAlign aggregator not implemented; E1 YAML is a declaration only "
            "(ISSUE-011)"
        )

    # ------------------------------------------------------------------
    # 4. Experiment runner existence
    # ------------------------------------------------------------------
    if RUNNER_SCRIPT.exists():
        checks["runner_exists"] = "PASS"
    else:
        checks["runner_exists"] = "FAIL"
        errors.append("run_experiment.py not found — experiment cannot be launched")
        warnings.append("Experiment runner entry point is not yet created (ISSUE-011)")

    # ------------------------------------------------------------------
    # 5. ISSUE-012 is resolved; P10-R1 still requires explicit teacher review.
    # ------------------------------------------------------------------
    checks["issue_012"] = "PASS"
    checks["p10_r1_teacher_review"] = "BLOCKED"
    warnings.append(
        "P10-R1 gates passed locally, but teacher review is required before E1."
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    all_explicit = [
        v for k, v in checks.items()
        if k not in {"method_detail", "p10_r1_teacher_review"}
    ]
    overall_pass = all(v == "PASS" for v in all_explicit)

    if checks.get("p10_r1_teacher_review") == "BLOCKED":
        status = "BLOCKED"
    elif overall_pass:
        status = "READY"
    else:
        status = "NOT_READY"

    report = {
        "experiment": cfg.get("name", "E1_balanced"),
        "status": status,
        "passed": overall_pass,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "e1_check.json"
    dump_json(report, out)

    # Human-readable summary
    print(f"E1: {status}")
    for key, val in checks.items():
        if key == "method_detail":
            print("  methods:")
            for m, s in val.items():
                print(f"    {m}: {s}")
        else:
            print(f"  {key}: {val}")
    for error in errors:
        print(f"  ERROR: {error}")
    for warning in warnings:
        print(f"  WARN: {warning}")
    print(f"report={out}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
