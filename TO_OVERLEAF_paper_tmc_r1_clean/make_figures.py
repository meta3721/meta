"""IEEE TMC figures for paper_tmc_r1 from frozen specification-seal CSVs."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOCAL = Path(__file__).resolve().parent / "figure_data"
SEAL = ROOT / "RAVEN_MCS_FINAL_FIGURE_TABLE_PAPER_SPECIFICATION_SEAL_R1"
SEAL_SRC = SEAL / "05_PROVENANCE" / "FINAL_FIGURE_SOURCES"
SRC = LOCAL if (LOCAL / "FIG_E1_E2_RISK_NONINTERCHANGEABILITY.csv").exists() else SEAL_SRC
OUT = Path(__file__).resolve().parent / "figures"

E2_METHODS = ["FedAvg-Window", "FedAsync-Window", "TimeAlign-Agg", "TwoStage-Hajek", "RAVEN-MCS"]
E3_METHODS = ["FedAvg-Window", "FedAsync-Window", "TimeAlign-Agg", "Local-Hajek", "TwoStage-Hajek", "RAVEN-MCS"]
E3_SHORT = ["FedAvg", "FedAsync", "TimeAlign", "Loc-Hajek", "2S-Hajek", "RAVEN"]
E2_SHORT = ["FedAvg", "FedAsync", "TimeAlign", "2S-Hajek", "RAVEN"]
COMPONENTS = ["Design", "Obs", "Use", "Inst", "Debt"]
HATCHES = ["///", "\\\\\\", "xxx", "...", "+++", "ooo"]
# Muted, print-safe palette (not neon).
COLORS = ["#6B7B8C", "#7A8B6F", "#8C7A6B", "#6F7A8B", "#8B7A8C", "#3D5A73"]
RAVEN_COLOR = "#3D5A73"


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            # Match the IEEEtran body font (Times) and math (Computer Modern).
            "font.serif": ["Times New Roman", "DejaVu Serif"],
            "mathtext.fontset": "cm",
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


def _barplot(ax, data, labels, raven_last=True, headroom=0.30, compact=False):
    """Bar + error bar (mean +/- std) with muted hatched fill.

    Replaces the boxplots so the figures match the ``mean +/- std`` tables
    and the reviewer's bar-chart preference. ``headroom`` keeps empty space
    above the tallest bar so the figure does not look cramped.
    ``compact`` is for one-column multi-panel layouts.
    """
    means = np.array([np.mean(d) for d in data])
    stds = np.array([np.std(d, ddof=1) if len(d) > 1 else 0.0 for d in data])
    x = np.arange(len(labels))
    cap = 1.5 if compact else 2.5
    bars = ax.bar(
        x, means, yerr=stds, capsize=cap,
        width=0.64 if compact else 0.6, edgecolor="0.15",
        linewidth=0.6 if compact else 0.7,
        error_kw=dict(ecolor="0.25", lw=0.6, capthick=0.6),
    )
    for i, b in enumerate(bars):
        is_raven = raven_last and i == len(data) - 1
        b.set_facecolor(RAVEN_COLOR if is_raven else COLORS[i % (len(COLORS) - 1)])
        b.set_alpha(0.85)
        b.set_hatch(HATCHES[-1] if is_raven else HATCHES[i % (len(HATCHES) - 1)])
    lo = float(np.min(means - stds))
    hi = float(np.max(means + stds))
    span = hi - lo if hi > lo else max(abs(hi), 1.0)
    ax.set_ylim(lo - 0.12 * span, hi + headroom * span)
    ax.set_xticks(x)
    ax.set_xticklabels(
        labels,
        rotation=42 if compact else 16,
        ha="right",
        fontsize=5.6 if compact else 7.5,
    )
    if compact:
        ax.tick_params(axis="y", labelsize=6.0)
    return bars


def _panel_caption(ax, text: str, compact: bool = False) -> None:
    ax.set_xlabel(text, fontsize=7.5 if compact else 9, labelpad=3 if compact else 4)


def fig1_framework() -> None:
    """Fig. 1 from ``_paper_work/figures_nature``: funnel + coupled loop.

    Visual content matches the Nature-restyled schematic.  The paper wrapper
    stays ``figure*`` + ``width=\\textwidth``; this function only redraws the
    same two panels in the IEEE two-column 1x2 slot.
    """

    EDGE = "#4D4D4D"
    TXT = "#272727"
    MUTED = "#767676"
    BLUE = "#D7E4F0"
    BEIGE = "#EFE6DA"
    GREEN = "#E3EDE4"
    TAUPE = "#E8DDD4"
    ACCENT = "#A56B6B"
    WASH_B = "#EEF4F8"
    WASH_G = "#EEF3EE"
    RING = "#C5D0C8"

    # Same 1x2 IEEE slot as the previous Overleaf Fig. 1 (not the stacked
    # Nature canvas).  Content, colours, and glyphs are those of figures_nature.
    fig, axes = plt.subplots(1, 2, figsize=(7.16, 3.35))
    fig.subplots_adjust(left=0.012, right=0.988, top=0.97, bottom=0.11, wspace=0.08)

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
        ax.set_xlabel(f"({letter}) {title}", fontsize=8, labelpad=2)

    def capsule(ax, xy, w, h, text, fc, fs=6.2, math=None, math_fs=7.5) -> None:
        x, y = xy
        ax.add_patch(FancyBboxPatch(
            (x - w / 2, y - h / 2), w, h,
            boxstyle="round,pad=0.03,rounding_size=0.18",
            facecolor=fc, edgecolor=EDGE, linewidth=0.75, zorder=3,
        ))
        if math is None:
            ax.text(x, y, text, ha="center", va="center", fontsize=fs,
                    color=TXT, zorder=4)
        else:
            ax.text(x, y + 0.18, text, ha="center", va="center", fontsize=fs,
                    color=TXT, zorder=4)
            ax.text(x, y - 0.26, math, ha="center", va="center", fontsize=math_fs,
                    color=TXT, zorder=4)

    def arrow(ax, p0, p1, color=EDGE, lw=0.95, rad=0.0, ms=8.0) -> None:
        ax.add_patch(FancyArrowPatch(
            p0, p1, arrowstyle="-|>", mutation_scale=ms,
            color=color, lw=lw, zorder=5, shrinkA=0.2, shrinkB=0.2,
            connectionstyle=f"arc3,rad={rad}",
        ))

    def bullseye(ax, x, y, r=0.26) -> None:
        ax.add_patch(Circle((x, y), r, facecolor="white", edgecolor=EDGE,
                            lw=0.55, zorder=5))
        ax.add_patch(Circle((x, y), r * 0.64, facecolor=BLUE, edgecolor=EDGE,
                            lw=0.4, zorder=6))
        ax.add_patch(Circle((x, y), r * 0.26, facecolor=ACCENT, edgecolor="none",
                            zorder=7))

    def phone(ax, x, y, h=0.52) -> None:
        w = h * 0.52
        ax.add_patch(FancyBboxPatch(
            (x - w / 2, y - h / 2), w, h,
            boxstyle="round,pad=0.012,rounding_size=0.07",
            facecolor=BEIGE, edgecolor=EDGE, linewidth=0.5, zorder=3,
        ))
        ax.add_patch(FancyBboxPatch(
            (x - w / 2 + 0.04, y - h / 2 + 0.08), w - 0.08, h - 0.18,
            boxstyle="round,pad=0.006,rounding_size=0.03",
            facecolor="white", edgecolor="#A8A8A8", linewidth=0.3, zorder=4,
        ))

    def bars(ax, x, y, heights, fc, w=0.30, gap=0.09) -> None:
        n = len(heights)
        total = n * w + (n - 1) * gap
        x0 = x - total / 2
        for i, hi in enumerate(heights):
            ax.add_patch(Rectangle(
                (x0 + i * (w + gap), y), w, hi,
                facecolor=fc, edgecolor=EDGE, linewidth=0.4, zorder=3,
            ))

    def funnel(ax, y_top, y_bot, w_top, w_bot, xc, fc, shift=0.0) -> None:
        xtl, xtr = xc - w_top / 2, xc + w_top / 2
        xbl, xbr = xc + shift - w_bot / 2, xc + shift + w_bot / 2
        ax.add_patch(Polygon(
            [(xtl, y_top), (xtr, y_top), (xbr, y_bot), (xbl, y_bot)],
            closed=True, facecolor=fc, edgecolor="none", zorder=0, alpha=0.95,
        ))

    def chain(ax, x, y) -> None:
        ax.add_patch(Circle((x - 0.12, y), 0.17, fill=False, edgecolor=EDGE,
                            lw=0.7, zorder=6))
        ax.add_patch(Circle((x + 0.12, y), 0.17, fill=False, edgecolor=EDGE,
                            lw=0.7, zorder=6))

    def feasible_set(ax, x, y, s=0.34) -> None:
        pts = np.array([
            (x, y + s), (x + 0.95 * s, y + 0.18 * s),
            (x + 0.59 * s, y - 0.81 * s), (x - 0.59 * s, y - 0.81 * s),
            (x - 0.95 * s, y + 0.18 * s),
        ])
        ax.add_patch(Polygon(pts, closed=True, facecolor="#F4F7F4",
                             edgecolor=EDGE, lw=0.6, zorder=6))

    # (a) funnel: public target is filtered by R → O → U into a mismatched arrival
    ax = axes[0]
    frame(ax)
    panel_label(ax, "a", "Selection warps the public target")

    ax.add_patch(FancyBboxPatch(
        (1.50, 7.58), 7.20, 1.56,
        boxstyle="round,pad=0.03,rounding_size=0.12",
        facecolor=WASH_B, edgecolor="#C5D4E0", linewidth=0.55, zorder=0,
    ))
    bullseye(ax, 2.18, 8.36, r=0.28)
    bars(ax, 4.15, 7.80, (0.66, 0.66, 0.66), BLUE)
    ax.text(6.85, 8.52, "Public target", ha="center", va="center",
            fontsize=6.2, color=TXT, zorder=4)
    ax.text(6.85, 8.02, r"$\mu$ over $h(i)$", ha="center", va="center",
            fontsize=7.5, color=TXT, zorder=4)

    funnel(ax, 6.82, 2.18, 6.55, 3.85, 5.10, "#F3EBE0", shift=0.32)
    phone(ax, 4.40, 6.52)
    phone(ax, 5.10, 6.52)
    phone(ax, 5.80, 6.52)
    capsule(ax, (5.10, 5.82), 3.45, 0.70, r"Opportunity $R$", BEIGE)
    capsule(ax, (5.20, 4.18), 3.25, 0.70, r"Observation $O$", BEIGE)
    capsule(ax, (5.32, 2.68), 3.05, 0.70, r"Usable $U$", BEIGE)
    arrow(ax, (5.12, 5.44), (5.18, 4.56), ms=8.0)
    arrow(ax, (5.22, 3.80), (5.30, 3.06), ms=8.0)
    ax.text(8.48, 4.18, "two-stage\nselection", ha="center", va="center",
            fontsize=5.8, color=MUTED, zorder=4)

    ax.add_patch(FancyBboxPatch(
        (1.50, 0.22), 7.20, 1.82,
        boxstyle="round,pad=0.03,rounding_size=0.12",
        facecolor="#F3EBE4", edgecolor="#D4C4B6", linewidth=0.55, zorder=0,
    ))
    bars(ax, 4.15, 0.48, (0.30, 0.58, 0.90), TAUPE)
    ax.text(6.85, 1.42, "Arrival mass", ha="center", va="center",
            fontsize=6.2, color=TXT, zorder=4)
    ax.text(6.85, 0.82, r"$\rho^{\mathrm{arr}}\neq\mu$", ha="center", va="center",
            fontsize=7.5, color=TXT, zorder=4)

    ax.plot([1.15, 1.15], [8.36, 1.13], color=ACCENT, lw=1.0,
            ls=(0, (2.0, 1.3)), zorder=2, solid_capstyle="butt")
    ax.plot([1.15, 1.48], [8.36, 8.36], color=ACCENT, lw=1.0, zorder=2)
    ax.plot([1.15, 1.48], [1.13, 1.13], color=ACCENT, lw=1.0, zorder=2)
    ax.add_patch(Circle((1.15, 4.75), 0.40, facecolor="white",
                        edgecolor=ACCENT, lw=0.8, zorder=6))
    ax.text(1.15, 4.75, r"$\neq$", ha="center", va="center", fontsize=8,
            color=ACCENT, zorder=7)

    # (b) orbit: reconstruction feeds a calibration loop on the feasible set
    ax = axes[1]
    frame(ax)
    panel_label(ax, "b", "One coupled reconstruction + calibration loop")

    ax.add_patch(FancyBboxPatch(
        (0.55, 7.58), 8.90, 1.52,
        boxstyle="round,pad=0.03,rounding_size=0.14",
        facecolor=WASH_B, edgecolor="#C5D4E0", linewidth=0.55, zorder=0,
        linestyle=(0, (1.6, 1.2)),
    ))
    capsule(ax, (3.05, 8.34), 3.70, 1.00,
            "Design, observation\nand usable correction", BLUE, fs=5.6)
    capsule(ax, (7.20, 8.34), 3.30, 1.00, "Normalized\nreconstruction", BLUE, fs=6.0)
    arrow(ax, (4.88, 8.34), (5.42, 8.34))

    cx, cy, rr = 5.05, 3.38, 2.38
    ax.add_patch(Circle((cx, cy), rr + 0.78, facecolor=WASH_G,
                        edgecolor="#C5D4C8", linewidth=0.55, zorder=0,
                        linestyle=(0, (1.6, 1.2))))
    ax.add_patch(Circle((cx, cy), rr, fill=False, edgecolor=RING,
                        linewidth=1.35, zorder=1))
    feasible_set(ax, cx, cy + 0.10, s=0.48)
    ax.text(cx, cy - 0.58, "feasible set", ha="center", va="center",
            fontsize=5.8, color=MUTED, zorder=6)

    nodes_b = [
        ((cx, cy + rr), 2.72, 0.95, "Instantaneous\ncalibration"),
        ((cx + rr, cy), 2.55, 0.95, "(P2) feasible\nadjustment"),
        ((cx, cy - rr), 2.28, 0.90, "Debt\nupdate"),
        ((cx - rr, cy), 2.38, 0.98, "Aggregation"),
    ]
    for (xy, w, h, text) in nodes_b:
        capsule(ax, xy, w, h, text, GREEN, fs=6.0)
    ax.text(cx - rr, cy - 0.58, r"$\theta_{r+1}$", ha="center", va="top",
            fontsize=7.5, color=TXT, zorder=6)

    arrow(ax, (5.05, 7.58), (5.05, cy + rr + 0.50))
    chain(ax, 4.22, 6.72)
    ax.text(cx, 0.32, "not five independent modules", ha="center",
            va="center", fontsize=6.2, color=MUTED, style="italic", zorder=7)
    arrow(ax, (cx + 0.92, cy + rr - 0.52), (cx + rr - 0.52, cy + 0.92), rad=-0.22)
    arrow(ax, (cx + rr - 0.52, cy - 0.92), (cx + 0.92, cy - rr + 0.52), rad=-0.22)
    arrow(ax, (cx - 0.92, cy - rr + 0.52), (cx - rr + 0.52, cy - 0.92), rad=-0.22)

    fig.savefig(OUT / "fig1_raven_problem_framework.pdf")
    fig.savefig(OUT / "fig1_raven_problem_framework.png")
    plt.close(fig)


def fig2_e2() -> None:
    df = pd.read_csv(SRC / "FIG_E1_E2_RISK_NONINTERCHANGEABILITY.csv")
    fig, axes = plt.subplots(1, 2, figsize=(3.5, 2.15))
    ax = axes[0]
    data = [df.loc[df["method"] == m, "D_aligned"].astype(float).to_numpy() for m in E2_METHODS]
    _barplot(ax, data, E2_SHORT, compact=True, headroom=0.38)
    ax.axhline(0.0, color="0.35", ls="--", lw=0.8)
    ax.set_ylabel(r"$D_{\mathrm{aligned}}$", fontsize=7)
    _box(ax)
    _panel_caption(ax, r"(a) Seed-level $D_{\mathrm{aligned}}$", compact=True)

    ax = axes[1]
    neg = [(df.loc[df["method"] == m, "D_aligned"].astype(float) < 0).sum() for m in E2_METHODS]
    x = np.arange(len(E2_METHODS))
    bars = ax.bar(x, neg, color=[RAVEN_COLOR if m == "RAVEN-MCS" else COLORS[i] for i, m in enumerate(E2_METHODS)],
                  edgecolor="0.15", linewidth=0.6, width=0.7)
    for i, b in enumerate(bars):
        b.set_hatch(HATCHES[-1] if E2_METHODS[i] == "RAVEN-MCS" else HATCHES[i])
    ax.set_xticks(x)
    ax.set_xticklabels(E2_SHORT, rotation=42, ha="right", fontsize=5.6)
    ax.set_ylabel("Negative seeds / 20", fontsize=7)
    ax.tick_params(axis="y", labelsize=6.0)
    ax.set_ylim(0, 24)
    ax.axhline(10, color="0.7", ls=":", lw=0.6)
    _box(ax)
    _panel_caption(ax, r"(b) Direction count (not a ranking)", compact=True)
    fig.tight_layout(w_pad=0.45)
    fig.savefig(OUT / "fig2_e2_risk_noninterchangeability.pdf")
    fig.savefig(OUT / "fig2_e2_risk_noninterchangeability.png")
    plt.close(fig)


def fig3_structural() -> None:
    df = pd.read_csv(SRC / "FIG_E2_E3_STRUCTURAL_ALIGNMENT.csv")
    df = df[df["method"].isin(E3_METHODS) & df["dataset"].isin(["SensorScope", "U-Air"])]
    fig, axes = plt.subplots(2, 2, figsize=(3.5, 3.35))
    specs = [
        (0, "SensorScope", "Delta_group", r"(a) SensorScope, $\Delta_{\mathrm{group}}$"),
        (1, "SensorScope", "Delta_c_s", r"(b) SensorScope, $\Delta_{c,s}$"),
        (2, "U-Air", "Delta_group", r"(c) U-Air, $\Delta_{\mathrm{group}}$"),
        (3, "U-Air", "Delta_c_s", r"(d) U-Air, $\Delta_{c,s}$"),
    ]
    for c, ds, col, cap in specs:
        ax = axes.flat[c]
        sub = df[df["dataset"] == ds]
        data = [sub.loc[sub["method"] == m, col].astype(float).dropna().to_numpy() for m in E3_METHODS]
        _barplot(ax, data, E3_SHORT, compact=True, headroom=0.42)
        ax.set_ylabel(r"$\Delta_{\mathrm{group}}$" if col == "Delta_group" else r"$\Delta_{c,s}$", fontsize=7)
        _box(ax)
        _panel_caption(ax, cap, compact=True)
    fig.tight_layout(h_pad=0.45, w_pad=0.35)
    fig.savefig(OUT / "fig3_e3_structural_mismatch.pdf")
    fig.savefig(OUT / "fig3_e3_structural_mismatch.png")
    plt.close(fig)


def fig4_prediction() -> None:
    df = pd.read_csv(SRC / "FIG_E3_E3_PREDICTION_RISK.csv")
    df = df[df["method"].isin(E3_METHODS) & df["dataset"].isin(["SensorScope", "U-Air"])]
    fig, axes = plt.subplots(2, 2, figsize=(3.5, 3.35))
    specs = [
        (0, "SensorScope", "RMSE_mu", r"(a) SensorScope, $\mathrm{RMSE}_{\mu}$"),
        (1, "SensorScope", "Tail_RMSE", r"(b) SensorScope, Tail RMSE"),
        (2, "U-Air", "RMSE_mu", r"(c) U-Air, $\mathrm{RMSE}_{\mu}$"),
        (3, "U-Air", "Tail_RMSE", r"(d) U-Air, Tail RMSE"),
    ]
    for c, ds, col, cap in specs:
        ax = axes.flat[c]
        sub = df[df["dataset"] == ds]
        data = [sub.loc[sub["method"] == m, col].astype(float).dropna().to_numpy() for m in E3_METHODS]
        _barplot(ax, data, E3_SHORT, compact=True, headroom=0.42)
        ax.set_ylabel(r"$\mathrm{RMSE}_{\mu}$" if col == "RMSE_mu" else "Tail RMSE", fontsize=7)
        _box(ax)
        _panel_caption(ax, cap, compact=True)
    fig.tight_layout(h_pad=0.45, w_pad=0.35)
    fig.savefig(OUT / "fig4_e3_prediction_risk.pdf")
    fig.savefig(OUT / "fig4_e3_prediction_risk.png")
    plt.close(fig)


def fig5_ablation() -> None:
    df = pd.read_csv(SRC / "FIG_E4_E4_COMPONENT_ABLATION.csv")
    fig, axes = plt.subplots(2, 2, figsize=(3.5, 3.45))
    metric_groups = [
        (0, "SensorScope", ["Delta_group", "Delta_c_s"], [r"$\Delta_{\mathrm{group}}$", r"$\Delta_{c,s}$"],
         r"(a) SensorScope, structural"),
        (1, "SensorScope", ["RMSE_mu", "Tail_RMSE"], [r"$\mathrm{RMSE}_{\mu}$", "Tail RMSE"],
         r"(b) SensorScope, prediction"),
        (2, "U-Air", ["Delta_group", "Delta_c_s"], [r"$\Delta_{\mathrm{group}}$", r"$\Delta_{c,s}$"],
         r"(c) U-Air, structural"),
        (3, "U-Air", ["RMSE_mu", "Tail_RMSE"], [r"$\mathrm{RMSE}_{\mu}$", "Tail RMSE"],
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

    def _draw_bars(ax, series, xvals=None, width=w, annotate=True, fs=5.5):
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
                    if abs(v) < 0.002 and not sig:
                        continue
                    off = 0.055 * span
                    label = f"{v:+.2f}" + ("*" if sig else "")
                    ax.text(b.get_x() + b.get_width() / 2.0, v + (off if v >= 0 else -off),
                            label, ha="center", va="bottom" if v >= 0 else "top",
                            fontsize=fs, color="0.15",
                            bbox=dict(boxstyle="square,pad=0.10", fc="white", ec="none", alpha=0.85))
        return artists

    for c, ds, metrics, labs, cap in metric_groups:
        ax = axes.flat[c]
        series = []
        for metric, lab in zip(metrics, labs):
            v, s = _vals_sig(ds, metric)
            series.append((v, lab, s))
        _draw_bars(ax, series, annotate=(ds != "U-Air"), fs=5.0)
        if ds == "U-Air":
            for j, (vals, lab, sigs) in enumerate(series):
                label = f"{vals[0]:+.2f}" + ("*" if sigs[0] else "")
                ax.text(x[0] + (j - 0.5) * w, vals[0] + (0.28 if vals[0] >= 0 else -0.28),
                        label, ha="center", va="bottom" if vals[0] >= 0 else "top",
                        fontsize=5.0, color="0.15",
                        bbox=dict(boxstyle="square,pad=0.08", fc="white", ec="none", alpha=0.85))
        flat = [v for vals, _, _ in series for v in vals]
        ymin, ymax = min(flat), max(flat)
        pad = max(0.18 * (ymax - ymin + 1e-6), 0.08 * max(abs(ymin), abs(ymax), 0.02))
        ax.set_ylim(ymin - pad, ymax + 1.55 * pad)
        ax.set_xticks(x)
        ax.set_xticklabels(COMPONENTS, fontsize=6.0)
        ax.set_ylabel("rel. change (%)", fontsize=7)
        ax.tick_params(axis="y", labelsize=6.0)
        _box(ax)
        loc = "upper right" if ds == "U-Air" else "best"
        leg = ax.legend(frameon=True, fancybox=False, edgecolor="0.3", loc=loc,
                        borderpad=0.2, handlelength=1.2, fontsize=5.0)
        leg.get_frame().set_linewidth(0.6)
        _panel_caption(ax, cap, compact=True)
    fig.tight_layout(h_pad=0.4, w_pad=0.3)
    fig.savefig(OUT / "fig5_e4_component_ablation.pdf")
    fig.savefig(OUT / "fig5_e4_component_ablation.png")
    plt.close(fig)


def fig6_uair_excl_design() -> None:
    """U-Air E4 ablation excluding the Design layer (1x2 magnified view).

    Reproduces the user-made fig6_e4_uair_excl_design with the panel titles
    moved from the top of each panel to directly below the image (xlabel),
    matching the panel-caption convention of figs 2-5.
    """
    df = pd.read_csv(SRC / "FIG_E4_E4_COMPONENT_ABLATION.csv")
    df = df[df["dataset"] == "U-Air"]
    comps = ["Obs", "Use", "Inst", "Debt"]
    xlabs = ["Obs", "Use", "Inst", "Debt"]
    x = np.arange(len(comps))
    w = 0.36
    fig, axes = plt.subplots(1, 2, figsize=(3.5, 2.25))

    def _series(metric):
        vals, sigs = [], []
        for comp in comps:
            hit = df[(df["component"] == comp) & (df["metric"] == metric)]
            vals.append(float(hit.iloc[0]["relative_change_percent"]))
            sigs.append(bool(hit.iloc[0]["holm_significant"]))
        return vals, sigs

    def _draw(ax, metrics, labels, ylim, yticks):
        for j, (metric, lab) in enumerate(zip(metrics, labels)):
            vals, sigs = _series(metric)
            bars = ax.bar(x + (j - 0.5) * w, vals, width=w, label=lab,
                          color=COLORS[j + 1], edgecolor="0.15", linewidth=0.6)
            for b in bars:
                b.set_hatch(HATCHES[j])
            for b, v, sig in zip(bars, vals, sigs):
                off = 0.012 * (ylim[1] - ylim[0])
                txt = (f"{v:+.2f}" if abs(v) >= 0.05 else f"{v:+.3f}") + ("*" if sig else "")
                ax.text(b.get_x() + b.get_width() / 2.0, v + (off if v >= 0 else -off),
                        txt, ha="center", va="bottom" if v >= 0 else "top",
                        fontsize=5.0, color="0.15",
                        bbox=dict(boxstyle="square,pad=0.08", fc="white", ec="none", alpha=0.85))
        ax.axhline(0.0, color="0.25", lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(xlabs, fontsize=6)
        ax.set_ylabel("rel. change (%)", fontsize=7)
        ax.tick_params(axis="y", labelsize=6)
        ax.set_ylim(*ylim)
        ax.set_yticks(yticks)
        _box(ax)
        leg = ax.legend(frameon=True, fancybox=False, edgecolor="0.3",
                        fontsize=5.0, handlelength=1.1, loc="best", borderpad=0.2)
        leg.get_frame().set_linewidth(0.5)

    _draw(axes[0], ["Delta_group", "Delta_c_s"],
          [r"$\Delta_{\mathrm{group}}$", r"$\Delta_{c,s}$"],
          (-0.25, 0.25), [-0.2, -0.1, 0.0, 0.1, 0.2])
    _panel_caption(axes[0], r"(a) Structural, excl.\ Design", compact=True)

    _draw(axes[1], ["RMSE_mu", "Tail_RMSE"],
          [r"$\mathrm{RMSE}_{\mu}$", "Tail RMSE"],
          (-0.06, 0.24), [-0.05, 0.00, 0.05, 0.10, 0.15, 0.20])
    _panel_caption(axes[1], r"(b) Prediction, excl.\ Design", compact=True)
    fig.tight_layout(w_pad=0.4)
    fig.savefig(OUT / "fig6_e4_uair_excl_design.pdf")
    fig.savefig(OUT / "fig6_e4_uair_excl_design.png")
    plt.close(fig)


def fig_w1_design_gate() -> None:
    df = pd.read_csv(SRC / "FIG_W1_DESIGN_GATE.csv")
    fig, axes = plt.subplots(1, 2, figsize=(3.5, 2.15))
    metrics = [
        (0, "Delta_group_pct", r"(a) $\Delta_{\mathrm{group}}$ vs No-Design"),
        (1, "RMSE_mu_pct", r"(b) $\mathrm{RMSE}_{\mu}$ vs No-Design"),
    ]
    datasets = ["SensorScope", "U-Air"]
    variants = ["Estimated", "Oracle"]
    x = np.arange(len(datasets))
    w = 0.36
    for c, col, cap in metrics:
        ax = axes[c]
        for j, var in enumerate(variants):
            vals = [
                float(df[(df["dataset"] == ds) & (df["variant"] == var)][col].iloc[0])
                for ds in datasets
            ]
            bars = ax.bar(
                x + (j - 0.5) * w, vals, width=w, label=var + " Design",
                color=COLORS[j + 1] if j == 0 else RAVEN_COLOR,
                edgecolor="0.15", linewidth=0.7,
            )
            for b in bars:
                b.set_hatch(HATCHES[j])
            for b, v in zip(bars, vals):
                ax.text(
                    b.get_x() + b.get_width() / 2.0,
                    v + (0.22 if v >= 0 else -0.22),
                    f"{v:+.2f}%", ha="center",
                    va="bottom" if v >= 0 else "top", fontsize=5.5, color="0.15",
                )
        ax.axhline(0.0, color="0.35", ls="--", lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(datasets, fontsize=6.5)
        ax.set_ylabel("rel. change (%)", fontsize=7)
        ax.tick_params(axis="y", labelsize=6)
        _box(ax)
        if c == 0:
            ax.legend(frameon=True, fancybox=False, edgecolor="0.3",
                      fontsize=5.5, handlelength=1.1, loc="upper left", borderpad=0.2)
        _panel_caption(ax, cap, compact=True)
    fig.tight_layout(w_pad=0.4)
    fig.savefig(OUT / "fig_w1_design_gate.pdf")
    fig.savefig(OUT / "fig_w1_design_gate.png")
    plt.close(fig)


def fig_g3_tdrive() -> None:
    mass = pd.read_csv(SRC / "FIG_G3_TDRIVE_H_MASS.csv")
    tv = pd.read_csv(SRC / "FIG_G3_TDRIVE_TV.csv")
    fig, axes = plt.subplots(1, 2, figsize=(3.5, 2.20))

    ax = axes[0]
    labels = mass["h_id"].tolist()
    x = np.arange(len(labels))
    w = 0.26
    series = [
        ("mu_test_seal", r"target $\mu$", COLORS[0], HATCHES[0]),
        ("pi_opp_real_R", r"real $R$", RAVEN_COLOR, HATCHES[-1]),
        ("pi_opp_balanced_unit", "unit-balanced", COLORS[1], HATCHES[1]),
    ]
    for j, (col, lab, fc, hatch) in enumerate(series):
        bars = ax.bar(
            x + (j - 1) * w, mass[col].to_numpy(), width=w, label=lab,
            color=fc, edgecolor="0.15", linewidth=0.7,
        )
        for b in bars:
            b.set_hatch(hatch)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=6.5)
    ax.set_ylabel("group mass", fontsize=7)
    ax.tick_params(axis="y", labelsize=6)
    ax.set_ylim(0, 0.78)
    ax.legend(frameon=True, fancybox=False, edgecolor="0.3",
              fontsize=5.2, handlelength=1.0, ncol=1, loc="upper left", borderpad=0.2)
    _box(ax)
    _panel_caption(ax, r"(a) Four-block masses on T-Drive", compact=True)

    ax = axes[1]
    names = tv["source"].tolist()
    vals = tv["tv_opp_vs_mu"].to_numpy()
    x = np.arange(len(names))
    bars = ax.bar(x, vals, width=0.55, color=[RAVEN_COLOR, COLORS[0], COLORS[1]],
                  edgecolor="0.15", linewidth=0.7)
    for i, b in enumerate(bars):
        b.set_hatch(HATCHES[-1] if i == 0 else HATCHES[i])
        ax.text(b.get_x() + b.get_width() / 2.0, vals[i] + 0.008,
                f"{vals[i]:.3f}", ha="center", va="bottom", fontsize=6, color="0.15")
    ax.axhline(0.05, color="0.45", ls=":", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(["T-Drive", "SS prot.", "UA prot."], fontsize=6)
    ax.set_ylabel(r"TV$(\pi^{\mathrm{opp}},\mu)$", fontsize=7)
    ax.tick_params(axis="y", labelsize=6)
    ax.set_ylim(0, 0.38)
    _box(ax)
    _panel_caption(ax, r"(b) Four-block opportunity--target TV", compact=True)

    fig.tight_layout(w_pad=0.4)
    fig.savefig(OUT / "fig_g3_tdrive_h_mass.pdf")
    fig.savefig(OUT / "fig_g3_tdrive_h_mass.png")
    plt.close(fig)


def fig_certificate() -> None:
    """Coverage-stress audit of Design_t := Gate_t (CERTIFIED windows + primary track)."""
    win = pd.read_csv(LOCAL / "FIG_CERTIFICATE_WINDOWS.csv")
    cert = win[win["state_before_decision"] == "CERTIFIED"].copy()
    fig, axes = plt.subplots(1, 2, figsize=(7.16, 2.55))

    ax = axes[0]
    ss = cert[cert["dataset"] == "sensorscope"]
    ua = cert[cert["dataset"] == "uair"]
    ax.scatter(
        ss["C_t"], ss["C_LCB"], s=14, marker="o", facecolors="none",
        edgecolors=RAVEN_COLOR, linewidths=0.7, label="SensorScope",
        zorder=3,
    )
    ax.scatter(
        ua["C_t"], ua["C_LCB"], s=16, marker="s", facecolors="none",
        edgecolors=COLORS[0], linewidths=0.7, label="U-Air",
        zorder=3,
    )
    lo = 0.0
    hi = max(float(cert["C_t"].max()), float(cert["C_LCB"].max()), 0.20)
    ax.plot([lo, hi], [lo, hi], color="0.55", lw=0.7, ls="--", zorder=1)
    ax.axhline(0.05, color="0.25", ls=":", lw=0.8, zorder=2)
    ax.axvline(0.05, color="0.25", ls=":", lw=0.8, zorder=2)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel(r"$C_t$", fontsize=8)
    ax.set_ylabel(r"$C^{\mathrm{LCB}}_t$", fontsize=8)
    ax.legend(frameon=False, loc="upper left", fontsize=7, handletextpad=0.3)
    _box(ax)
    _panel_caption(ax, r"(a) CERTIFIED windows", compact=True)

    ax = axes[1]
    tr = win[
        (win["dataset"] == "sensorscope") & (win["availability_level"] == 0.4)
    ].sort_values("window_id")
    x = tr["window_id"].to_numpy()
    warmup = tr["state_before_decision"].eq("WARMUP").to_numpy()
    reset = tr["state_before_decision"].eq("RESET").to_numpy()
    in_band = False
    start = 0
    for i, flag in enumerate(warmup):
        if flag and not in_band:
            start = i
            in_band = True
        elif not flag and in_band:
            ax.axvspan(x[start] - 0.5, x[i - 1] + 0.5, color="0.88", lw=0, zorder=0)
            in_band = False
    if in_band:
        ax.axvspan(x[start] - 0.5, x[-1] + 0.5, color="0.88", lw=0, zorder=0)
    rst_idx = np.flatnonzero(reset)
    if len(rst_idx):
        ax.axvspan(
            x[rst_idx[0]] - 0.5, x[rst_idx[-1]] + 0.5,
            color="#E8D4D4", lw=0, zorder=0,
        )
    ax.plot(x, tr["C_t"], color=RAVEN_COLOR, lw=1.1, label=r"$C_t$")
    ax.plot(x, tr["C_hat"], color=COLORS[0], lw=0.9, ls="--", label=r"$\widehat C_t$")
    ax.plot(x, tr["C_LCB"], color=COLORS[1], lw=1.1, label=r"$C^{\mathrm{LCB}}_t$")
    ax.axhline(0.05, color="0.25", ls=":", lw=0.8)
    trig = tr[tr["reset_trigger_after_window"].astype(int) == 1]
    if len(trig):
        ax.scatter(
            trig["window_id"], trig["C_LCB"], marker="x", s=28,
            color="#8C3A3A", linewidths=0.9, zorder=4, label="RESET trigger",
        )
    ax.set_xlim(-1, float(x.max()) + 1)
    ax.set_ylim(0.0, 0.10)
    ax.set_xlabel("window", fontsize=8)
    ax.set_ylabel("coverage", fontsize=8)
    ax.legend(frameon=False, loc="upper right", fontsize=6.5, ncol=2, columnspacing=0.6)
    _box(ax)
    _panel_caption(ax, r"(b) SensorScope, $a=0.40$", compact=True)

    fig.tight_layout(w_pad=0.55)
    fig.savefig(OUT / "fig_certificate_audit.pdf")
    fig.savefig(OUT / "fig_certificate_audit.png")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _style()
    fig1_framework()
    fig2_e2()
    fig3_structural()
    fig4_prediction()
    fig5_ablation()
    fig6_uair_excl_design()
    fig_w1_design_gate()
    fig_g3_tdrive()
    fig_certificate()
    print("wrote", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
