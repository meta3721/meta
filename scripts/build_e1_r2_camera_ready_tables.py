#!/usr/bin/env python3
"""Build camera-ready IEEE LaTeX/CSV tables for E1-R2."""
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
    "twostage_hajek": "TwoStage-Hajek",
}
BASELINE_SHORT = {
    "raven_vs_fedavg_window": "FedAvg",
    "raven_vs_fedasync_window": "FedAsync",
    "raven_vs_flamf_timealign_adapted": "TimeAlign",
    "raven_vs_twostage_hajek": "TwoStage-Hajek",
}
METHOD_ORDER = list(METHOD_LABELS.keys())


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _stats_dir(root: Path) -> Path:
    for candidate in (
        root / "outputs/statistics/E1_R2_FINAL_SEALED",
        root / "outputs/statistics/E1_R2_SEALED",
    ):
        if (candidate / "no_harm_summary.json").is_file():
            return candidate
    return root / "outputs/statistics/E1_R2_FINAL_SEALED"


def _sci(value: float) -> str:
    if value == 0:
        return "0"
    text = f"{value:.2e}"
    mantissa, exp = text.split("e")
    exp_i = int(exp)
    return f"{mantissa}\\times10^{{{exp_i}}}"


def _mark(values: list[float]) -> list[str]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    marks = [""] * len(values)
    if order:
        marks[order[0]] = "best"
    if len(order) > 1:
        marks[order[1]] = "second"
    return marks


def _cell(text: str, mark: str) -> str:
    if mark == "best":
        return f"\\textbf{{{text}}}"
    if mark == "second":
        return f"\\underline{{{text}}}"
    return text


def _write_tex(path: Path, frame: pd.DataFrame, caption: str, label: str) -> None:
    cols = "l" + "c" * (len(frame.columns) - 1)
    header = " & ".join(str(c) for c in frame.columns) + " \\\\"
    rows = [" & ".join(str(v) for v in row) + " \\\\" for row in frame.itertuples(index=False)]
    path.write_text(
        "\\begin{table}[t]\n\\centering\n"
        f"\\caption{{{caption}}}\n\\label{{{label}}}\n"
        f"\\begin{{tabular}}{{{cols}}}\n\\hline\n{header}\n\\hline\n"
        + "\n".join(rows)
        + "\n\\hline\n\\end{tabular}\n\\end{table}\n",
        encoding="utf-8",
    )


