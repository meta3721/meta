#!/usr/bin/env python3
"""Build E1-R2 publication-ready paper figures."""
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
    "flamf_timealign_adapted": "TimeAlign",
    "raven": "RAVEN",
    "fedavg_window": "FedAvg",
    "fedasync_window": "FedAsync",
    "twostage_hajek": "TwoStage",
}
METHOD_ORDER = list(METHOD_LABELS.keys())


def _stats_dir(root: Path) -> Path:
    for candidate in (
        root / "outputs/statistics/E1_R2_FINAL_SEALED",
        root / "outputs/statistics/E1_R2_SEALED",
        root / "outputs/statistics/E1_R2",
    ):
        if candidate.is_dir():
            return candidate
    return root / "outputs/statistics/E1_R2_FINAL_SEALED"


def _style(publication_ready: bool) -> None:
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 9 if publication_ready else 10,
        "axes.labelsize": 9 if publication_ready else 10,
        "axes.titlesize": 10 if publication_ready else 11,
        "legend.fontsize": 8,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "axes.grid": False,
    })


def _save_figure(out_dir: Path, stem: str, frame: pd.DataFrame, plot_fn, *, figsize=(3.5, 2.6)) -> None:
    fig, ax = plt.subplots(figsize=figsize)
    plot_fn(ax)
    fig.tight_layout()
    fig.savefig(out_dir / f"{stem}.pdf")
    fig.savefig(out_dir / f"{stem}.png", dpi=300)
    plt.close(fig)
    frame.to_csv(out_dir / f"{stem}_source_data.csv", index=False)


