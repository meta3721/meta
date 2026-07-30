#!/usr/bin/env python3
"""Environment and repository verification for RAVEN-MCS."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs import CONSTITUTION_VERSION, OFFICIAL_PYTHON, __version__
from raven_mcs.experiments.registry import KNOWN_EXPERIMENTS
from raven_mcs.utils.config import load_base_config, resolve_run_config
from raven_mcs.utils.hashing import environment_fingerprint
from raven_mcs.utils.manifest import REQUIRED_MANIFEST_FIELDS, build_manifest
from raven_mcs.utils.seed import SeedBundle
from raven_mcs.utils.validation import validate_config


REQUIRED_PATHS = [
    "pyproject.toml",
    "environment.yml",
    "requirements.txt",
    "requirements-lock.txt",
    "configs/config.yaml",
    "configs/seeds_20.txt",
    "src/raven_mcs/__init__.py",
    "src/raven_mcs/utils/seed.py",
    "src/raven_mcs/utils/manifest.py",
    "src/raven_mcs/utils/hashing.py",
    "src/raven_mcs/utils/validation.py",
    "src/raven_mcs/utils/run.py",
    "src/raven_mcs/training/checkpoints.py",
    "docs/IMPLEMENTATION_PLAN.md",
    "docs/FORMULA_TO_CODE_MAP.md",
    "docs/SOURCES.md",
    "STATUS.md",
    "ISSUES.md",
]


def check_environment() -> int:
    info = environment_fingerprint()
    py = sys.version_info
    print(f"raven-mcs version: {__version__}")
    print(f"constitution: {CONSTITUTION_VERSION}")
    print(f"official_python: {OFFICIAL_PYTHON}")
    print(f"detected_python: {py.major}.{py.minor}.{py.micro}")
    print(f"executable: {info['executable']}")
    print(f"platform: {info['platform']}")

    errors: list[str] = []
    if py < (3, 11):
        errors.append(
            f"Python >= 3.11 required; found {py.major}.{py.minor}.{py.micro}"
        )
    if f"{py.major}.{py.minor}" != OFFICIAL_PYTHON:
        print(
            f"WARNING: official reproducibility Python is {OFFICIAL_PYTHON}; "
            f"current is {py.major}.{py.minor}.{py.micro} (ISSUE-001)."
        )
    else:
        print(f"Python minor matches official pin ({OFFICIAL_PYTHON}).")

    for mod in ("numpy", "yaml", "pandas", "pytest"):
        try:
            __import__(mod if mod != "yaml" else "yaml")
            print(f"dependency OK: {mod}")
        except ImportError:
            errors.append(f"missing dependency: {mod}")

    if errors:
        print("ENVIRONMENT CHECK FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("ENVIRONMENT CHECK PASSED")
    return 0


def check_repository(*, require_git: bool = False) -> int:
    root = _REPO_ROOT
    errors: list[str] = []
    for rel in REQUIRED_PATHS:
        if not (root / rel).exists():
            errors.append(f"missing path: {rel}")

    try:
        cfg = load_base_config()
        result = validate_config(cfg)
        if not result.ok:
            errors.extend(result.errors)
        else:
            print("base config validation OK")
            resolve_run_config(validate=True)
            print("resolved default run config OK")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"config load/validate failed: {exc}")

    for exp in ("E0_unit", "E1_balanced"):
        if exp not in KNOWN_EXPERIMENTS:
            errors.append(f"registry missing experiment: {exp}")

    try:
        probe = build_manifest(
            run_id="verification",
            config=resolve_run_config(validate=True),
            seed_bundle=SeedBundle.from_master(26001),
            data_hash="a" * 64,
            event_trace_hash="b" * 64,
            repo_root=root,
            require_git=require_git,
        )
        manifest_errors = probe.validate()
        if manifest_errors:
            errors.extend(manifest_errors)
        else:
            print(
                f"required manifest fields ({len(REQUIRED_MANIFEST_FIELDS)}): "
                "schema and values OK"
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"manifest construction failed: {exc}")

    git_executable = shutil.which("git")
    if git_executable is None or not (root / ".git").exists():
        message = "Git executable/repository unavailable; paper runs must use --require-git"
        if require_git:
            errors.append(message)
        else:
            print(f"WARNING: {message}")
    else:
        print(f"Git audit available: {git_executable}")

    for rel in ("outputs/runs", "outputs/aggregate", "outputs/reproducibility"):
        if not (root / rel).is_dir():
            errors.append(f"missing output directory: {rel}")

    if errors:
        print("REPOSITORY CHECK FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("REPOSITORY CHECK PASSED (PHASE 1 INFRASTRUCTURE ONLY)")
    print("DATA, MODELS, E0, AND G0-G7 ARE NOT VERIFIED BY THIS COMMAND")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify RAVEN-MCS environment/repository"
    )
    parser.add_argument("--check-environment", action="store_true")
    parser.add_argument("--check-repository", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="Accepted for CLI uniformity."
    )
    parser.add_argument(
        "--require-git",
        action="store_true",
        help="Fail unless Git and repository metadata are available.",
    )
    args = parser.parse_args(argv)

    if not args.check_environment and not args.check_repository:
        parser.error("Specify --check-environment and/or --check-repository")

    code = 0
    if args.check_environment:
        code = max(code, check_environment())
    if args.check_repository:
        code = max(code, check_repository(require_git=args.require_git))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
