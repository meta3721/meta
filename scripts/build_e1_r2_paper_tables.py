#!/usr/bin/env python3
"""Build E1-R2 paper tables from sealed formal audit artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

METHOD_LABELS = {
    "flamf_timealign_adapted": "FLAMF-TimeAlign-Adapted",
    "raven": "RAVEN",
    "fedavg_window": "FedAvg-Window",
    "fedasync_window": "FedAsync-Window",
    "twostage_hajek": "TwoStage-Hajek",
}


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _latex_escape(value: str) -> str:
    return (
        value.replace("\\", "\\textbackslash{}")
        .replace("_", "\\_")
        .replace("%", "\\%")
    )


def _dataframe_to_latex(frame: pd.DataFrame, caption: str, label: str) -> str:
    columns = "l" + "r" * (len(frame.columns) - 1)
    header = " & ".join(_latex_escape(str(col)) for col in frame.columns) + " \\\\"
    rows = []
    for row in frame.itertuples(index=False):
        rows.append(" & ".join(_latex_escape(f"{value:.6g}" if isinstance(value, float) else str(value))
                                for value in row) + " \\\\")
    body = "\n".join(rows)
    return (
        "\\begin{table}[t]\n"
        "\\centering\n"
        "\\caption{" + caption + "}\n"
        "\\label{" + label + "}\n"
        "\\begin{tabular}{" + columns + "}\n"
        "\\hline\n"
        f"{header}\n\\hline\n"
        f"{body}\n"
        "\\hline\n"
        "\\end{tabular}\n"
        "\\end{table}\n"
    )


def _write_pair(out_dir: Path, stem: str, frame: pd.DataFrame, caption: str, label: str) -> None:
    frame.to_csv(out_dir / f"{stem}.csv", index=False)
    (out_dir / f"{stem}.tex").write_text(
        _dataframe_to_latex(frame, caption, label), encoding="utf-8",
    )


def build_tables(root: Path) -> dict[str, Any]:
    root = Path(root)
    out_dir = root / "outputs/paper/E1_R2/tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    aggregate = pd.read_parquet(root / "outputs/aggregate/E1_R2/per_seed_metrics.parquet")
    recompute_path = root / "outputs/audits/E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json"
    if not recompute_path.is_file():
        from audit_e1_r2_formal_results import audit as audit_results
        audit_results(
            root / "outputs/runs/E1_R2",
            root / "outputs/aggregate/E1_R2",
            root=root,
        )
    recompute = _json(recompute_path)
    safety_path = root / "outputs/audits/E1_R2_FORMAL_SAFETY_SUMMARY.csv"
    if not safety_path.is_file():
        from audit_e1_r2_formal_results import audit as audit_results
        audit_results(
            root / "outputs/runs/E1_R2",
            root / "outputs/aggregate/E1_R2",
            root=root,
        )
    safety = pd.read_csv(safety_path)
    solver_path = root / "outputs/audits/E1_R2_RAVEN_SOLVER_SUMMARY.csv"
    if not solver_path.is_file():
        from audit_e1_r2_solver_fallback import audit as audit_solver
        audit_solver(root / "outputs/runs/E1_R2", root=root)
    solver = pd.read_csv(solver_path)

    stats_dir = root / "outputs/statistics/E1_R2_SEALED"
    if not stats_dir.is_dir():
        stats_dir = root / "outputs/statistics/E1_R2"
    no_harm = _json(stats_dir / "no_harm_summary.json")
    wilcoxon = pd.read_csv(stats_dir / "wilcoxon_results.csv")
    holm = pd.read_csv(stats_dir / "holm_results.csv")

    summary_rows = []
    for row in recompute.get("method_summary", []):
        summary_rows.append({
            "Method": METHOD_LABELS.get(row["method"], row["method"]),
            "RMSE_mu_mean": row["RMSE_mu_mean"],
            "RMSE_mu_std": row["RMSE_mu_std"],
            "RMSE_rho_mean": row.get("RMSE_rho_mean"),
            "Gap_mis_mean": row.get("Gap_mis_mean"),
            "Head_RMSE_mean": row.get("Head_RMSE_mean"),
            "Tail_RMSE_mean": row.get("Tail_RMSE_mean"),
            "Rank": row.get("RMSE_mu_rank"),
        })
    main_metrics = pd.DataFrame(summary_rows).sort_values("Rank")

    per_seed = aggregate.pivot(index="seed", columns="method", values="RMSE_mu")
    per_seed.columns = [METHOD_LABELS.get(col, col) for col in per_seed.columns]
    per_seed = per_seed.reset_index()

    safety_table = safety.groupby("method", as_index=False).agg({
        "c_clip_obs": "max",
        "second_stage_clip_rate": "max",
        "median_n_eff": "min",
        "q_nonattempt_leakage_count": "sum",
        "solver_failure_count": "sum",
    })
    safety_table["method"] = safety_table["method"].map(METHOD_LABELS)

    raven_nh = no_harm.get("no_harm_tests", {}).get("raven", {})
    no_harm_table = pd.DataFrame([{
        "Baseline": "FLAMF-TimeAlign-Adapted",
        "Candidate": "RAVEN",
        "MeanRelativeDegradation": raven_nh.get("relative_degradation_mean"),
        "OneSidedUpperBound": raven_nh.get("one_sided_upper_bound"),
        "Threshold": no_harm.get("no_harm_threshold", 0.03),
        "NoHarmPass": raven_nh.get("no_harm_pass"),
    }])

    wh = wilcoxon.merge(
        holm[["comparison", "metric", "holm_adjusted_p", "holm_significant"]],
        on=["comparison", "metric"],
        how="left",
    )

    solver_table = solver[["seed", "fallback_invoked_count", "complete_solver_failure_count",
                           "max_simplex_residual", "max_ess_l2_violation"]]

    runtime_table = aggregate.groupby("method", as_index=False).agg({
        "runtime": "mean",
        "communication": "mean",
    })
    runtime_table["method"] = runtime_table["method"].map(METHOD_LABELS)
    runtime_table.rename(columns={
        "runtime": "runtime_sec_mean",
        "communication": "communication_updates_mean",
    }, inplace=True)

    _write_pair(out_dir, "table_e1_main_metrics", main_metrics,
                "E1-R2 formal main metrics (n=5 seeds).", "tab:e1-main-metrics")
    _write_pair(out_dir, "table_e1_per_seed_rmse_mu", per_seed,
                "Per-seed RMSE_mu.", "tab:e1-per-seed-rmse")
    _write_pair(out_dir, "table_e1_safety", safety_table,
                "Safety summary by method.", "tab:e1-safety")
    _write_pair(out_dir, "table_e1_no_harm", no_harm_table,
                "RAVEN no-harm test vs validation-selected baseline.", "tab:e1-no-harm")
    _write_pair(out_dir, "table_e1_wilcoxon_holm", wh,
                "Wilcoxon and Holm results.", "tab:e1-wilcoxon-holm")
    _write_pair(out_dir, "table_e1_solver_fallback", solver_table,
                "RAVEN solver fallback by seed.", "tab:e1-solver-fallback")
    _write_pair(out_dir, "table_e1_runtime_updates", runtime_table,
                "Runtime and communication updates.", "tab:e1-runtime-updates")

    return {"status": "PASS", "tables_dir": out_dir.as_posix(), "table_count": 7}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    result = build_tables(args.root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
