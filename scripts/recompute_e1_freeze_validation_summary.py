#!/usr/bin/env python3
"""Copy raw E1 freeze-safety artifacts and recompute their summary."""
from __future__ import annotations

import shutil
from pathlib import Path

from raven_mcs.utils.serialization import dump_json, load_json

SEEDS = (26001, 26002, 26003, 26004, 26005)


def copy_artifacts(source: Path, target: Path) -> list[str]:
    target.mkdir(parents=True, exist_ok=True)
    patterns = ("manifest.json", "resolved_config.yaml", "metrics_run.json",
                "metrics_window.parquet", "*diagnostics*.parquet", "stdout.log", "stderr.log")
    copied = []
    for pattern in patterns:
        for path in source.glob(pattern):
            if path.is_file() and path.name not in copied:
                shutil.copy2(path, target / path.name)
                copied.append(path.name)
    return sorted(copied)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    source_root = root / "outputs/validation/e1_formal_freeze_r1_safety_runs"
    evidence = root / "evidence/validation"
    rows, unavailable = [], []
    for seed in SEEDS:
        candidates = sorted(source_root.glob(f"E1_BALANCED_raven_{seed}_*"))
        if not candidates:
            unavailable.append(seed)
            continue
        run = candidates[-1]
        metrics = load_json(run / "metrics_run.json")
        rows.append({
            "seed": seed, "local_steps": 2,
            "first_stage_clip_rate": metrics["first_stage_clip_rate"],
            "second_stage_clip_rate": metrics["second_stage_clip_rate"],
            "median_n_eff": metrics["median_n_eff"],
            "q_nonattempt_leakage": metrics["q_nonattempt_leakage_count"],
            "failed_attempt_omission": metrics["q_failed_attempt_omission_count"],
            "unsupported_arrival_contribution": metrics["unsupported_arrival_contribution_sum"],
            "solver_failures": metrics["solver_failure_count"],
            "run_dir": str(run.relative_to(root)),
        })
        rows[-1]["passes"] = bool(
            rows[-1]["first_stage_clip_rate"] <= .05 and
            rows[-1]["second_stage_clip_rate"] <= .05 and
            rows[-1]["median_n_eff"] >= 2 and
            rows[-1]["q_nonattempt_leakage"] == 0 and
            rows[-1]["failed_attempt_omission"] == 0 and
            rows[-1]["unsupported_arrival_contribution"] == 0 and
            rows[-1]["solver_failures"] == 0)
        rows[-1]["copied_artifacts"] = copy_artifacts(run, evidence / f"seed_{seed}")
    summary = {
        "evaluation_split": "validation", "test_read_count": 0, "local_steps": 2,
        "all_seeds_pass": len(rows) == len(SEEDS) and all(row["passes"] for row in rows),
        "max_first_stage_clip_rate": max((row["first_stage_clip_rate"] for row in rows), default=None),
        "max_second_stage_clip_rate": max((row["second_stage_clip_rate"] for row in rows), default=None),
        "min_median_n_eff": min((row["median_n_eff"] for row in rows), default=None),
        "rows": rows, "unavailable_seeds": unavailable,
    }
    dump_json(summary, evidence / "VALIDATION_RECOMPUTE_SUMMARY.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
