#!/usr/bin/env python3
"""Audit that execution HEAD only changes orchestration/freeze identity paths."""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from pathlib import Path

AUTHORIZED_DEFAULT = "53e277c53b01695330652b8e1bc8a234909d56e5"

ALLOWED = [
    "configs/frozen/**",
    "manifests/**",
    "scripts/check_e1_formal_*.py",
    "scripts/run_e1_formal*.py",
    "scripts/export_e1_formal_*.py",
    "scripts/rebuild_frozen_config_manifest.py",
    "scripts/verify_frozen_config_manifest.py",
    "scripts/generate_e1_formal_resolved_config.py",
    "scripts/audit_execution_diff_scope.py",
    "scripts/audit_e1_formal_freeze_baseline.py",
    "scripts/run_e1_formal_freeze_*.py",
    "scripts/check_e1_formal_freeze_gates.py",
    "scripts/select_e1_baseline.py",
    "scripts/aggregate_results.py",
    "scripts/statistical_tests.py",
    "scripts/freeze_config.py",
    "scripts/run_e1_r4_*.py",
    "scripts/run_experiment.py",
    "src/raven_mcs/experiments/**",
    "tests/**/*freeze*",
    "tests/**/*formal*",
    "tests/unit/test_e1_entry_*.py",
    "docs/**",
    "STATUS.md",
    "ISSUES.md",
    "CHANGELOG.md",
    ".gitignore",
    "deliverables/**",
    "logs/**",
    "outputs/**",
]

FORBIDDEN_PREFIXES = [
    "src/raven_mcs/training/",
    "src/raven_mcs/aggregation/",
    "src/raven_mcs/propensity/",
    "src/raven_mcs/correction/",
    "src/raven_mcs/opportunities/",
    "src/raven_mcs/models/",
    "src/raven_mcs/data/",
    "src/raven_mcs/metrics/",
    "src/raven_mcs/simulation/",
]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout


def _allowed(path: str) -> bool:
    posix = path.replace("\\", "/")
    for pattern in ALLOWED:
        if fnmatch.fnmatch(posix, pattern):
            return True
    return False


def _forbidden(path: str) -> bool:
    posix = path.replace("\\", "/")
    return any(posix.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorized-commit", default=AUTHORIZED_DEFAULT)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    execution = _git(root, "rev-parse", "HEAD").strip()
    diff = _git(
        root, "diff", "--name-only", f"{args.authorized_commit}...{execution}",
    )
    modified = [line.strip().replace("\\", "/") for line in diff.splitlines() if line.strip()]
    # Also include uncommitted tracked modifications for local review.
    dirty = [
        line[3:].replace("\\", "/").strip()
        for line in _git(root, "status", "--porcelain").splitlines()
        if line.strip() and not line.startswith("??")
    ]
    untracked = [
        line[3:].replace("\\", "/").strip()
        for line in _git(root, "status", "--porcelain").splitlines()
        if line.startswith("??")
    ]
    all_paths = sorted(set(modified + dirty + untracked))
    allowed_paths = [path for path in all_paths if _allowed(path)]
    forbidden_core = [
        path for path in all_paths if _forbidden(path) or not _allowed(path)
    ]
    # Untracked under allowed patterns are fine; only forbidden if core.
    forbidden_core = [
        path for path in all_paths
        if _forbidden(path) or (path.startswith("src/") and not _allowed(path))
    ]
    result = {
        "authorized_algorithm_commit": args.authorized_commit,
        "execution_commit": execution,
        "modified_files": all_paths,
        "allowed_paths": allowed_paths,
        "forbidden_paths": forbidden_core,
        "forbidden_core_changes": len(forbidden_core),
        "status": "PASS" if not forbidden_core else "FAIL",
    }
    out = root / "outputs/audits/e1_formal_execution_diff_scope.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "forbidden_core_changes": result["forbidden_core_changes"],
        "modified_count": len(all_paths),
    }, indent=2))
    if result["status"] != "PASS":
        raise RuntimeError(
            "forbidden core changes: " + ", ".join(forbidden_core)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