def build_tables(root: Path, output_root: Path | None = None) -> dict[str, Any]:
    root = Path(root)
    out_dir = Path(output_root) if output_root else root / "outputs/paper/E1_R2_CAMERA_READY/tables"
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    aggregate = pd.read_parquet(root / "outputs/aggregate/E1_R2/per_seed_metrics.parquet")
    recompute = _json(root / "outputs/audits/E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json")
    safety = pd.read_csv(root / "outputs/audits/E1_R2_FORMAL_SAFETY_SUMMARY.csv")
    solver = pd.read_csv(root / "outputs/audits/E1_R2_RAVEN_SOLVER_SUMMARY.csv")
    stats = _stats_dir(root)
    holm = pd.read_csv(stats / "holm_results.csv")
    wilcoxon = pd.read_csv(stats / "wilcoxon_results.csv")
    summary = {row["method"]: row for row in recompute["method_summary"]}

    metrics = ["RMSE_mu", "RMSE_rho", "Gap_mis", "Tail_RMSE", "runtime"]
    means = {
        m: [float(summary[method].get(f"{m}_mean", aggregate.loc[aggregate.method == method, m].mean()))
            for method in METHOD_ORDER]
        for m in metrics
    }
    stds = {
        m: [float(summary[method].get(f"{m}_std", aggregate.loc[aggregate.method == method, m].std()))
            for method in METHOD_ORDER]
        for m in metrics
    }
    marks = {m: _mark(means[m]) for m in metrics}

    main_csv_rows = []
    main_tex_rows = []
    for i, method in enumerate(METHOD_ORDER):
        main_csv_rows.append({
            "Method": METHOD_LABELS[method],
            "RMSE_mu": f"{means['RMSE_mu'][i]:.4f} ± {stds['RMSE_mu'][i]:.4f}",
            "RMSE_rho": f"{means['RMSE_rho'][i]:.4f} ± {stds['RMSE_rho'][i]:.4f}",
            "Gap_mis": f"{means['Gap_mis'][i]:.4f} ± {stds['Gap_mis'][i]:.4f}",
            "Tail RMSE": f"{means['Tail_RMSE'][i]:.4f} ± {stds['Tail_RMSE'][i]:.4f}",
            "Runtime (s)": f"{means['runtime'][i]:.1f} ± {stds['runtime'][i]:.1f}",
        })
        main_tex_rows.append({
            "Method": METHOD_LABELS[method],
            "RMSE$_\\mu$": _cell(f"{means['RMSE_mu'][i]:.4f}$\\pm${stds['RMSE_mu'][i]:.4f}", marks["RMSE_mu"][i]),
            "RMSE$_\\rho$": _cell(f"{means['RMSE_rho'][i]:.4f}$\\pm${stds['RMSE_rho'][i]:.4f}", marks["RMSE_rho"][i]),
            "Gap$_{\\mathrm{mis}}$": _cell(f"{means['Gap_mis'][i]:.4f}$\\pm${stds['Gap_mis'][i]:.4f}", marks["Gap_mis"][i]),
            "Tail RMSE": _cell(f"{means['Tail_RMSE'][i]:.4f}$\\pm${stds['Tail_RMSE'][i]:.4f}", marks["Tail_RMSE"][i]),
            "Runtime (s)": _cell(f"{means['runtime'][i]:.1f}$\\pm${stds['runtime'][i]:.1f}", marks["runtime"][i]),
        })
    main_csv = pd.DataFrame(main_csv_rows)
    main_tex = pd.DataFrame(main_tex_rows)
    main_csv.to_csv(out_dir / "table_e1_main_metrics.csv", index=False)
    _write_tex(out_dir / "table_e1_main_metrics.tex", main_tex,
               "E1-R2 main metrics (mean$\\pm$SD, n=5). Best bold; second underlined.",
               "tab:e1-main")

    safety_g = safety.groupby("method", as_index=False).agg({
        "c_clip_obs": "max",
        "second_stage_clip_rate": "max",
        "median_n_eff": "min",
        "solver_failure_count": "sum",
    })
    safety_g["method"] = safety_g["method"].map(METHOD_LABELS)
    safety_table = pd.DataFrame({
        "Method": safety_g["method"],
        "Max Clip_obs (%)": (safety_g["c_clip_obs"] * 100).round(3),
        "Max Stage-2 Clip (%)": (safety_g["second_stage_clip_rate"] * 100).round(3),
        "Median ESS": safety_g["median_n_eff"].round(2),
        "Solver Failures": safety_g["solver_failure_count"].astype(int),
    })
    safety_table.to_csv(out_dir / "table_e1_safety.csv", index=False)
    _write_tex(out_dir / "table_e1_safety.tex", safety_table,
               "Safety summary by method.", "tab:e1-safety")

    wh = wilcoxon.merge(
        holm[["comparison", "metric", "holm_adjusted_p", "holm_significant"]],
        on=["comparison", "metric"], how="left",
    )
    wh = wh[wh["metric"] == "RMSE_mu"].copy()
    holm_table = pd.DataFrame({
        "Baseline": wh["comparison"].map(BASELINE_SHORT),
        "Wilcoxon p": wh["p_value"].map(lambda x: f"{x:.4f}"),
        "Holm-adjusted p": wh["holm_adjusted_p"].map(lambda x: f"{x:.4f}"),
        "Significant": wh["holm_significant"].map(lambda x: "No" if not x else "Yes"),
    })
    holm_table.to_csv(out_dir / "table_e1_wilcoxon_holm.csv", index=False)
    _write_tex(out_dir / "table_e1_wilcoxon_holm.tex", holm_table,
               "RMSE$_\\mu$ Wilcoxon and metric-wise Holm results.", "tab:e1-holm")

    solver_table = pd.DataFrame({
        "Seed": solver["seed"],
        "Fallback": solver["fallback_invoked_count"],
        "Complete failures": solver["complete_solver_failure_count"],
        "Max simplex residual": solver["max_simplex_residual"].map(lambda x: f"{x:.2e}"),
        "Max ESS L2": solver["max_ess_l2_violation"].map(lambda x: f"{x:.2e}"),
    })
    solver_tex = solver_table.copy()
    solver_tex["Max simplex residual"] = solver["max_simplex_residual"].map(_sci)
    solver_tex["Max ESS L2"] = solver["max_ess_l2_violation"].map(_sci)
    solver_table.to_csv(out_dir / "table_e1_solver_fallback.csv", index=False)
    _write_tex(out_dir / "table_e1_solver_fallback.tex", solver_tex,
               "RAVEN solver fallback and residuals by seed.", "tab:e1-solver")

    # Keep names expected by seal gates.
    for stem in ("table_e1_per_seed_rmse_mu", "table_e1_no_harm", "table_e1_runtime_updates"):
        # Lightweight companions for gate compatibility.
        pass
    per_seed = aggregate.pivot(index="seed", columns="method", values="RMSE_mu")[METHOD_ORDER]
    per_seed = per_seed.rename(columns=METHOD_LABELS).reset_index()
    per_seed.to_csv(out_dir / "table_e1_per_seed_rmse_mu.csv", index=False)
    _write_tex(out_dir / "table_e1_per_seed_rmse_mu.tex", per_seed.round(4),
               "Per-seed RMSE$_\\mu$.", "tab:e1-per-seed")

    no_harm = _json(stats / "no_harm_summary.json")["no_harm_tests"]["raven"]
    nh = pd.DataFrame([{
        "Baseline": "TimeAlign",
        "Candidate": "RAVEN",
        "Mean rel. deg. (%)": round(float(no_harm["relative_degradation_mean"]) * 100, 5),
        "One-sided 95% UB (%)": round(float(no_harm["one_sided_upper_bound"]) * 100, 5),
        "Threshold (%)": 3.0,
        "Pass": bool(no_harm["no_harm_pass"]),
    }])
    nh.to_csv(out_dir / "table_e1_no_harm.csv", index=False)
    _write_tex(out_dir / "table_e1_no_harm.tex", nh, "No-harm test versus TimeAlign.", "tab:e1-noharm")

    runtime = aggregate.groupby("method", as_index=False).agg(runtime=("runtime", "mean"),
                                                             communication=("communication", "mean"))
    runtime["method"] = runtime["method"].map(METHOD_LABELS)
    runtime = runtime.rename(columns={"method": "Method", "runtime": "Runtime (s)",
                                      "communication": "Communication updates"})
    runtime.to_csv(out_dir / "table_e1_runtime_updates.csv", index=False)
    _write_tex(out_dir / "table_e1_runtime_updates.tex", runtime.round(2),
               "Runtime and communication updates.", "tab:e1-runtime")

    return {"status": "PASS", "tables_dir": out_dir.as_posix(), "table_count": 7}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--camera-ready", action="store_true")
    args = parser.parse_args(argv)
    result = build_tables(args.root, args.output_root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
