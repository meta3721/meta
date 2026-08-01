"""Reproducible Phase 0 repository scans required by the experiment constitution."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import yaml

AUDIT_VERSION = "1.0"
SCAN_ROOTS = ("src", "scripts", "configs", "tests", "notebooks")
CODE_CONFIG_SUFFIXES = {".py", ".yaml", ".yml", ".toml", ".json", ".ipynb"}
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "Lib",
    "build",
    "dist",
    "node_modules",
}
SCANNER_EXCLUDED_FILES = {
    "scripts/audit_phase0.py",
    "src/raven_mcs/experiments/phase0_audit.py",
    "tests/unit/test_phase0_audit.py",
}

SCAN_PATTERNS = {
    "immediate_async": (
        r"\bon_arrival\b",
        r"\barrival_callback\b",
        r"global[_ ]model.*(?:update|step).*arrival",
        r"(?:update|step).*global[_ ]model.*arrival",
    ),
    "test_tuning": (
        r"\btest\b.{0,80}\b(?:tune|select|choose|best|hyperparam)",
        r"\b(?:tune|select|choose|best|hyperparam).{0,80}\btest\b",
        r"(?:tune|select|choose|best|hyperparam)[A-Za-z0-9_]{0,80}test",
        r"test[A-Za-z0-9_]{0,80}(?:tune|select|choose|best|hyperparam)",
        r"\boptuna\b",
        r"\btest[_ ](?:score|metric|rmse|loss)\b.{0,80}\b(?:min|max|best)",
    ),
    "q_post_outcome": (
        r"\brealized\b",
        r"\barrival\b",
        r"\bfuture\b",
        r"\bupdate_norm\b",
        r"\bupdate_value\b",
        r"\bactual_delay\b",
    ),
    "p2_current_update": (
        r"\bcurrent[_ ]update(?:\b|_)",
        r"\bupdate[_ ](?:norm|vector|direction|coordinate|coordinates)\b",
        r"\bu[_ ](?:norm|vector|direction|coordinate|coordinates)\b",
    ),
}


@dataclass(frozen=True)
class ScanHit:
    path: str
    line: int
    pattern: str
    text: str


def _is_excluded(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return any(part in EXCLUDED_DIRS for part in relative.parts)


def repository_tree_files(root: Path) -> list[str]:
    """Return the complete project file tree with only declared exclusions."""
    root = Path(root).resolve()
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not _is_excluded(path, root)
    )


def scan_scope_files(root: Path) -> list[Path]:
    root = Path(root).resolve()
    files: list[Path] = []
    for relative_root in SCAN_ROOTS:
        directory = root / relative_root
        if not directory.exists():
            continue
        files.extend(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and path.suffix.lower() in CODE_CONFIG_SUFFIXES
            and not _is_excluded(path, root)
            and path.relative_to(root).as_posix() not in SCANNER_EXCLUDED_FILES
        )
    return sorted(set(files), key=lambda path: path.relative_to(root).as_posix())


def _read_text(path: Path) -> tuple[Path, str, str | None]:
    try:
        return path, path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeError) as exc:
        return path, "", f"{type(exc).__name__}: {exc}"


def _scan_patterns(
    root: Path,
    files: Iterable[tuple[Path, str]],
    patterns: tuple[str, ...],
) -> list[ScanHit]:
    compiled = [(pattern, re.compile(pattern, re.IGNORECASE)) for pattern in patterns]
    hits: list[ScanHit] = []
    for path, text in files:
        for line_number, line in enumerate(text.splitlines(), start=1):
            for pattern, regex in compiled:
                if regex.search(line):
                    hits.append(
                        ScanHit(
                            path=path.relative_to(root).as_posix(),
                            line=line_number,
                            pattern=pattern,
                            text=line.strip()[:300],
                        )
                    )
    return hits


def run_phase0_audit(root: Path, *, max_workers: int = 1) -> dict[str, object]:
    """Run all mandatory Phase 0 scans and return JSON-serializable evidence."""
    root = Path(root).resolve()
    scope = scan_scope_files(root)
    worker_count = max(1, int(max_workers))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        read_results = list(executor.map(_read_text, scope))
    read_errors = {
        path.relative_to(root).as_posix(): error
        for path, _, error in read_results
        if error is not None
    }
    readable = [(path, text) for path, text, error in read_results if error is None]

    executable = [
        item
        for item in readable
        if item[0].parts[len(root.parts)] in {"src", "scripts", "configs", "notebooks"}
    ]
    q_candidates = [
        item
        for item in executable
        if (
            (
                "propensity" in item[0].parts
                and item[0].name not in {"__init__.py", "leakage.py"}
            )
            or "usable" in item[0].stem.lower()
            or re.search(r"\b(?:q_features|usable_features|Xuse)\b", item[1])
        )
    ]
    p2_candidates = [
        item
        for item in executable
        if "p2" in item[0].stem.lower()
        or (
            "aggregation" in item[0].parts
            and item[0].name != "__init__.py"
        )
    ]

    scan_inputs = {
        "immediate_async": readable,
        "test_tuning": readable,
        "q_post_outcome": q_candidates,
        "p2_current_update": p2_candidates,
    }
    scans: dict[str, object] = {}
    whitelist_path = root / "configs" / "audit" / "q_feature_whitelist.yaml"
    whitelist_files: set[str] = set()
    if whitelist_path.exists():
        whitelist = yaml.safe_load(whitelist_path.read_text(encoding="utf-8")) or {}
        whitelist_files = {
            str(entry["file"]).replace("\\", "/")
            for entry in whitelist.get("entries", [])
            if all(entry.get(key) for key in ("file", "symbol", "reason", "allowed_role"))
        }
    for name, files in scan_inputs.items():
        hits = _scan_patterns(root, files, SCAN_PATTERNS[name])
        reviewed_only = bool(hits) and all(hit.path in whitelist_files for hit in hits)
        scans[name] = {
            "patterns": list(SCAN_PATTERNS[name]),
            "candidate_files": [
                path.relative_to(root).as_posix() for path, _ in files
            ],
            "hits": [asdict(hit) for hit in hits],
            "status": (
                "VACUOUS_NO_IMPLEMENTATION"
                if name in {"q_post_outcome", "p2_current_update"} and not files
                else (
                    "REVIEWED_WHITELIST_ONLY"
                    if name == "q_post_outcome" and reviewed_only
                    else ("MATCHES_REQUIRE_REVIEW" if hits else "NO_MATCHES")
                )
            ),
        }

    source_files = [path for path, _ in executable]
    dataset_files = [
        path.relative_to(root).as_posix()
        for path in source_files
        if "data" in path.parts and path.name != "__init__.py"
    ]
    model_files = [
        path.relative_to(root).as_posix()
        for path in source_files
        if "models" in path.parts and path.name != "__init__.py"
    ]
    run_artifacts = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "outputs" / "runs").rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    )
    frozen_configs = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "configs" / "frozen").glob("*.yaml")
        if path.is_file()
    )
    required_tests = {
        "test_no_post_outcome_features",
        "test_p2_not_using_current_update",
        "test_no_test_leakage",
        "test_window_model_frozen",
        "test_one_update_per_window",
    }
    test_names = set(
        re.findall(
            r"^def (test_[A-Za-z0-9_]+)",
            "\n".join(text for path, text in readable if "tests" in path.parts),
            flags=re.MULTILINE,
        )
    )
    return {
        "audit_version": AUDIT_VERSION,
        "repository_root": str(root),
        "scope_roots": list(SCAN_ROOTS),
        "excluded_directories": sorted(EXCLUDED_DIRS),
        "excluded_files": sorted(SCANNER_EXCLUDED_FILES),
        "tree_files": repository_tree_files(root),
        "scan_files": [path.relative_to(root).as_posix() for path in scope],
        "read_errors": read_errors,
        "inventory": {
            "dataset_files": dataset_files,
            "model_files": model_files,
        },
        "scans": scans,
        "test_leakage_gate": {
            "frozen_configs": frozen_configs,
            "missing_required_tests": sorted(required_tests - test_names),
            "status": (
                "PASS"
                if frozen_configs and not (required_tests - test_names)
                else "INCOMPLETE"
            ),
        },
        "main_experiment_artifacts": run_artifacts,
        "main_experiment_status": "NOT_STARTED" if not run_artifacts else "ARTIFACTS_FOUND",
    }
