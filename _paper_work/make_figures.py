"""IEEE TMC figures for paper_tmc_r1 from frozen specification-seal CSVs."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path(__file__).resolve().parent / "figure_data"
SEAL = ROOT / "RAVEN_MCS_FINAL_FIGURE_TABLE_PAPER_SPECIFICATION_SEAL_R1"
SEAL_SRC = SEAL / "05_PROVENANCE" / "FINAL_FIGURE_SOURCES"
SRC = LOCAL if (LOCAL / "FIG_E1_E2_RISK_NONINTERCHANGEABILITY.csv").exists() else SEAL_SRC
OUT = Path(__file__).resolve().parent / "figures"

E2_METHODS = ["FedAvg-Window", "FedAsync-Window", "TimeAlign-Agg", "TwoStage-Hajek", "RAVEN-MCS"]
E3_METHODS = ["FedAvg-Window", "FedAsync-Window", "TimeAlign-Agg", "Local-Hajek", "TwoStage-Hajek", "FedAU-Window", "ObsUse-Window", "RAVEN-MCS"]
E3_SHORT = ["FedAvg", "FedAsync", "TimeAlign", "Loc-Hajek", "2S-Hajek", "FedAU", "ObsUse", "RAVEN"]
E2_SHORT = ["FedAvg", "FedAsync", "TimeAlign", "2S-Hajek", "RAVEN"]
COMPONENTS = ["Design", "Obs", "Use", "Inst", "Debt"]
HATCHES = ["///", "\\\\\\", "xxx", "...", "+++", "ooo", "---"]
# Muted, print-safe palette (not neon).
COLORS = ["#6B7B8C", "#7A8B6F", "#8C7A6B", "#6F7A8B", "#8B7A8C", "#7A6F8B", "#3D5A73"]
RAVEN_COLOR = "#3D5A73"


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 9,
            "axes.titlesize": 9,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "axes.linewidth": 0.8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.03,
        }
    )


def _box(ax) -> None:
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_color("#595959")
        s.set_linewidth(1.2)
    ax.tick_params(direction="in", length=2.5, width=0.8)
    ax.grid(False)


def _frame_only(ax) -> None:
    """Show a clean border without ticks (used by the schematic Fig. 1)."""
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_color("#595959")
        s.set_linewidth(1.2)


def _barplot(ax, data, labels, raven_last=True, headroom=0.30):
    """Bar + error bar (mean +/- std) with muted hatched fill.

    Replaces the boxplots so the figures match the ``mean +/- std`` tables
    and the reviewer's bar-chart preference. ``headroom`` keeps empty space
    above the tallest bar so the figure does not look cramped.
    """
    means = np.array([np.mean(d) for d in data])
    stds = np.array([np.std(d, ddof=1) if len(d) > 1 else 0.0 for d in data])
    x = np.arange(len(labels))
    bars = ax.bar(
        x, means, yerr=stds, capsize=2.5, tick_label=labels,
        width=0.6, edgecolor="0.15", linewidth=0.7,
        error_kw=dict(ecolor="0.25", lw=0.7, capthick=0.7),
    )
    for i, b in enumerate(bars):
        is_raven = raven_last and i == len(data) - 1
        b.set_facecolor(RAVEN_COLOR if is_raven else COLORS[i % (len(COLORS) - 1)])
        b.set_alpha(0.85)
        b.set_hatch(HATCHES[-1] if is_raven else HATCHES[i % (len(HATCHES) - 1)])
    lo = float(np.min(means - stds))
    hi = float(np.max(means + stds))
    span = hi - lo if hi > lo else max(abs(hi), 1.0)
    ax.set_ylim(lo - 0.15 * span, hi + headroom * span)
    return bars


def _panel_caption(ax, text: str) -> None:
    ax.set_xlabel(text, fontsize=9, labelpad=3)


def fig1_framework() -> None:
    """Fig. 1 schematic. Meaning is unchanged: (a) R→O→U can make
    arrival mass differ from the public target; (b) reconstruction then
    calibration then aggregation is one coordinated loop.

    Decorative glyphs (bullseye, phones, density sketch, grouping bands)
    only illustrate those existing relations; they are not extra modules.
    """
    from matplotlib.patches import Circle, FancyArrowPatch, Rectangle

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.size": 7,
        "mathtext.fontset": "dejavusans",
        # Keep the declared 7.20 in × 3.15 in canvas; do not inherit
        # tight cropping from _style() if this function is called via main().
        "savefig.bbox": "standard",
        "savefig.pad_inches": 0.0,
    })

    EDGE = "#4D4D4D"
    TXT = "#272727"
    MUTED = "#767676"
    BLUE = "#D7E4F0"     # target / reconstruction
    BEIGE = "#EFE6DA"    # selection layers
    GREEN = "#E3EDE4"    # calibration loop (incl. aggregation)
    TAUPE = "#E8DDD4"    # arrival / mismatch
    ACCENT = "#A56B6B"   # mismatch stroke only; ≠ is also in the arrival node
    WASH_B = "#EEF4F8"
    WASH_G = "#EEF3EE"

    fig, axes = plt.subplots(1, 2, figsize=(7.20, 3.15))

    def frame(ax) -> None:
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(True)
            s.set_color("#B0B0B0")
            s.set_linewidth(0.7)

    def panel_label(ax, letter: str, title: str) -> None:
        ax.text(0.03, 0.97, letter, transform=ax.transAxes, fontsize=8,
                fontweight="bold", color=TXT, ha="left", va="top", zorder=8)
        ax.text(0.10, 0.97, title, transform=ax.transAxes, fontsize=7,
                color=MUTED, ha="left", va="top", zorder=8)

    def node(ax, xy, w, h, text, fc, fs=7.0, math=None, math_fs=9.0, dx=0.0) -> None:
        x, y = xy
        ax.add_patch(FancyBboxPatch(
            (x - w / 2, y - h / 2), w, h,
            boxstyle="round,pad=0.04,rounding_size=0.10",
            facecolor=fc, edgecolor=EDGE, linewidth=0.8, zorder=2,
        ))
        if math is None:
            ax.text(x + dx, y, text, ha="center", va="center", fontsize=fs,
                    color=TXT, zorder=3)
        else:
            ax.text(x + dx, y + 0.22, text, ha="center", va="center", fontsize=fs,
                    color=TXT, zorder=3)
            ax.text(x + dx, y - 0.28, math, ha="center", va="center", fontsize=math_fs,
                    color=TXT, zorder=3)

    def arrow(ax, p0, p1, color=EDGE, lw=0.9, ls="-") -> None:
        ax.add_patch(FancyArrowPatch(
            p0, p1, arrowstyle="-|>", mutation_scale=8.5,
            color=color, lw=lw, linestyle=ls, zorder=4,
            shrinkA=0.5, shrinkB=0.5,
        ))

    def bullseye(ax, x, y, r=0.28) -> None:
        ax.add_patch(Circle((x, y), r, facecolor="white", edgecolor=EDGE,
                            lw=0.55, zorder=5))
        ax.add_patch(Circle((x, y), r * 0.64, facecolor=BLUE, edgecolor=EDGE,
                            lw=0.4, zorder=6))
        ax.add_patch(Circle((x, y), r * 0.26, facecolor=ACCENT, edgecolor="none",
                            zorder=7))

    def phone(ax, x, y, h=0.62) -> None:
        w = h * 0.52
        ax.add_patch(FancyBboxPatch(
            (x - w / 2, y - h / 2), w, h,
            boxstyle="round,pad=0.015,rounding_size=0.08",
            facecolor=BEIGE, edgecolor=EDGE, linewidth=0.55, zorder=3,
        ))
        ax.add_patch(FancyBboxPatch(
            (x - w / 2 + 0.05, y - h / 2 + 0.10), w - 0.10, h - 0.22,
            boxstyle="round,pad=0.008,rounding_size=0.04",
            facecolor="white", edgecolor="#A8A8A8", linewidth=0.35, zorder=4,
        ))
        ax.add_patch(Circle((x, y - h / 2 + 0.055), 0.028,
                            facecolor="#8A8A8A", edgecolor="none", zorder=5))

    def mini_density(ax, x, y) -> None:
        """Unlabeled visual echo of μ vs a skewed arrival; not a new node."""
        ax.add_patch(FancyBboxPatch(
            (x - 1.15, y - 0.72), 2.30, 1.38,
            boxstyle="round,pad=0.03,rounding_size=0.10",
            facecolor="#F7F7F5", edgecolor="#D0D0D0", linewidth=0.5, zorder=1,
        ))
        base = y - 0.22
        for i, hi in enumerate((0.38, 0.40, 0.36)):
            ax.add_patch(Rectangle(
                (x - 0.92 + i * 0.22, base), 0.16, hi,
                facecolor=BLUE, edgecolor=EDGE, linewidth=0.35, zorder=2,
            ))
        for i, hi in enumerate((0.18, 0.30, 0.55)):
            ax.add_patch(Rectangle(
                (x + 0.22 + i * 0.22, base), 0.16, hi,
                facecolor=TAUPE, edgecolor=EDGE, linewidth=0.35, zorder=2,
            ))
        ax.text(x - 0.70, y - 0.52, r"$\mu$", ha="center", va="center",
                fontsize=7, color=TXT, zorder=3)
        ax.text(x + 0.54, y - 0.52, r"$\rho$", ha="center", va="center",
                fontsize=7, color=TXT, zorder=3)
        ax.plot([x, x], [y - 0.18, y + 0.48], color="#C8C8C8", lw=0.45, zorder=2)

    def chain(ax, x, y) -> None:
        ax.add_patch(Circle((x - 0.11, y), 0.16, fill=False, edgecolor=EDGE,
                            lw=0.7, zorder=5))
        ax.add_patch(Circle((x + 0.11, y), 0.16, fill=False, edgecolor=EDGE,
                            lw=0.7, zorder=5))

    def feasible_set(ax, x, y) -> None:
        from matplotlib.patches import Polygon
        pts = np.array([
            (x, y + 0.22), (x + 0.20, y + 0.04), (x + 0.12, y - 0.20),
            (x - 0.12, y - 0.20), (x - 0.20, y + 0.04),
        ])
        ax.add_patch(Polygon(pts, closed=True, facecolor="#F4F7F4",
                             edgecolor=EDGE, lw=0.55, zorder=5))

    # (a) problem: public target vs R → O → U → arrival
    ax = axes[0]
    frame(ax)
    panel_label(ax, "a", "Two-stage selection vs. deployment target")
    node(ax, (5.20, 8.08), 5.0, 1.15, "Public target\n$\\mu$ over $h(i)$", BLUE, fs=7.0, dx=0.28)
    bullseye(ax, 3.28, 8.08, r=0.30)
    phone(ax, 4.35, 6.58)
    phone(ax, 5.05, 6.58)
    phone(ax, 5.75, 6.58)
    node(ax, (3.15, 5.25), 2.7, 1.25, "Opportunity $R$", BEIGE, fs=7.0)
    node(ax, (6.95, 5.25), 2.7, 1.25, "Observation $O$", BEIGE, fs=7.0)
    node(ax, (6.95, 2.35), 2.7, 1.25, "Usable $U$", BEIGE, fs=7.0)
    node(ax, (3.15, 2.35), 2.7, 1.35, "Arrival mass", TAUPE, fs=7.0,
         math=r"$\rho^{\mathrm{arr}}\neq\mu$", math_fs=9.0)
    mini_density(ax, 5.05, 3.78)
    arrow(ax, (4.55, 5.25), (5.55, 5.25))
    arrow(ax, (6.95, 4.58), (6.95, 3.02))
    arrow(ax, (5.55, 2.35), (4.55, 2.35))
    ax.plot([2.55, 0.85, 0.85, 1.75], [8.08, 8.08, 2.35, 2.35],
            color=ACCENT, lw=0.9, ls=(0, (2.2, 1.4)), zorder=1, solid_capstyle="butt")
    arrow(ax, (1.55, 2.35), (1.78, 2.35), color=ACCENT, lw=0.9, ls="-")
    ax.text(1.18, 5.25, "mismatch", fontsize=7, color=ACCENT, rotation=90,
            ha="center", va="center", style="italic", rotation_mode="anchor")

    # (b) architecture: left reconstruction column + calibration loop
    ax = axes[1]
    frame(ax)
    panel_label(ax, "b", "One coordinated architecture")
    ax.text(5.0, 8.72, "Coupled reconstruction + calibration",
            ha="center", va="center", fontsize=7.5, color=TXT)
    ax.text(5.0, 8.22, "not five independent modules",
            ha="center", va="center", fontsize=7.0, color=MUTED)
    xl, xr = 3.55, 7.15
    ax.add_patch(FancyBboxPatch(
        (1.15, 4.95), 4.80, 2.85,
        boxstyle="round,pad=0.04,rounding_size=0.16",
        facecolor=WASH_B, edgecolor="#C5D4E0", linewidth=0.6, zorder=0, linestyle=(0, (1.6, 1.2)),
    ))
    ax.add_patch(FancyBboxPatch(
        (2.05, 0.95), 6.40, 3.40,
        boxstyle="round,pad=0.04,rounding_size=0.16",
        facecolor=WASH_G, edgecolor="#C5D4C8", linewidth=0.6, zorder=0, linestyle=(0, (1.6, 1.2)),
    ))
    node(ax, (xl, 7.15), 4.4, 1.10, "Design / Obs / Use\ncorrection", BLUE, fs=7.0)
    node(ax, (xl, 5.55), 4.4, 1.00, "Normalized reconstruction", BLUE, fs=7.0)
    node(ax, (xl, 3.70), 2.45, 1.15, "Inst.\ncalibration", GREEN, fs=7.0)
    node(ax, (xr, 3.70), 2.45, 1.15, "(P2) feasible\nadjustment", GREEN, fs=7.0)
    feasible_set(ax, 8.72, 3.70)
    node(ax, (xr, 1.80), 2.45, 1.15, "Debt\nupdate", GREEN, fs=7.0)
    node(ax, (xl, 1.80), 2.45, 1.15, "Aggregation", GREEN, fs=7.0,
         math=r"$\theta_{r+1}$", math_fs=9.0)
    chain(ax, 1.42, 4.62)
    arrow(ax, (xl, 6.57), (xl, 6.08))
    arrow(ax, (xl, 5.02), (xl, 4.30))
    arrow(ax, (4.80, 3.70), (5.90, 3.70))
    arrow(ax, (xr, 3.10), (xr, 2.40))
    arrow(ax, (5.90, 1.80), (4.80, 1.80))

    fig.tight_layout(w_pad=0.85, h_pad=0.15)
    OUT.mkdir(parents=True, exist_ok=True)
    stem = OUT / "fig1_raven_problem_framework"
    fig.savefig(f"{stem}.svg", bbox_inches=None)
    fig.savefig(f"{stem}.pdf", bbox_inches=None)
    fig.savefig(f"{stem}.tiff", dpi=600, bbox_inches=None)
    fig.savefig(f"{stem}.png", dpi=600, bbox_inches=None)
    nature_out = Path(__file__).resolve().parent / "figures_nature"
    nature_out.mkdir(parents=True, exist_ok=True)
    nstem = nature_out / "fig1_raven_problem_framework"
    fig.savefig(f"{nstem}.svg", bbox_inches=None)
    fig.savefig(f"{nstem}.pdf", bbox_inches=None)
    fig.savefig(f"{nstem}.tiff", dpi=600, bbox_inches=None)
    fig.savefig(f"{nstem}.png", dpi=600, bbox_inches=None)
    plt.close(fig)


def fig2_e2() -> None:
    df = pd.read_csv(SRC / "FIG_E1_E2_RISK_NONINTERCHANGEABILITY.csv")
    fig, axes = plt.subplots(1, 2, figsize=(7.16, 2.45), gridspec_kw={"width_ratios": [1.35, 1.0]})
    ax = axes[0]
    data = [df.loc[df["method"] == m, "D_aligned"].astype(float).to_numpy() for m in E2_METHODS]
    _barplot(ax, data, E2_SHORT)
    ax.axhline(0.0, color="0.35", ls="--", lw=0.8)
    ax.set_ylabel(r"$D_{\mathrm{aligned}}=\Delta\mathrm{RMSE}_{\mu}-\Delta\mathrm{RMSE}_{\rho}$")
    _box(ax)
    _panel_caption(ax, r"(a) Seed-level $D_{\mathrm{aligned}}$ (20 paired seeds)")

    ax = axes[1]
    neg = [(df.loc[df["method"] == m, "D_aligned"].astype(float) < 0).sum() for m in E2_METHODS]
    x = np.arange(len(E2_METHODS))
    bars = ax.bar(x, neg, color=[RAVEN_COLOR if m == "RAVEN-MCS" else COLORS[i] for i, m in enumerate(E2_METHODS)],
                  edgecolor="0.15", linewidth=0.7, width=0.7)
    for i, b in enumerate(bars):
        b.set_hatch(HATCHES[-1] if E2_METHODS[i] == "RAVEN-MCS" else HATCHES[i])
    ax.set_xticks(x)
    ax.set_xticklabels(E2_SHORT, rotation=18, ha="right")
    ax.set_ylabel("Negative seeds / 20")
    ax.set_ylim(0, 22)
    ax.axhline(10, color="0.7", ls=":", lw=0.6)
    _box(ax)
    _panel_caption(ax, r"(b) Direction count (not a ranking)")
    fig.tight_layout(w_pad=0.7)
    fig.savefig(OUT / "fig2_e2_risk_noninterchangeability.pdf")
    fig.savefig(OUT / "fig2_e2_risk_noninterchangeability.png")
    plt.close(fig)


def fig3_structural() -> None:
    df = pd.read_csv(SRC / "FIG_E2_E3_STRUCTURAL_ALIGNMENT.csv")
    df = df[df["method"].isin(E3_METHODS) & df["dataset"].isin(["SensorScope", "U-Air"])]
    fig, axes = plt.subplots(2, 2, figsize=(7.16, 4.55))
    specs = [
        (0, 0, "SensorScope", "Delta_group", r"(a) SensorScope, $\Delta_{\mathrm{group}}$"),
        (0, 1, "SensorScope", "Delta_c_s", r"(b) SensorScope, $\Delta_{c,s}$"),
        (1, 0, "U-Air", "Delta_group", r"(c) U-Air, $\Delta_{\mathrm{group}}$"),
        (1, 1, "U-Air", "Delta_c_s", r"(d) U-Air, $\Delta_{c,s}$"),
    ]
    for r, c, ds, col, cap in specs:
        ax = axes[r, c]
        sub = df[df["dataset"] == ds]
        data = [sub.loc[sub["method"] == m, col].astype(float).dropna().to_numpy() for m in E3_METHODS]
        _barplot(ax, data, E3_SHORT)
        ax.set_ylabel(r"$\Delta_{\mathrm{group}}$" if col == "Delta_group" else r"$\Delta_{c,s}$")
        ax.tick_params(axis="x", rotation=28)
        _box(ax)
        _panel_caption(ax, cap)
    fig.tight_layout(h_pad=1.1, w_pad=0.6)
    fig.savefig(OUT / "fig3_e3_structural_mismatch.pdf")
    fig.savefig(OUT / "fig3_e3_structural_mismatch.png")
    plt.close(fig)


def fig4_prediction() -> None:
    df = pd.read_csv(SRC / "FIG_E3_E3_PREDICTION_RISK.csv")
    df = df[df["method"].isin(E3_METHODS) & df["dataset"].isin(["SensorScope", "U-Air"])]
    fig, axes = plt.subplots(2, 2, figsize=(7.16, 4.55))
    specs = [
        (0, 0, "SensorScope", "RMSE_mu", r"(a) SensorScope, $\mathrm{RMSE}_{\mu}$"),
        (0, 1, "SensorScope", "Tail_RMSE", r"(b) SensorScope, Tail RMSE"),
        (1, 0, "U-Air", "RMSE_mu", r"(c) U-Air, $\mathrm{RMSE}_{\mu}$"),
        (1, 1, "U-Air", "Tail_RMSE", r"(d) U-Air, Tail RMSE"),
    ]
    for r, c, ds, col, cap in specs:
        ax = axes[r, c]
        sub = df[df["dataset"] == ds]
        data = [sub.loc[sub["method"] == m, col].astype(float).dropna().to_numpy() for m in E3_METHODS]
        _barplot(ax, data, E3_SHORT)
        ax.set_ylabel(r"$\mathrm{RMSE}_{\mu}$" if col == "RMSE_mu" else "Tail RMSE")
        ax.tick_params(axis="x", rotation=28)
        _box(ax)
        _panel_caption(ax, cap)
    fig.tight_layout(h_pad=1.1, w_pad=0.6)
    fig.savefig(OUT / "fig4_e3_prediction_risk.pdf")
    fig.savefig(OUT / "fig4_e3_prediction_risk.png")
    plt.close(fig)


def fig5_ablation() -> None:
    df = pd.read_csv(SRC / "FIG_E4_E4_COMPONENT_ABLATION.csv")
    fig, axes = plt.subplots(2, 2, figsize=(7.16, 4.65))
    metric_groups = [
        (0, 0, "SensorScope", ["Delta_group", "Delta_c_s"], [r"$\Delta_{\mathrm{group}}$", r"$\Delta_{c,s}$"],
         r"(a) SensorScope, structural"),
        (0, 1, "SensorScope", ["RMSE_mu", "Tail_RMSE"], [r"$\mathrm{RMSE}_{\mu}$", "Tail RMSE"],
         r"(b) SensorScope, prediction"),
        (1, 0, "U-Air", ["Delta_group", "Delta_c_s"], [r"$\Delta_{\mathrm{group}}$", r"$\Delta_{c,s}$"],
         r"(c) U-Air, structural"),
        (1, 1, "U-Air", ["RMSE_mu", "Tail_RMSE"], [r"$\mathrm{RMSE}_{\mu}$", "Tail RMSE"],
         r"(d) U-Air, prediction"),
    ]
    x = np.arange(len(COMPONENTS))
    w = 0.36

    def _vals_sig(ds, metric):
        vals, sigs = [], []
        for comp in COMPONENTS:
            hit = df[(df["dataset"] == ds) & (df["component"] == comp) & (df["metric"] == metric)]
            if len(hit):
                vals.append(float(hit.iloc[0]["relative_change_percent"]))
                sigs.append(bool(hit.iloc[0]["holm_significant"]))
            else:
                vals.append(0.0)
                sigs.append(False)
        return vals, sigs

    def _draw_bars(ax, series, xvals=None, width=w, annotate=True, fs=6.0):
        xs = x if xvals is None else xvals
        artists = []
        for j, (vals, lab, sigs) in enumerate(series):
            bars = ax.bar(xs + (j - 0.5) * width, vals, width=width, label=lab,
                          color=COLORS[j + 1], edgecolor="0.15", linewidth=0.6)
            for b in bars:
                b.set_hatch(HATCHES[j])
            artists.append((bars, vals, sigs))
        ax.axhline(0.0, color="0.25", lw=0.8)
        if annotate:
            flat = [v for vals, _, _ in series for v in vals]
            span = max(max(flat) - min(flat), 1e-3)
            for bars, vals, sigs in artists:
                for b, v, sig in zip(bars, vals, sigs):
                    if abs(v) < 0.05 and not sig:
                        continue
                    off = 0.055 * span
                    label = f"{v:+.2f}" + ("*" if sig else "")
                    ax.text(b.get_x() + b.get_width() / 2.0, v + (off if v >= 0 else -off),
                            label, ha="center", va="bottom" if v >= 0 else "top",
                            fontsize=fs, color="0.15",
                            bbox=dict(boxstyle="square,pad=0.10", fc="white", ec="none", alpha=0.85))
        return artists

    for r, c, ds, metrics, labs, cap in metric_groups:
        ax = axes[r, c]
        series = []
        for metric, lab in zip(metrics, labs):
            v, s = _vals_sig(ds, metric)
            series.append((v, lab, s))
        _draw_bars(ax, series, annotate=(ds != "U-Air"))
        if ds == "U-Air":
            # Design dominates U-Air, so only label Design's first metric on the
            # main axis and zoom the rest in an inset.
            for j, (vals, lab, sigs) in enumerate(series):
                label = f"{vals[0]:+.2f}" + ("*" if sigs[0] else "")
                ax.text(x[0] + (j - 0.5) * w, vals[0] + (0.28 if vals[0] >= 0 else -0.28),
                        label, ha="center", va="bottom" if vals[0] >= 0 else "top",
                        fontsize=6.0, color="0.15",
                        bbox=dict(boxstyle="square,pad=0.10", fc="white", ec="none", alpha=0.85))
            ins = ax.inset_axes([0.40, 0.10, 0.57, 0.40])
            ins.set_facecolor("white")
            zoom = [(vals[1:], lab, sigs[1:]) for vals, lab, sigs in series]
            zx = np.arange(len(COMPONENTS) - 1)
            _draw_bars(ins, zoom, xvals=zx, width=0.34, annotate=True, fs=5.5)
            ins.set_xticks(zx)
            ins.set_xticklabels(COMPONENTS[1:], fontsize=6.5)
            ins.set_title("excl. Design", fontsize=6.5, pad=1.5, color="0.3")
            _box(ins)
            ins.tick_params(labelsize=6)
        flat = [v for vals, _, _ in series for v in vals]
        ymin, ymax = min(flat), max(flat)
        pad = max(0.18 * (ymax - ymin + 1e-6), 0.08 * max(abs(ymin), abs(ymax), 0.02))
        ax.set_ylim(ymin - pad, ymax + 1.55 * pad)
        ax.set_xticks(x)
        ax.set_xticklabels(COMPONENTS)
        ax.set_ylabel("rel. change (%)")
        _box(ax)
        loc = "upper right" if ds == "U-Air" else "best"
        leg = ax.legend(frameon=True, fancybox=False, edgecolor="0.3", loc=loc,
                        borderpad=0.25, handlelength=1.4)
        leg.get_frame().set_linewidth(0.6)
        _panel_caption(ax, cap)
    fig.tight_layout(h_pad=1.05, w_pad=0.55)
    fig.savefig(OUT / "fig5_e4_component_ablation.pdf")
    fig.savefig(OUT / "fig5_e4_component_ablation.png")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _style()
    fig1_framework()
    fig2_e2()
    fig3_structural()
    fig4_prediction()
    fig5_ablation()
    print("wrote", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
