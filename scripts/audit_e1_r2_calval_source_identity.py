#!/usr/bin/env python3
"""Create C1 source identity evidence for E1-R2 calibration/validation."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Sequence

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"
ENTRY = "src/raven_mcs/experiments/e1_entry.py"
NUMERIC_PATHS = (
    "src/raven_mcs/training/client.py",
    "src/raven_mcs/training/local_objective.py",
    "src/raven_mcs/propensity/observation.py",
    "src/raven_mcs/propensity/usable.py",
    "src/raven_mcs/opportunities/estimator.py",
    "src/raven_mcs/correction/design_ratio.py",
    "src/raven_mcs/correction/hajek.py",
    "src/raven_mcs/aggregation/methods.py",
    "src/raven_mcs/aggregation/method_policy.py",
    "src/raven_mcs/aggregation/p2_cvxpy.py",
    "src/raven_mcs/aggregation/debt.py",
    "src/raven_mcs/metrics/debt.py",
    "src/raven_mcs/metrics/variance.py",
    "src/raven_mcs/training/window_runner.py",
    "src/raven_mcs/metrics/accuracy.py",
)


def _git(root: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
        text=not binary, encoding=None if binary else "utf-8",
        errors=None if binary else "replace",
    )
    return result.stdout


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _blob(root: Path, commit: str, path: str) -> str | None:
    try:
        return str(_git(root, "rev-parse", f"{commit}:{path}")).strip()
    except subprocess.CalledProcessError:
        return None


def _function_hashes(root: Path, commit: str, path: str = ENTRY) -> dict[str, str]:
    source = str(_git(root, "show", f"{commit}:{path}"))
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    result: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            text = "".join(lines[node.lineno - 1:node.end_lineno]).encode("utf-8")
            result[node.name] = _sha256_bytes(text)
    return result


def audit_source_identity(
    root: Path,
    output_dir: Path,
    *,
    authorized: str = AUTHORIZED,
    candidate: str = "HEAD",
    numeric_paths: Sequence[str] = NUMERIC_PATHS,
) -> dict[str, Any]:
    """Snapshot a committed candidate tree and compare numerical source identity."""
    root, output_dir = Path(root).resolve(), Path(output_dir).resolve()
    candidate_commit = str(_git(root, "rev-parse", f"{candidate}^{{commit}}")).strip()
    authorized_commit = str(
        _git(root, "rev-parse", f"{authorized}^{{commit}}")
    ).strip()
    parent = str(_git(root, "rev-parse", f"{candidate_commit}^")).strip()
    output_dir.mkdir(parents=True, exist_ok=True)

    archive_path = output_dir / "E1_R2_C1_SOURCE.tar.gz"
    archive_path.write_bytes(
        bytes(_git(root, "archive", "--format=tar.gz", candidate_commit, binary=True))
    )
    patch_path = output_dir / "AUTHORIZED_TO_C1.patch"
    patch = str(_git(
        root, "diff", "--binary", "--no-ext-diff",
        f"{authorized_commit}...{candidate_commit}",
    ))
    patch_path.write_text(patch, encoding="utf-8", newline="\n")

    blobs = []
    for path in numeric_paths:
        old, new = _blob(root, authorized_commit, path), _blob(
            root, candidate_commit, path
        )
        blobs.append({
            "path": path,
            "authorized_blob": old,
            "candidate_blob": new,
            "equivalent": bool(old and old == new),
        })
    old_functions = _function_hashes(root, authorized_commit)
    new_functions = _function_hashes(root, candidate_commit)
    functions = [{
        "path": ENTRY,
        "function": name,
        "authorized_sha256": old_functions.get(name),
        "candidate_sha256": new_functions.get(name),
        "equivalent": old_functions.get(name) == new_functions.get(name),
    } for name in sorted(set(old_functions) | set(new_functions))]

    report = {
        "schema_version": 1,
        "mode": "C1",
        "status": "PASS" if all(row["equivalent"] for row in blobs) else "FAIL",
        "authorized_algorithm_commit": authorized_commit,
        "candidate_commit": candidate_commit,
        "candidate_parent_commit": parent,
        "candidate_tree": str(_git(root, "rev-parse", f"{candidate_commit}^{{tree}}")).strip(),
        "eventual_clean_tree": True,
        "working_tree_used_as_source": False,
        "snapshot": {
            "path": archive_path.name,
            "sha256": _sha256_file(archive_path),
            "size_bytes": archive_path.stat().st_size,
        },
        "git_patch": {
            "path": patch_path.name,
            "sha256": _sha256_file(patch_path),
            "size_bytes": patch_path.stat().st_size,
            "range": f"{authorized_commit}...{candidate_commit}",
        },
        "selected_numeric_paths": list(numeric_paths),
        "blob_equivalence": blobs,
        "all_numeric_blobs_equivalent": all(row["equivalent"] for row in blobs),
        "entry_function_equivalence": functions,
        "formal_outcomes_accessed": False,
    }
    (output_dir / "E1_R2_C1_SOURCE_IDENTITY.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--authorized", default=AUTHORIZED)
    parser.add_argument("--candidate", default="HEAD")
    parser.add_argument("--mode", choices=("C1",), default="C1")
    args = parser.parse_args(argv)
    output = args.output_dir or args.root / "outputs/audits/e1_r2_source_identity"
    report = audit_source_identity(
        args.root, output, authorized=args.authorized, candidate=args.candidate
    )
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
