#!/usr/bin/env python3
"""Build E1-R2 IEEE-style paper tables from sealed formal audit artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

METHOD_LABELS = {
    "flamf_timealign_adapted": "TimeAlign",
    "raven": "RAVEN",
    "fedavg_window": "FedAvg",
    "fedasync_window": "FedAsync",
    "twostage_hajek": "TwoStage",
}
METHOD_ORDER = [
    "flamf_timealign_adapted",
    "raven",
    "fedavg_window",
    "fedasync_window",
    "twostage_hajek",
]


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _stats_dir(root: Path) -> Path:
    for candidate in (
        root / "outputs/statistics/E1_R2_FINAL_SEALED",
        root / "outputs/statistics/E1_R2_SEALED",
        root / "outputs/statistics/E1_R2",
    ):
        if (candidate / "no_harm_summary.json").is_file():
            return candidate
    return root / "outputs/statistics/E1_R2_FINAL_SEALED"


def _fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def _mark_best_second(values: list[float], *, lower_is_better: bool = True) -> list[str]:
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=not lower_is_better)
    marks = [""] * len(values)
    if order:
        marks[order[0]] = "best"
    if len(order) > 1:
        marks[order[1]] = "second"
    return marks


def _cell(value: str, mark: str) -> str:
    if mark == "best":
        return f"\\textbf{{{value}}}"
    if mark == "second":
        return f"\\underline{{{value}}}"
    return value


def _dataframe_to_latex(frame: pd.DataFrame, caption: str, label: str) -> str:
    columns = "l" + "c" * (len(frame.columns) - 1)
    header = " & ".join(str(col) for col in frame.columns) + " \\\\"
    rows = []
    for row in frame.itertuples(index=False):
        rows.append(" & ".join(str(value) for value in row) + " \\\\")
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


def build_tables(root: Path, output_root: Path | None = None) -> dict[str, Any]:
    root = Path(root)
    out_dir = Path(output_root) if output_root else root / "outputs/paper/E1_R2_FINAL/tables"
    if not out_dir.is_absolute():
        out_dir = root / out_dir
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
    safety = pd.read_csv(root / "outputs/audits/E1_R2_FORMAL_SAFETY_SUMMARY.csv")
    solver = pd.read_csv(root / "outputs/audits/E1_R2_RAVEN_SOLVER_SUMMARY.csv")
    stats_dir = _stats_dir(root)
    no_harm = _json(stats_dir / "no_harm_summary.json")
    wilcoxon = pd.read_csv(stats_dir / "wilcoxon_results.csv")
    holm = pd.read_csv(stats_dir / "holm_results.csv")

    summary = {row["method"]: row for row in recompute.get("method_summary", [])}
    metrics = ["RMSE_mu", "RMSE_rho", "Gap_mis", "Tail_RMSE", "runtime"]
    means = {
        metric: [
            float(summary[method].get(f"{metric}_mean", aggregate.loc[
                aggregate["method"] == method, metric
            ].mean()))
            for method in METHOD_ORDER
        ]
        for metric in metrics
    }
    marks = {metric: _mark_best_second(values, lower_is_better=True) for metric, values in means.items()}
    main_rows = []
    for index, method in enumerate(METHOD_ORDER):
        main_rows.append({
            "Method": METHOD_LABELS[method],
            "RMSE_$\\mu$": _cell(_fmt(means["RMSE_mu"][index]), marks["RMSE_mu"][index]),
            "RMSE_$\\rho$": _cell(_fmt(means["RMSE_rho"][index]), marks["RMSE_rho"][index]),
            "Gap$_{\\mathrm{mis}}$": _cell(_fmt(means["Gap_mis"][index]), marks["Gap_mis"][index]),
            "Tail RMSE": _cell(_fmt(means["Tail_RMSE"][index]), marks["Tail_RMSE"][index]),
            "Runtime (s)": _cell(_fmt(means["runtime"][index], 1), marks["runtime"][index]),
        })
    main_metrics = pd.DataFrame(main_rows)
    # CSV uses plain symbols for readability outside LaTeX.
    main_csv = pd.DataFrame([
        {
            "Method": METHOD_LABELS[method],
            "RMSE_mu": means["RMSE_mu"][i],
            "RMSE_rho": means["RMSE_rho"][i],
            "Gap_mis": means["Gap_mis"][i],
            "Tail_RMSE": means["Tail_RMSE"][i],
            "Runtime": means["runtime"][i],
        }
        for i, method in enumerate(METHOD_ORDER)
    ])
    main_csv.to_csv(out_dir / "table_e1_main_metrics.csv", index=False)
    (out_dir / "table_e1_main_metrics.tex").write_text(
        _dataframe_to_latex(
            main_metrics,
            "E1-R2 main metrics (n=5). Best in bold; second underlined.",
            "tab:e1-main-metrics",
        ),
        encoding="utf-8",
    )

    per_seed = aggregate.pivot(index="seed", columns="method", values="RMSE_mu")
    per_seed = per_seed[METHOD_ORDER].rename(columns=METHOD_LABELS).reset_index()
    _write_pair(out_dir, "table_e1_per_seed_rmse_mu", per_seed,
                "Per-seed RMSE$_\\mu$.", "tab:e1-per-seed-rmse")

    safety_table = safety.groupby("method", as_index=False).agg({
        "c_clip_obs": "max",
        "second_stage_clip_rate": "max",
        "median_n_eff": "min",
        "solver_failure_count": "sum",
    })
    safety_table["method"] = safety_table["method"].map(METHOD_LABELS)
    safety_table = safety_table.rename(columns={
        "method": "Method",
        "c_clip_obs": "Clip_obs",
        "second_stage_clip_rate": "Stage-2 clip",
        "median_n_eff": "Median ESS",
        "solver_failure_count": "Solver failure",
    })
    _write_pair(out_dir, "table_e1_safety", safety_table,
                "Safety summary by method.", "tab:e1-safety")

    raven_nh = no_harm.get("no_harm_tests", {}).get("raven", {})
    no_harm_table = pd.DataFrame([{
        "Baseline": "TimeAlign",
        "Candidate": "RAVEN",
        "Mean relative degradation": raven_nh.get("relative_degradation_mean"),
        "One-sided 95% upper bound": raven_nh.get("one_sided_upper_bound"),
        "Threshold": no_harm.get("no_harm_threshold", 0.03),
        "No-harm pass": raven_nh.get("no_harm_pass"),
    }])
    _write_pair(out_dir, "table_e1_no_harm", no_harm_table,
                "RAVEN no-harm test versus TimeAlign.", "tab:e1-no-harm")

    holm_cols = ["comparison", "metric", "holm_adjusted_p", "holm_significant"]
    if "family_id" in holm.columns:
        holm_cols = ["comparison", "metric", "family_id", "family_size",
                     "holm_adjusted_p", "holm_significant"]
    wh = wilcoxon.merge(holm[holm_cols], on=["comparison", "metric"], how="left")
    wh_rmse = wh[wh["metric"] == "RMSE_mu"].copy()
    wh_rmse = wh_rmse.rename(columns={
        "comparison": "Comparison",
        "p_value": "Wilcoxon p",
        "holm_adjusted_p": "Holm-adjusted p",
        "holm_significant": "Significant",
    })
    stats_table = wh_rmse[["Comparison", "Wilcoxon p", "Holm-adjusted p", "Significant"]]
    _write_pair(out_dir, "table_e1_wilcoxon_holm", stats_table,
                "RMSE$_\\mu$ Wilcoxon and metric-wise Holm results.", "tab:e1-wilcoxon-holm")
    _write_pair(out_dir, "table_e1_wilcoxon_holm_all", wh,
                "All Wilcoxon and metric-wise Holm results.", "tab:e1-wilcoxon-holm-all")

    solver_table = solver[["seed", "fallback_invoked_count", "complete_solver_failure_count",
                           "max_simplex_residual", "max_ess_l2_violation"]].rename(columns={
        "seed": "Seed",
        "fallback_invoked_count": "Fallback count",
        "complete_solver_failure_count": "Complete failures",
        "max_simplex_residual": "Max simplex residual",
        "max_ess_l2_violation": "Max ESS L2 violation",
    })
    _write_pair(out_dir, "table_e1_solver_fallback", solver_table,
                "RAVEN solver fallback by seed.", "tab:e1-solver-fallback")

    runtime_table = aggregate.groupby("method", as_index=False).agg({
        "runtime": "mean",
        "communication": "mean",
    })
    runtime_table["method"] = runtime_table["method"].map(METHOD_LABELS)
    runtime_table = runtime_table.rename(columns={
        "method": "Method",
        "runtime": "Runtime (s)",
        "communication": "Communication updates",
    })
    _write_pair(out_dir, "table_e1_runtime_updates", runtime_table,
                "Runtime and communication updates (not bytes).", "tab:e1-runtime-updates")

    return {"status": "PASS", "tables_dir": out_dir.as_posix(), "table_count": 8}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args(argv)
    result = build_tables(args.root, args.output_root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
