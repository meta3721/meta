#!/usr/bin/env python3
"""Build camera-ready E1-R2 figures for teacher review / paper submission."""
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

SHORT_LABELS = {
    "flamf_timealign_adapted": "TimeAlign",
    "raven": "RAVEN",
    "fedavg_window": "FedAvg",
    "fedasync_window": "FedAsync",
    "twostage_hajek": "2S-Hajek",
}
METHOD_ORDER = list(SHORT_LABELS.keys())
COLORS = ["#1f4e79", "#c55a11", "#7f7f7f", "#7f7f7f", "#7f7f7f"]


def _stats_dir(root: Path) -> Path:
    for candidate in (
        root / "outputs/statistics/E1_R2_FINAL_SEALED",
        root / "outputs/statistics/E1_R2_SEALED",
    ):
        if candidate.is_dir():
            return candidate
    return root / "outputs/statistics/E1_R2_FINAL_SEALED"


def _save(out_dir: Path, stem: str, frame: pd.DataFrame, plot_fn, *, figsize=(3.4, 2.5)) -> None:
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 8,
        "axes.labelsize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "savefig.dpi": 300,
    })
    fig, ax = plt.subplots(figsize=figsize)
    plot_fn(ax)
    fig.tight_layout()
    fig.savefig(out_dir / f"{stem}.pdf")
    fig.savefig(out_dir / f"{stem}.png", dpi=300)
    plt.close(fig)
    frame.to_csv(out_dir / f"{stem}_source.csv", index=False)


def build_figures(root: Path, output_root: Path | None = None) -> dict[str, Any]:
    root = Path(root)
    out_dir = Path(output_root) if output_root else root / "outputs/paper/E1_R2_CAMERA_READY/figures"
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    aggregate = pd.read_parquet(root / "outputs/aggregate/E1_R2/per_seed_metrics.parquet")
    recompute = json.loads(
        (root / "outputs/audits/E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json").read_text(encoding="utf-8")
    )
    safety = pd.read_csv(root / "outputs/audits/E1_R2_FORMAL_SAFETY_SUMMARY.csv")
    solver = pd.read_csv(root / "outputs/audits/E1_R2_RAVEN_SOLVER_SUMMARY.csv")
    stats_dir = _stats_dir(root)
    no_harm = pd.read_parquet(stats_dir / "no_harm_per_seed.parquet")

    summary = pd.DataFrame(recompute["method_summary"]).set_index("method").loc[METHOD_ORDER].reset_index()
    summary["label"] = summary["method"].map(SHORT_LABELS)
    rmse = summary[["label", "RMSE_mu_mean", "RMSE_mu_std"]].rename(
        columns={"label": "method", "RMSE_mu_mean": "mean", "RMSE_mu_std": "std"}
    )

    def plot_rmse(ax):
        bars = ax.bar(rmse["method"], rmse["mean"], yerr=rmse["std"], capsize=2.5,
                      color=COLORS, edgecolor="black", linewidth=0.4)
        ymin = float(rmse["mean"].min() - rmse["std"].max()) - 0.004
        ymax = float(rmse["mean"].max() + rmse["std"].max()) + 0.006
        ax.set_ylim(ymin, ymax)
        ax.set_ylabel(r"RMSE$_\mu$")
        ax.tick_params(axis="x", rotation=18)
        for bar, tag in zip(bars, ["best", "second", "", "", ""]):
            if tag:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), tag,
                        ha="center", va="bottom", fontsize=7)

    _save(out_dir, "fig_e1_rmse_mu_by_method", rmse, plot_rmse)

    deg = no_harm[["seed", "degradation"]].copy()
    deg["relative_pct"] = deg["degradation"] * 100.0

    def plot_deg(ax):
        ax.bar(deg["seed"].astype(str), deg["relative_pct"], color="#1f4e79", width=0.65)
        ax.axhline(0.0, color="black", linewidth=0.8)
        ax.set_ylim(-0.25, 0.25)
        ax.set_ylabel("Rel. degradation (%)")
        ax.set_xlabel("Seed")
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)

    _save(out_dir, "fig_e1_relative_degradation", deg, plot_deg)

    clip = safety[safety["method"] == "raven"][["seed", "c_clip_obs"]].copy()
    clip["clip_pct"] = clip["c_clip_obs"] * 100.0

    def plot_clip(ax):
        ax.bar(clip["seed"].astype(str), clip["clip_pct"], color="#1f4e79", width=0.65)
        ax.axhline(5.0, color="red", linestyle="--", linewidth=1.0)
        ax.set_ylabel("Observed-micro clip (%)")
        ax.set_xlabel("Seed")

    _save(out_dir, "fig_e1_clip_by_seed", clip, plot_clip)

    fb = solver[["seed", "fallback_invoked_count"]].copy()

    def plot_fb(ax):
        ax.bar(fb["seed"].astype(str), fb["fallback_invoked_count"], color="#c55a11", width=0.65)
        ax.set_ylabel("Fallback count")
        ax.set_xlabel("Seed")

    _save(out_dir, "fig_e1_solver_fallback_by_seed", fb, plot_fb)

    runtime = aggregate.groupby("method", as_index=False)["runtime"].mean()
    runtime = runtime.set_index("method").loc[METHOD_ORDER].reset_index()
    runtime["label"] = runtime["method"].map(SHORT_LABELS)

    def plot_runtime(ax):
        ax.bar(runtime["label"], runtime["runtime"], color=COLORS, edgecolor="black", linewidth=0.4)
        ax.set_ylabel("Mean runtime (s)")
        ax.tick_params(axis="x", rotation=18)

    _save(out_dir, "fig_e1_runtime_by_method", runtime[["label", "runtime"]], plot_runtime)

    return {
        "status": "PASS",
        "figures_dir": out_dir.as_posix(),
        "figure_count": 5,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--publication-ready", action="store_true")
    args = parser.parse_args(argv)
    result = build_figures(args.root, args.output_root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
