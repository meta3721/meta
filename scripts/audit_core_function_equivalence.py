#!/usr/bin/env python3
"""Prove the frozen E1 numerical implementation is blob-identical."""
from __future__ import annotations

import argparse
import ast
import subprocess
from pathlib import Path

import pandas as pd

from raven_mcs.utils.serialization import dump_json

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"
COMPONENTS = {
    "local training": ["src/raven_mcs/training/client.py", "src/raven_mcs/training/local_objective.py"],
    "p_obs": ["src/raven_mcs/propensity/observation.py"],
    "q_use": ["src/raven_mcs/propensity/usable.py"],
    "opportunity EMA": ["src/raven_mcs/opportunities/estimator.py"],
    "zeta": ["src/raven_mcs/correction/design_ratio.py"],
    "Hajek weights": ["src/raven_mcs/correction/hajek.py"],
    "second-stage": ["src/raven_mcs/aggregation/methods.py"],
    "TimeAlign": ["src/raven_mcs/aggregation/method_policy.py"],
    "P2": ["src/raven_mcs/aggregation/p2_cvxpy.py"],
    "debt": ["src/raven_mcs/aggregation/debt.py", "src/raven_mcs/metrics/debt.py"],
    "variance": ["src/raven_mcs/metrics/variance.py"],
    "arrival risk": ["src/raven_mcs/training/window_runner.py"],
    "RMSE_mu": ["src/raven_mcs/metrics/accuracy.py"],
    "RMSE_rho": ["src/raven_mcs/metrics/accuracy.py"],
    "Gap_mis": ["src/raven_mcs/metrics/accuracy.py"],
}
ENTRY = "src/raven_mcs/experiments/e1_entry.py"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout.strip()


def blob(root: Path, commit: str, path: str) -> str | None:
    try:
        return git(root, "rev-parse", f"{commit}:{path}")
    except subprocess.CalledProcessError:
        return None


def functions(root: Path, commit: str) -> dict[str, str]:
    source = git(root, "show", f"{commit}:{ENTRY}")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    return {
        node.name: "".join(lines[node.lineno - 1:node.end_lineno])
        for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorized", default=AUTHORIZED)
    parser.add_argument("--candidate", default=None)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    candidate = args.candidate or git(root, "rev-parse", "HEAD")
    evidence = root / "evidence/code_audit"
    evidence.mkdir(parents=True, exist_ok=True)

    rows = []
    component_rows = []
    changed_functions = []
    for component, paths in COMPONENTS.items():
        for path in paths:
            old, new = blob(root, args.authorized, path), blob(root, candidate, path)
            record = {"kind": "component", "component": component, "path": path,
                      "function": None, "authorized_blob": old, "candidate_blob": new,
                      "status": "UNCHANGED" if old == new else "CHANGED"}
            rows.append(record)
            component_rows.append(record)
    old_functions, new_functions = functions(root, args.authorized), functions(root, candidate)
    for name in sorted(set(old_functions) | set(new_functions)):
        old, new = old_functions.get(name), new_functions.get(name)
        if old != new:
            changed_functions.append({
                "component": "e1_entry", "path": ENTRY, "function": name,
                "status": "CHANGED",
            })
    frame = pd.DataFrame(rows)
    try:
        frame.to_parquet(evidence / "CORE_FUNCTION_EQUIVALENCE.parquet", index=False)
        table = "CORE_FUNCTION_EQUIVALENCE.parquet"
    except (ImportError, ValueError):
        frame.to_csv(evidence / "CORE_FUNCTION_EQUIVALENCE.csv", index=False)
        table = "CORE_FUNCTION_EQUIVALENCE.csv"
    dump_json({"authorized_commit": args.authorized, "candidate_commit": candidate,
               "components": component_rows,
               "all_core_blobs_identical": all(
                   row["status"] == "UNCHANGED" for row in component_rows)},
              evidence / "CORE_PATH_EQUIVALENCE.json")
    dump_json({"authorized_commit": args.authorized, "candidate_commit": candidate,
               "table": table, "changed_e1_entry_functions": changed_functions,
               "changed_function_count": len(changed_functions)},
              evidence / "CORE_FUNCTION_EQUIVALENCE_SUMMARY.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
