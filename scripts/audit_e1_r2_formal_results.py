#!/usr/bin/env python3
"""Independently recompute E1-R2 formal results from immutable run artifacts."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

FORMAL_METHODS = (
    "fedavg_window",
    "fedasync_window",
    "flamf_timealign_adapted",
    "twostage_hajek",
    "raven",
)
FORMAL_SEEDS = (28001, 28002, 28003, 28004, 28005)
BASELINES = (
    "fedavg_window",
    "fedasync_window",
    "flamf_timealign_adapted",
    "twostage_hajek",
)
METHOD_LABELS = {
    "flamf_timealign_adapted": "FLAMF-TimeAlign-Adapted",
    "raven": "RAVEN",
    "fedavg_window": "FedAvg-Window",
    "fedasync_window": "FedAsync-Window",
    "twostage_hajek": "TwoStage-Hajek",
}
SUMMARY_METRICS = (
    "RMSE_mu",
    "RMSE_rho",
    "Gap_mis",
    "Head_RMSE",
    "Tail_RMSE",
    "runtime",
    "communication",
    "c_clip_obs",
    "median_n_eff",
)
# Audit-only reference means; never used as computed results.
AUDIT_EXPECTED_RMSE_MU_MEAN = {
    "flamf_timealign_adapted": 7.710763,
    "raven": 7.715395,
    "fedavg_window": 7.722020,
    "fedasync_window": 7.722198,
    "twostage_hajek": 7.726166,
}
AUDIT_EXPECTED_CLIP_BY_SEED = {
    28001: 0.041726,
    28002: 0.044747,
    28003: 0.043457,
    28004: 0.040170,
    28005: 0.044791,
}
AUDIT_TOLERANCE = 1e-4


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_from_run_json(run_root: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for manifest_path in sorted(run_root.glob("*/manifest.json")):
        run_dir = manifest_path.parent
        metrics_path = run_dir / "metrics_run.json"
        if not metrics_path.is_file():
            continue
        metrics = _load_json(metrics_path)
        manifest = _load_json(manifest_path)
        if not manifest.get("formal"):
            continue
        rows.append({
            "seed": int(metrics["seed"]),
            "method": metrics["method"],
            "RMSE_mu": float(metrics["RMSE_mu"]),
            "RMSE_rho": float(metrics["RMSE_rho"]),
            "Gap_mis": float(metrics["Gap_mis"]),
            "Head_RMSE": float(metrics["Head_RMSE"]),
            "Tail_RMSE": float(metrics["Tail_RMSE"]),
            "runtime": float(metrics["total_runtime"]),
            "communication": int(metrics["total_communication"]),
            "c_clip_obs": float(metrics.get("c_clip_obs", metrics.get(
                "first_stage_clip_observed_micro_true_exceed", np.nan
            ))),
            "first_stage_clip_rate_legacy_macro": float(
                metrics.get("first_stage_clip_rate_legacy_macro",
                             metrics.get("first_stage_clip_rate", np.nan))
            ),
            "second_stage_clip_rate": float(metrics["second_stage_clip_rate"]),
            "median_n_eff": float(metrics["median_n_eff"]),
            "min_n_eff": float(metrics.get("min_n_eff", metrics["median_n_eff"])),
            "q_nonattempt_leakage_count": int(metrics.get("q_nonattempt_leakage_count", 0)),
            "q_failed_attempt_omission_count": int(
                metrics.get("q_failed_attempt_omission_count", 0)
            ),
            "unsupported_arrival_contribution_count": int(
                metrics.get("unsupported_arrival_contribution_count", 0)
            ),
            "solver_failure_count": int(metrics.get("solver_failure_count", 0)),
            "run_id": manifest.get("run_id"),
            "run_dir": run_dir.as_posix(),
            "source": "metrics_run.json",
        })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["seed", "method"]).reset_index(drop=True)


def load_from_parquet(aggregate_root: Path) -> pd.DataFrame:
    path = aggregate_root / "per_seed_metrics.parquet"
    if not path.is_file():
        return pd.DataFrame()
    frame = pd.read_parquet(path)
    frame = frame.copy()
    frame["source"] = "per_seed_metrics.parquet"
    if "c_clip_obs" not in frame.columns:
        frame["c_clip_obs"] = frame.get(
            "first_stage_clip_observed_micro_true_exceed", np.nan
        )
    return frame.sort_values(["seed", "method"]).reset_index(drop=True)


def _method_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for method in FORMAL_METHODS:
        part = frame[frame["method"] == method]
        if part.empty:
            continue
        row: dict[str, Any] = {"method": method, "label": METHOD_LABELS[method], "n_seeds": len(part)}
        for metric in SUMMARY_METRICS:
            if metric not in part.columns:
                continue
            values = part[metric].astype(float)
            row[f"{metric}_mean"] = float(values.mean())
            row[f"{metric}_std"] = float(values.std(ddof=1)) if len(values) > 1 else 0.0
            row[f"{metric}_median"] = float(values.median())
        rows.append(row)
    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary
    summary["RMSE_mu_rank"] = summary["RMSE_mu_mean"].rank(method="min").astype(int)
    return summary.sort_values("RMSE_mu_mean").reset_index(drop=True)


def _relative_vs_baselines(frame: pd.DataFrame) -> pd.DataFrame:
    raven = frame[frame["method"] == "raven"].set_index("seed")
    rows: list[dict[str, Any]] = []
    for baseline in BASELINES:
        base = frame[frame["method"] == baseline].set_index("seed")
        common = sorted(set(raven.index) & set(base.index))
        for seed in common:
            rel = (
                float(raven.at[seed, "RMSE_mu"]) - float(base.at[seed, "RMSE_mu"])
            ) / float(base.at[seed, "RMSE_mu"])
            rows.append({
                "seed": int(seed),
                "baseline": baseline,
                "baseline_label": METHOD_LABELS[baseline],
                "raven_rmse_mu": float(raven.at[seed, "RMSE_mu"]),
                "baseline_rmse_mu": float(base.at[seed, "RMSE_mu"]),
                "relative_pct": rel * 100.0,
            })
        if common:
            rel_mean = float(np.mean([row["relative_pct"] for row in rows if row["baseline"] == baseline]))
            rows.append({
                "seed": "mean",
                "baseline": baseline,
                "baseline_label": METHOD_LABELS[baseline],
                "raven_rmse_mu": float(raven.loc[common, "RMSE_mu"].mean()),
                "baseline_rmse_mu": float(base.loc[common, "RMSE_mu"].mean()),
                "relative_pct": rel_mean,
            })
    return pd.DataFrame(rows)


def _reconcile_sources(
    parquet_frame: pd.DataFrame,
    json_frame: pd.DataFrame,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if parquet_frame.empty or json_frame.empty:
        return {"status": "INCOMPLETE", "checks": checks}
    for metric in ("RMSE_mu", "RMSE_rho", "Gap_mis", "Head_RMSE", "Tail_RMSE"):
        merged = parquet_frame.merge(
            json_frame,
            on=["seed", "method"],
            suffixes=("_parquet", "_json"),
            how="inner",
        )
        if merged.empty:
            checks.append({"metric": metric, "status": "NO_OVERLAP"})
            continue
        left = merged[f"{metric}_parquet"].astype(float)
        right = merged[f"{metric}_json"].astype(float)
        max_abs = float((left - right).abs().max())
        checks.append({
            "metric": metric,
            "max_abs_diff": max_abs,
            "status": "PASS" if max_abs <= 1e-10 else "FAIL",
        })
    status = "PASS" if checks and all(item["status"] == "PASS" for item in checks) else "FAIL"
    return {"status": status, "checks": checks}


def _audit_expected_means(summary: pd.DataFrame) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for method, expected in AUDIT_EXPECTED_RMSE_MU_MEAN.items():
        row = summary.loc[summary["method"] == method]
        if row.empty:
            audits.append({"method": method, "status": "MISSING"})
            continue
        observed = float(row.iloc[0]["RMSE_mu_mean"])
        diff = abs(observed - expected)
        audits.append({
            "method": method,
            "expected_rmse_mu_mean": expected,
            "observed_rmse_mu_mean": observed,
            "abs_diff": diff,
            "status": "PASS" if diff <= AUDIT_TOLERANCE else "REVIEW",
        })
    return audits


def _safety_summary(json_frame: pd.DataFrame) -> pd.DataFrame:
    if json_frame.empty:
        return pd.DataFrame()
    columns = [
        "seed", "method", "c_clip_obs", "first_stage_clip_rate_legacy_macro",
        "second_stage_clip_rate", "median_n_eff", "min_n_eff",
        "q_nonattempt_leakage_count", "q_failed_attempt_omission_count",
        "unsupported_arrival_contribution_count", "solver_failure_count",
    ]
    present = [column for column in columns if column in json_frame.columns]
    return json_frame[present].sort_values(["seed", "method"]).reset_index(drop=True)


def _semantic_audit(json_frame: pd.DataFrame, safety: pd.DataFrame) -> dict[str, Any]:
    nan_inf = 0
    for column in SUMMARY_METRICS:
        if column in json_frame.columns:
            values = json_frame[column].astype(float)
            nan_inf += int((~np.isfinite(values)).sum())
    clip_audit = []
    for seed, expected in AUDIT_EXPECTED_CLIP_BY_SEED.items():
        rows = safety.loc[(safety["seed"] == seed) & (safety["method"] == "raven")]
        if rows.empty:
            clip_audit.append({"seed": seed, "status": "MISSING"})
            continue
        observed = float(rows.iloc[0]["c_clip_obs"])
        clip_audit.append({
            "seed": seed,
            "expected_c_clip_obs": expected,
            "observed_c_clip_obs": observed,
            "abs_diff": abs(observed - expected),
            "status": "PASS" if abs(observed - expected) <= AUDIT_TOLERANCE else "REVIEW",
        })
    gates = {
        "max_observed_micro_clip_lt_0_05": bool(
            safety["c_clip_obs"].astype(float).max() < 0.05
        ) if not safety.empty else False,
        "max_second_stage_clip_lt_0_05": bool(
            safety["second_stage_clip_rate"].astype(float).max() < 0.05
        ) if not safety.empty else False,
        "min_median_n_eff_gte_2": bool(
            safety["median_n_eff"].astype(float).min() >= 2.0
        ) if not safety.empty else False,
        "total_q_leakage_eq_0": int(safety["q_nonattempt_leakage_count"].sum()) == 0
        if not safety.empty else False,
        "total_failed_attempt_omission_eq_0": int(
            safety["q_failed_attempt_omission_count"].sum()
        ) == 0 if not safety.empty else False,
        "total_unsupported_arrival_eq_0": int(
            safety["unsupported_arrival_contribution_count"].sum()
        ) == 0 if not safety.empty else False,
        "total_solver_failure_eq_0": int(safety["solver_failure_count"].sum()) == 0
        if not safety.empty else False,
        "total_nan_inf_eq_0": nan_inf == 0,
    }
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_count": int(len(json_frame)),
        "formal_seeds": list(FORMAL_SEEDS),
        "methods": list(FORMAL_METHODS),
        "clip_audit_by_seed": clip_audit,
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "nan_inf_count": nan_inf,
    }


def _write_reconciliation_md(
    path: Path,
    *,
    summary: pd.DataFrame,
    relative: pd.DataFrame,
    source_reconcile: dict[str, Any],
    audit_means: list[dict[str, Any]],
) -> None:
    lines = [
        "# E1-R2 Formal Results Independent Reconciliation",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Method Summary (RMSE_mu rank ascending = better)",
        "",
        summary.to_string(index=False),
        "",
        "## RAVEN Relative % vs Baselines (negative = RAVEN lower RMSE)",
        "",
        relative.to_string(index=False),
        "",
        "## Source Reconciliation (parquet vs metrics_run.json)",
        "",
        f"Status: **{source_reconcile.get('status', 'UNKNOWN')}**",
        "",
    ]
    for check in source_reconcile.get("checks", []):
        lines.append(f"- {check}")
    lines.extend(["", "## Audit Expected Means (reference only)", ""])
    for item in audit_means:
        lines.append(f"- {item}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def audit(
    run_root: Path,
    aggregate_root: Path,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    run_root = Path(run_root).resolve()
    aggregate_root = Path(aggregate_root).resolve()
    root = Path(root).resolve()
    audits = root / "outputs/audits"
    audits.mkdir(parents=True, exist_ok=True)

    parquet_frame = load_from_parquet(aggregate_root)
    json_frame = load_from_run_json(run_root)
    primary = parquet_frame if not parquet_frame.empty else json_frame
    if primary.empty:
        raise FileNotFoundError(
            f"no formal metrics under {aggregate_root} or {run_root}"
        )

    summary = _method_summary(primary)
    relative = _relative_vs_baselines(primary)
    source_reconcile = _reconcile_sources(parquet_frame, json_frame)
    audit_means = _audit_expected_means(summary)
    safety = _safety_summary(json_frame if not json_frame.empty else primary)
    semantic = _semantic_audit(json_frame if not json_frame.empty else primary, safety)

    per_seed = primary[
        ["seed", "method"] + [column for column in SUMMARY_METRICS if column in primary.columns]
    ].copy()

    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_root": (
            run_root.relative_to(root).as_posix()
            if run_root.is_relative_to(root)
            else run_root.as_posix()
        ),
        "aggregate_root": (
            aggregate_root.relative_to(root).as_posix()
            if aggregate_root.is_relative_to(root)
            else aggregate_root.as_posix()
        ),
        "primary_source": "per_seed_metrics.parquet" if not parquet_frame.empty else "metrics_run.json",
        "run_count": int(len(primary)),
        "method_summary": summary.to_dict(orient="records"),
        "raven_relative_vs_baselines": relative.to_dict(orient="records"),
        "source_reconciliation": source_reconcile,
        "audit_expected_rmse_mu_means": audit_means,
        "per_seed_metrics": per_seed.to_dict(orient="records"),
        "semantic_audit": semantic,
    }

    recompute_json = audits / "E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json"
    recompute_csv = audits / "E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.csv"
    reconcile_md = audits / "E1_R2_FORMAL_RESULTS_RECONCILIATION.md"
    safety_csv = audits / "E1_R2_FORMAL_SAFETY_SUMMARY.csv"
    semantic_json = audits / "E1_R2_FORMAL_SEMANTIC_AUDIT.json"

    recompute_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    summary.to_csv(recompute_csv, index=False)
    _write_reconciliation_md(
        reconcile_md,
        summary=summary,
        relative=relative,
        source_reconcile=source_reconcile,
        audit_means=audit_means,
    )
    safety.to_csv(safety_csv, index=False)
    semantic_json.write_text(
        json.dumps(semantic, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )

    print(json.dumps({
        "status": "PASS" if semantic["all_gates_pass"] else "FAIL",
        "recompute_json": recompute_json.as_posix(),
        "safety_csv": safety_csv.as_posix(),
        "semantic_json": semantic_json.as_posix(),
    }, indent=2))
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, default=ROOT / "outputs/runs/E1_R2")
    parser.add_argument("--aggregate-root", type=Path, default=ROOT / "outputs/aggregate/E1_R2")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    audit(args.run_root, args.aggregate_root, root=args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
