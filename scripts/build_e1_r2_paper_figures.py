#!/usr/bin/env python3
"""Build E1-R2 paper figures from formal audit artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

METHOD_LABELS = {
    "flamf_timealign_adapted": "FLAMF",
    "raven": "RAVEN",
    "fedavg_window": "FedAvg",
    "fedasync_window": "FedAsync",
    "twostage_hajek": "TwoStage",
}
METHOD_ORDER = list(METHOD_LABELS.keys())


def _save_figure(out_dir: Path, stem: str, frame: pd.DataFrame, plot_fn) -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    plot_fn(ax)
    ax.set_title(stem.replace("_", " "))
    fig.tight_layout()
    fig.savefig(out_dir / f"{stem}.pdf")
    fig.savefig(out_dir / f"{stem}.png", dpi=300)
    plt.close(fig)
    frame.to_csv(out_dir / f"{stem}_source_data.csv", index=False)


def build_figures(root: Path) -> dict[str, Any]:
    root = Path(root)
    out_dir = root / "outputs/paper/E1_R2/figures"
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
    recompute = json.loads(recompute_path.read_text(encoding="utf-8"))
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
    no_harm_path = stats_dir / "no_harm_per_seed.parquet"
    if no_harm_path.is_file():
        no_harm = pd.read_parquet(no_harm_path)
    else:
        baseline = aggregate[aggregate["method"] == "flamf_timealign_adapted"][["seed", "RMSE_mu"]]
        raven_rows = aggregate[aggregate["method"] == "raven"][["seed", "RMSE_mu"]]
        merged = baseline.merge(raven_rows, on="seed", suffixes=("_baseline", "_raven"))
        no_harm = merged.assign(
            degradation=(merged["RMSE_mu_raven"] - merged["RMSE_mu_baseline"])
            / merged["RMSE_mu_baseline"]
        )

    summary = pd.DataFrame(recompute["method_summary"])
    summary["label"] = summary["method"].map(METHOD_LABELS)
    summary = summary.set_index("method").loc[METHOD_ORDER].reset_index()

    rmse_source = summary[["label", "RMSE_mu_mean", "RMSE_mu_std"]].rename(columns={
        "label": "method",
        "RMSE_mu_mean": "mean",
        "RMSE_mu_std": "std",
    })

    def plot_rmse(ax):
        ax.bar(rmse_source["method"], rmse_source["mean"], yerr=rmse_source["std"], capsize=4)
        ax.set_ylabel("RMSE_mu (seed std error bars, n=5)")

    _save_figure(out_dir, "fig_e1_rmse_mu_by_method", rmse_source, plot_rmse)

    baseline = aggregate[aggregate["method"] == "flamf_timealign_adapted"][["seed", "RMSE_mu"]]
    raven = aggregate[aggregate["method"] == "raven"][["seed", "RMSE_mu"]]
    paired = baseline.merge(raven, on="seed", suffixes=("_baseline", "_raven"))

    def plot_paired(ax):
        ax.plot(paired["seed"], paired["RMSE_mu_baseline"], marker="o", label="FLAMF")
        ax.plot(paired["seed"], paired["RMSE_mu_raven"], marker="s", label="RAVEN")
        ax.set_xlabel("seed")
        ax.set_ylabel("RMSE_mu")
        ax.legend()

    _save_figure(out_dir, "fig_e1_per_seed_raven_vs_baseline", paired, plot_paired)

    deg_source = no_harm[["seed", "degradation"]].copy()
    deg_source["relative_pct"] = deg_source["degradation"] * 100.0

    def plot_deg(ax):
        ax.bar(deg_source["seed"].astype(str), deg_source["relative_pct"])
        ax.axhline(3.0, color="red", linestyle="--", label="3% threshold")
        ax.set_ylabel("Relative degradation (%)")
        ax.legend()

    _save_figure(out_dir, "fig_e1_relative_degradation", deg_source, plot_deg)

    clip_source = safety[safety["method"] == "raven"][["seed", "c_clip_obs"]]

    def plot_clip(ax):
        ax.bar(clip_source["seed"].astype(str), clip_source["c_clip_obs"])
        ax.axhline(0.05, color="red", linestyle="--")
        ax.set_ylabel("Observed-micro clip rate")

    _save_figure(out_dir, "fig_e1_clip_by_seed", clip_source, plot_clip)

    ess_source = aggregate.groupby("method", as_index=False)["median_n_eff"].mean()
    ess_source["label"] = ess_source["method"].map(METHOD_LABELS)

    def plot_ess(ax):
        ax.bar(ess_source["label"], ess_source["median_n_eff"])
        ax.set_ylabel("Mean median n_eff")

    _save_figure(out_dir, "fig_e1_ess_by_method", ess_source, plot_ess)

    runtime_source = aggregate.groupby("method", as_index=False)["runtime"].mean()
    runtime_source["label"] = runtime_source["method"].map(METHOD_LABELS)

    def plot_runtime(ax):
        ax.bar(runtime_source["label"], runtime_source["runtime"])
        ax.set_ylabel("Mean runtime (sec)")

    _save_figure(out_dir, "fig_e1_runtime_by_method", runtime_source, plot_runtime)

    def plot_fallback(ax):
        ax.bar(solver["seed"].astype(str), solver["fallback_invoked_count"])
        ax.set_ylabel("Fallback count")

    _save_figure(out_dir, "fig_e1_solver_fallback_by_seed", solver[["seed", "fallback_invoked_count"]], plot_fallback)

    residual_source = solver[[
        "seed", "max_simplex_residual", "max_nonnegativity_violation",
        "max_upper_bound_violation", "max_ess_l2_violation",
    ]]

    def plot_residuals(ax):
        width = 0.2
        x = range(len(residual_source))
        cols = [
            "max_simplex_residual", "max_nonnegativity_violation",
            "max_upper_bound_violation", "max_ess_l2_violation",
        ]
        for index, col in enumerate(cols):
            ax.bar([i + index * width for i in x], residual_source[col], width=width, label=col)
        ax.set_xticks([i + 1.5 * width for i in x])
        ax.set_xticklabels(residual_source["seed"].astype(str))
        ax.legend(fontsize=7)

    _save_figure(out_dir, "fig_e1_solver_residuals", residual_source, plot_residuals)

    gap_source = aggregate.groupby("method", as_index=False)["Gap_mis"].mean()
    gap_source["label"] = gap_source["method"].map(METHOD_LABELS)

    def plot_gap(ax):
        ax.bar(gap_source["label"], gap_source["Gap_mis"])
        ax.set_ylabel("Mean Gap_mis")

    _save_figure(out_dir, "fig_e1_gap_mis_by_method", gap_source, plot_gap)

    head_tail = aggregate.groupby("method", as_index=False).agg({
        "Head_RMSE": "mean",
        "Tail_RMSE": "mean",
    })
    head_tail["label"] = head_tail["method"].map(METHOD_LABELS)

    def plot_head_tail(ax):
        width = 0.35
        x = range(len(head_tail))
        ax.bar([i - width / 2 for i in x], head_tail["Head_RMSE"], width=width, label="Head")
        ax.bar([i + width / 2 for i in x], head_tail["Tail_RMSE"], width=width, label="Tail")
        ax.set_xticks(list(x))
        ax.set_xticklabels(head_tail["label"])
        ax.legend()

    _save_figure(out_dir, "fig_e1_head_tail_rmse", head_tail, plot_head_tail)

    return {"status": "PASS", "figures_dir": out_dir.as_posix(), "figure_count": 10}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    result = build_figures(args.root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
