"""G6 scoring: RMSE_g* from frozen GSTAR.json + G2 per-seed blocks. No new training."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
TAB = OUT / "tables"
G2_CSV = ROOT / "post_review" / "G2_external_baselines" / "tables" / "per_seed.csv"
GSTAR_PATH = OUT / "GSTAR.json"
VAL_SEEDS = list(range(30001, 30011))
TEST_SEEDS = list(range(30011, 30021))
DATASETS = ("sensorscope", "uair")
GATED = {"sensorscope": "raven", "uair": "raven_wo_design"}
STRONG = ("fedau_window", "obsuse_window")
COPY = ("twostage_hajek", "raven_wo_design", "fedavg_window", "raven")
MPID = 0.5


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _pct(new: float, ref: float) -> float:
    if ref is None or not np.isfinite(ref) or abs(float(ref)) < 1e-15:
        return float("nan")
    return 100.0 * (float(new) - float(ref)) / float(ref)


def _mean_ci(vals: np.ndarray) -> tuple[float, float, float]:
    vals = np.asarray(vals, dtype=np.float64)
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return float("nan"), float("nan"), float("nan")
    mean = float(vals.mean())
    se = float(vals.std(ddof=1) / np.sqrt(vals.size)) if vals.size > 1 else 0.0
    return mean, mean - 1.96 * se, mean + 1.96 * se


def load_gstar() -> dict:
    if not GSTAR_PATH.is_file():
        raise FileNotFoundError("GSTAR.json missing; refuse to score")
    payload = _load_json(GSTAR_PATH)
    if payload.get("scored") is True:
        raise RuntimeError("GSTAR.json marked scored; refuse to re-pick g*")
    for dataset in DATASETS:
        rec = payload["datasets"][dataset]
        if "g_star" not in rec:
            raise RuntimeError(f"GSTAR missing g_star for {dataset}")
        if int(rec["g_star"]) not in {0, 1, 2, 3}:
            raise RuntimeError(f"illegal g_star {rec['g_star']}")
    return payload


def attach_gstar(frame: pd.DataFrame, gstar: dict) -> pd.DataFrame:
    out = frame.copy()
    stars = []
    vals = []
    for rec in out.itertuples(index=False):
        g = int(gstar["datasets"][str(rec.dataset)]["g_star"])
        col = f"RMSE_block{g}"
        stars.append(g)
        vals.append(float(getattr(rec, col)))
    out["g_star"] = stars
    out["RMSE_gstar"] = vals
    return out


def paired_table(frame: pd.DataFrame, seeds: list[int], split: str, baselines: tuple[str, ...]) -> pd.DataFrame:
    from raven_mcs.e3.formal.stats import holm, wilcoxon_signed_rank_two_sided

    rows = []
    for dataset in DATASETS:
        g = frame[
            (frame.dataset == dataset)
            & (frame.method == "raven_gated")
            & (frame.seed.isin(seeds))
            & (frame.status == "OK")
        ].set_index("seed")
        raw_p = {}
        tmp = []
        for base in baselines:
            b = frame[
                (frame.dataset == dataset)
                & (frame.method == base)
                & (frame.seed.isin(seeds))
                & (frame.status == "OK")
            ].set_index("seed")
            common = sorted(set(g.index) & set(b.index))
            diffs = [float(g.loc[s, "RMSE_gstar"] - b.loc[s, "RMSE_gstar"]) for s in common]
            pcts = [_pct(float(g.loc[s, "RMSE_gstar"]), float(b.loc[s, "RMSE_gstar"])) for s in common]
            p, stat = wilcoxon_signed_rank_two_sided(diffs)
            raw_p[base] = p
            mean_pct, lo, hi = _mean_ci(np.asarray(pcts))
            tmp.append(
                {
                    "split": split,
                    "dataset": dataset,
                    "baseline": base,
                    "n": len(common),
                    "gated_mean": float(g.loc[common, "RMSE_gstar"].mean()) if common else float("nan"),
                    "base_mean": float(b.loc[common, "RMSE_gstar"].mean()) if common else float("nan"),
                    "mean_pct_gated_minus_base": mean_pct,
                    "pct_ci95_low": lo,
                    "pct_ci95_high": hi,
                    "p_raw": p,
                    "test": stat,
                    "win": bool(mean_pct <= -MPID) if base in STRONG else None,
                    "no_harm": bool(mean_pct <= MPID) if base in STRONG else None,
                }
            )
        adj = holm({k: raw_p[k] for k in STRONG if k in raw_p})
        for row in tmp:
            if row["baseline"] in adj:
                row["p_holm"] = adj[row["baseline"]]
            rows.append(row)
    return pd.DataFrame(rows)


def _dataset_verdict(paired: pd.DataFrame, dataset: str) -> dict:
    sub = paired[(paired.dataset == dataset) & (paired.baseline.isin(STRONG))]
    by_base = {str(r.baseline): r for r in sub.itertuples(index=False)}
    missing = [b for b in STRONG if b not in by_base]
    if missing:
        return {
            "dataset": dataset,
            "win": False,
            "no_harm": False,
            "missing": missing,
        }
    win = all(bool(by_base[b].win) for b in STRONG)
    no_harm = all(bool(by_base[b].no_harm) for b in STRONG)
    return {
        "dataset": dataset,
        "win": win,
        "no_harm": no_harm,
        "vs_fedau_pct": float(by_base["fedau_window"].mean_pct_gated_minus_base),
        "vs_obsuse_pct": float(by_base["obsuse_window"].mean_pct_gated_minus_base),
    }


def val_gate(frame: pd.DataFrame, paired_val: pd.DataFrame, gstar: dict) -> dict:
    checks = []
    methods = sorted(frame.method.unique())
    finite_ok = True
    for dataset in DATASETS:
        for method in methods:
            n_ok = int(
                (
                    (frame.dataset == dataset)
                    & (frame.method == method)
                    & (frame.seed.isin(VAL_SEEDS))
                    & (frame.status == "OK")
                    & np.isfinite(frame.RMSE_gstar)
                ).sum()
            )
            ok = n_ok == len(VAL_SEEDS)
            finite_ok = finite_ok and ok
            checks.append(
                {
                    "rule": f"{dataset}_{method}_finite_val",
                    "n": n_ok,
                    "pass": ok,
                }
            )
    per_ds = {d: _dataset_verdict(paired_val, d) for d in DATASETS}
    ss, ua = per_ds["sensorscope"], per_ds["uair"]
    family = bool((ss["win"] and ua["no_harm"]) or (ua["win"] and ss["no_harm"]))
    if not finite_ok:
        verdict = "G6_VAL_INCOMPLETE"
    elif family:
        verdict = "G6_VAL_FAMILY_SUCCESS"
    else:
        verdict = "G6_RECORDED_NEGATIVE"
    return {
        "verdict": verdict,
        "family_success": family and finite_ok,
        "g_star": {d: int(gstar["datasets"][d]["g_star"]) for d in DATASETS},
        "datasets": per_ds,
        "checks": checks,
        "mpid": MPID,
        "rule": "win: mean paired d_m <= -0.5% vs fedau AND obsuse; no-harm: <= +0.5%; family: win one and no-harm the other",
    }


def copy_matrix(paired: pd.DataFrame) -> pd.DataFrame:
    keep = paired[paired.baseline.isin(STRONG + COPY)].copy()
    return keep


def score(split: str) -> dict:
    gstar = load_gstar()
    raw = pd.read_csv(G2_CSV)
    frame = attach_gstar(raw, gstar)
    if split == "val":
        seeds = VAL_SEEDS
        paired = paired_table(frame, seeds, "val", STRONG + COPY)
        gate = val_gate(frame, paired, gstar)
        return {
            "split": "val",
            "gate": gate,
            "paired": paired.to_dict("records"),
            "per_seed": frame[frame.seed.isin(seeds)].to_dict("records"),
        }
    if split == "test":
        seeds = TEST_SEEDS
        paired = paired_table(frame, seeds, "test", STRONG + COPY)
        per_ds = {d: _dataset_verdict(paired, d) for d in DATASETS}
        ss, ua = per_ds["sensorscope"], per_ds["uair"]
        family = bool((ss["win"] and ua["no_harm"]) or (ua["win"] and ss["no_harm"]))
        return {
            "split": "test",
            "gate": {
                "verdict": "G6_TEST_FAMILY_SUCCESS" if family else "G6_VAL_ONLY",
                "family_success": family,
                "g_star": {d: int(gstar["datasets"][d]["g_star"]) for d in DATASETS},
                "datasets": per_ds,
            },
            "paired": paired.to_dict("records"),
            "per_seed": frame[frame.seed.isin(seeds)].to_dict("records"),
        }
    raise ValueError(split)


def main() -> None:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--split", choices=("val", "test"), default="val")
    args = p.parse_args()
    print(json.dumps(score(args.split), indent=2, default=str))


if __name__ == "__main__":
    main()