def build_figures(
    root: Path,
    output_root: Path | None = None,
    *,
    publication_ready: bool = False,
) -> dict[str, Any]:
    root = Path(root)
    out_dir = Path(output_root) if output_root else root / "outputs/paper/E1_R2_FINAL/figures"
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    _style(publication_ready)

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
    safety = pd.read_csv(root / "outputs/audits/E1_R2_FORMAL_SAFETY_SUMMARY.csv")
    solver_path = root / "outputs/audits/E1_R2_RAVEN_SOLVER_SUMMARY.csv"
    if not solver_path.is_file():
        from audit_e1_r2_solver_fallback import audit as audit_solver
        audit_solver(root / "outputs/runs/E1_R2", root=root)
    solver = pd.read_csv(solver_path)

    stats_dir = _stats_dir(root)
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
    colors = ["#1f4e79", "#c55a11", "#7f7f7f", "#7f7f7f", "#7f7f7f"]

    rmse_source = summary[["label", "RMSE_mu_mean", "RMSE_mu_std"]].rename(columns={
        "label": "method",
        "RMSE_mu_mean": "mean",
        "RMSE_mu_std": "std",
    })

    def plot_rmse(ax):
        bars = ax.bar(
            rmse_source["method"], rmse_source["mean"],
            yerr=rmse_source["std"], capsize=3, color=colors, edgecolor="black", linewidth=0.4,
        )
        ymin = float(rmse_source["mean"].min() - rmse_source["std"].max()) - 0.005
        ymax = float(rmse_source["mean"].max() + rmse_source["std"].max()) + 0.005
        ax.set_ylim(ymin, ymax)
        ax.set_ylabel(r"RMSE$_\mu$")
        ax.set_xlabel("")
        ax.text(0.02, 0.98, "n=5 seeds; error bars = seed SD",
                transform=ax.transAxes, va="top", fontsize=7)
        ax.text(0.98, 0.98, "1st: TimeAlign\n2nd: RAVEN",
                transform=ax.transAxes, va="top", ha="right", fontsize=7)
        for bar, label in zip(bars, ["1st", "2nd", "", "", ""]):
            if label:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), label,
                        ha="center", va="bottom", fontsize=7)

    _save_figure(out_dir, "fig_e1_rmse_mu_by_method", rmse_source, plot_rmse)

    baseline = aggregate[aggregate["method"] == "flamf_timealign_adapted"][["seed", "RMSE_mu"]]
    raven = aggregate[aggregate["method"] == "raven"][["seed", "RMSE_mu"]]
    paired = baseline.merge(raven, on="seed", suffixes=("_baseline", "_raven"))

    def plot_paired(ax):
        ax.plot(paired["seed"], paired["RMSE_mu_baseline"], marker="o", label="TimeAlign")
        ax.plot(paired["seed"], paired["RMSE_mu_raven"], marker="s", label="RAVEN")
        ax.set_xlabel("Seed")
        ax.set_ylabel(r"RMSE$_\mu$")
        ax.legend(frameon=False)

    _save_figure(out_dir, "fig_e1_per_seed_raven_vs_baseline", paired, plot_paired)

    deg_source = no_harm[["seed", "degradation"]].copy()
    deg_source["relative_pct"] = deg_source["degradation"] * 100.0

    def plot_deg(ax):
        ax.bar(deg_source["seed"].astype(str), deg_source["relative_pct"], color="#1f4e79")
        ax.axhline(0.0, color="black", linewidth=0.8)
        ax.set_ylim(-0.25, 0.25)
        ax.set_ylabel("Relative degradation (%)")
        ax.set_xlabel("Seed")
        ax.annotate(
            "3% no-harm threshold outside axis",
            xy=(0.98, 0.02), xycoords="axes fraction",
            ha="right", va="bottom", fontsize=7,
        )

    _save_figure(out_dir, "fig_e1_relative_degradation", deg_source, plot_deg)

    clip_source = safety[safety["method"] == "raven"][["seed", "c_clip_obs"]]

    def plot_clip(ax):
        ax.bar(clip_source["seed"].astype(str), clip_source["c_clip_obs"], color="#1f4e79")
        ax.axhline(0.05, color="red", linestyle="--", linewidth=1.0, label="5% threshold")
        ax.set_ylabel("Observed-micro clip")
        ax.set_xlabel("Seed")
        ax.legend(frameon=False, loc="upper right")

    _save_figure(out_dir, "fig_e1_clip_by_seed", clip_source, plot_clip)

    ess_source = aggregate.groupby("method", as_index=False)["median_n_eff"].mean()
    ess_source["label"] = ess_source["method"].map(METHOD_LABELS)
    ess_source = ess_source.set_index("method").loc[METHOD_ORDER].reset_index()

    def plot_ess(ax):
        ax.bar(ess_source["label"], ess_source["median_n_eff"], color=colors)
        ax.set_ylabel("Mean median ESS")

    _save_figure(out_dir, "fig_e1_ess_by_method", ess_source, plot_ess)

    runtime_source = aggregate.groupby("method", as_index=False)["runtime"].mean()
    runtime_source["label"] = runtime_source["method"].map(METHOD_LABELS)
    runtime_source = runtime_source.set_index("method").loc[METHOD_ORDER].reset_index()

    def plot_runtime(ax):
        ax.bar(runtime_source["label"], runtime_source["runtime"], color=colors)
        ax.set_ylabel("Mean runtime (s)")

    _save_figure(out_dir, "fig_e1_runtime_by_method", runtime_source, plot_runtime)

    def plot_fallback(ax):
        ax.bar(solver["seed"].astype(str), solver["fallback_invoked_count"], color="#c55a11")
        ax.set_ylabel("Fallback count")
        ax.set_xlabel("Seed")

    _save_figure(
        out_dir, "fig_e1_solver_fallback_by_seed",
        solver[["seed", "fallback_invoked_count"]], plot_fallback,
    )

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
        ax.legend(fontsize=6, frameon=False)

    _save_figure(out_dir, "fig_e1_solver_residuals", residual_source, plot_residuals)

    gap_source = aggregate.groupby("method", as_index=False)["Gap_mis"].mean()
    gap_source["label"] = gap_source["method"].map(METHOD_LABELS)
    gap_source = gap_source.set_index("method").loc[METHOD_ORDER].reset_index()

    def plot_gap(ax):
        ax.bar(gap_source["label"], gap_source["Gap_mis"], color=colors)
        ax.set_ylabel(r"Mean Gap$_{\mathrm{mis}}$")

    _save_figure(out_dir, "fig_e1_gap_mis_by_method", gap_source, plot_gap)

    head_tail = aggregate.groupby("method", as_index=False).agg({
        "Head_RMSE": "mean",
        "Tail_RMSE": "mean",
    })
    head_tail["label"] = head_tail["method"].map(METHOD_LABELS)
    head_tail = head_tail.set_index("method").loc[METHOD_ORDER].reset_index()

    def plot_head_tail(ax):
        width = 0.35
        x = range(len(head_tail))
        ax.bar([i - width / 2 for i in x], head_tail["Head_RMSE"], width=width, label="Head")
        ax.bar([i + width / 2 for i in x], head_tail["Tail_RMSE"], width=width, label="Tail")
        ax.set_xticks(list(x))
        ax.set_xticklabels(head_tail["label"])
        ax.legend(frameon=False)

    _save_figure(out_dir, "fig_e1_head_tail_rmse", head_tail, plot_head_tail)

    return {
        "status": "PASS",
        "figures_dir": out_dir.as_posix(),
        "figure_count": 10,
        "publication_ready": publication_ready,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--publication-ready", action="store_true")
    args = parser.parse_args(argv)
    result = build_figures(args.root, args.output_root, publication_ready=args.publication_ready)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
