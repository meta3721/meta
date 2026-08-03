#!/usr/bin/env python3
"""Audit that post-selection work never inspected E1-R2 formal seeds."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = (
    ROOT / "outputs",
    ROOT / "data/frozen/e1_r2/formal",
)
FORBIDDEN_TOKENS = (
    "train",
    "metric",
    "prediction",
    "checkpoint",
    "gradient",
    "model_state",
)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _read_formal_seeds(manifest_path: Path) -> list[int]:
    if not manifest_path.is_file():
        return []
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [int(seed) for seed in document.get("formal_seeds", [])]


def _key_is_forbidden(key: object) -> bool:
    lowered = str(key).lower()
    return any(token in lowered for token in FORBIDDEN_TOKENS)


def _matching_seed(value: object, seeds: set[int]) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        candidate = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return candidate if candidate in seeds else None


def _walk_json(
    value: object,
    seeds: set[int],
    source: Path,
    trail: tuple[str, ...] = (),
) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        record_seed = next(
            (
                _matching_seed(value[key], seeds)
                for key in ("seed", "run_seed", "data_seed", "formal_seed")
                if key in value and _matching_seed(value[key], seeds) is not None
            ),
            None,
        )
        if record_seed is not None:
            for key, child in value.items():
                activity_recorded = child not in (None, False, 0, "", [], {})
                if _key_is_forbidden(key) and activity_recorded:
                    yield {
                        "source": source.as_posix(),
                        "seed": record_seed,
                        "kind": str(key),
                        "location": ".".join((*trail, str(key))),
                    }
        for key, child in value.items():
            yield from _walk_json(child, seeds, source, (*trail, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_json(child, seeds, source, (*trail, str(index)))


def _path_findings(path: Path, seeds: set[int]) -> Iterable[dict[str, Any]]:
    lowered = path.as_posix().lower()
    named_seed = next(
        (
            seed
            for seed in seeds
            if re.search(rf"(?<!\d){seed}(?!\d)", lowered)
        ),
        None,
    )
    if named_seed is not None and any(token in lowered for token in FORBIDDEN_TOKENS):
        category = next(
            (token for token in FORBIDDEN_TOKENS if token in lowered),
            "forbidden_artifact",
        )
        yield {
            "source": path.as_posix(),
            "seed": named_seed,
            "kind": category,
            "location": path.name,
        }

    if path.suffix.lower() not in {".json", ".jsonl", ".yaml", ".yml"}:
        return
    try:
        if path.suffix.lower() == ".json":
            documents = [json.loads(path.read_text(encoding="utf-8"))]
        elif path.suffix.lower() == ".jsonl":
            documents = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            documents = [yaml.safe_load(path.read_text(encoding="utf-8"))]
    except (OSError, json.JSONDecodeError, yaml.YAMLError):
        return
    for document in documents:
        yield from _walk_json(document, seeds, path)


def audit_noninspection(
    manifest_path: Path,
    selection_roots: Iterable[Path],
) -> dict[str, Any]:
    """Return PASS/BLOCKED/FAIL and exact forbidden-record counters."""
    formal_seeds = _read_formal_seeds(manifest_path)
    roots = list(selection_roots)
    present_roots = [root for root in roots if root.exists()]
    if not formal_seeds:
        return {
            "status": "BLOCKED",
            "reason": "frozen manifest with formal_seeds is absent or incomplete",
            "formal_seeds": formal_seeds,
            "formal_seed_training_records": 0,
            "formal_seed_metric_records": 0,
            "formal_seed_prediction_records": 0,
            "findings": [],
            "formal_experiments_run": 0,
        }
    if not present_roots:
        return {
            "status": "BLOCKED",
            "reason": "post-selection output roots are absent",
            "formal_seeds": formal_seeds,
            "formal_seed_training_records": 0,
            "formal_seed_metric_records": 0,
            "formal_seed_prediction_records": 0,
            "findings": [],
            "formal_experiments_run": 0,
        }

    findings: list[dict[str, Any]] = []
    scanned: list[str] = []
    for root in present_roots:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            scanned.append(path.as_posix())
            findings.extend(_path_findings(path, set(formal_seeds)))

    def count(token: str) -> int:
        return sum(token in str(item["kind"]).lower() for item in findings)

    training_count = count("train") + count("gradient") + count("checkpoint")
    metric_count = count("metric")
    prediction_count = count("prediction")
    status = "PASS" if not findings else "FAIL"
    return {
        "status": status,
        "reason": (
            "zero formal-seed training, metrics, or predictions in post-selection evidence"
            if status == "PASS"
            else "formal-seed post-selection inspection evidence was found"
        ),
        "formal_seeds": formal_seeds,
        "selection_roots": [path.as_posix() for path in present_roots],
        "files_scanned": len(scanned),
        "formal_seed_training_records": training_count,
        "formal_seed_metric_records": metric_count,
        "formal_seed_prediction_records": prediction_count,
        "findings": findings,
        "formal_experiments_run": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "configs/frozen/E1_R2_FROZEN_CONFIG_MANIFEST.json",
    )
    parser.add_argument(
        "--selection-root",
        action="append",
        type=Path,
        dest="selection_roots",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/audits/E1_R2_FORMAL_SEED_NONINSPECTION.json",
    )
    args = parser.parse_args(argv)
    result = audit_noninspection(
        args.manifest.resolve(),
        [path.resolve() for path in (args.selection_roots or DEFAULT_ROOTS)],
    )
    _write_json(args.output, result)
    print(json.dumps(result, indent=2))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
