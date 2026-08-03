#!/usr/bin/env python3
"""Read-only diagnostics for the retained E1 formal weight-safety failure.

This command never invokes training, regenerates EventTrace, or writes inside
the formal run directory.  It reconstructs stage-1 weights from persisted
pre-update zeta/p vectors and frozen safety parameters.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUN_NAME = "E1_FORMAL_fedavg_window_26001_20260802_154112_605315"
EPS = 1e-12


def _hash_frame(frame: pd.DataFrame, columns: list[str]) -> str:
    payload = frame.loc[:, columns].sort_values(columns).to_json(
        orient="records", date_format="iso", double_precision=15,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _run_path(value: str | None) -> Path:
    run = Path(value) if value else ROOT / "outputs/runs" / RUN_NAME
    run = run.resolve()
    if run.name != RUN_NAME:
        raise ValueError(f"diagnostic is frozen to {RUN_NAME}")
    return run


def reconstruct(run: Path, output: Path) -> pd.DataFrame:
    """Reconstruct one risk-row per persisted p/zeta element."""
    resolved = json.loads((run / "resolved_config.yaml").read_text()) if False else None
    # YAML is intentionally read through the project's loader to preserve types.
    from raven_mcs.utils.serialization import load_yaml

    safety = load_yaml(run / "resolved_config.yaml")["weight_safety"]
    a_max, p_min, pi_min = (
        float(safety["a_max"]), float(safety["p_min"]), float(safety["pi_min"])
    )
    diag = pd.read_parquet(run / "method_diagnostics.parquet")
    history = pd.read_parquet(run / "p_propensity_history.parquet")
    trace = pd.read_parquet(ROOT / "outputs/event_traces/e1_balanced_seed26001/events.parquet")
    rows: list[dict] = []
    for item in diag.itertuples(index=False):
        window_id, client_id = int(item.window_id), str(item.client_id)
        hist = history.loc[
            (history["window_id"] == window_id) & (history["client_id"] == client_id)
        ].sort_values("unit_id")
        event = trace.loc[
            (trace["window_id"] == window_id) & (trace["client_id"] == client_id)
        ]
        if len(event) != 1:
            raise RuntimeError(f"missing EventTrace row for {window_id}/{client_id}")
        # History insertion and runner calculation both use the EventTrace risk order.
        ids = json.loads(event.iloc[0]["risk_set_unit_ids"])
        hist = hist.set_index("unit_id").reindex(ids).reset_index()
        zeta, p_hat = np.asarray(item.zeta_hat, dtype=float), np.asarray(item.p_hat, dtype=float)
        if len(hist) != len(zeta) or len(zeta) != len(p_hat):
            raise RuntimeError(f"risk identity/vector mismatch for {window_id}/{client_id}")
        raw = zeta / np.maximum(p_hat, p_min)
        clipped = np.minimum(a_max, raw)
        attempted, usable = int(event.iloc[0]["attempted"]), int(event.iloc[0]["usable"])
        for i, source in hist.iterrows():
            unit_id = str(source["unit_id"])
            # target group is frozen UTC mapping.  Unit id time indices are 30-minute slots.
            time_index = int(unit_id.rsplit("_t", 1)[1])
            target_group = int((time_index % 48) // 12)
            record_hash = hashlib.sha256(
                f"{window_id}|{client_id}|{unit_id}".encode("utf-8")
            ).hexdigest()
            rows.append({
                "seed": 26001, "window_id": window_id, "client_id": client_id,
                "unit_id": unit_id, "target_group": target_group,
                "opportunity_stratum": str(source["opportunity_stratum"]),
                "attempted": attempted, "observed": int(source["O"]), "usable": usable,
                "p_hat_obs": float(p_hat[i]), "p_floor_hit": bool(p_hat[i] <= p_min + EPS),
                "pi_opp_hat": np.nan, "pi_floor_hit": False, "nu_opp_hat": np.nan,
                "nu_floor_hit": False, "zeta_hat": float(zeta[i]),
                "raw_weight_u": float(raw[i]), "clipped_weight_a": float(clipped[i]),
                "true_exceed": bool(raw[i] > a_max + EPS),
                "exact_boundary": bool(abs(raw[i] - a_max) <= EPS),
                "at_or_above": bool(raw[i] >= a_max - EPS),
                "excess_amount": float(max(raw[i] - a_max, 0.0)),
                "excess_ratio": float(raw[i] / a_max),
                "warmup": bool(window_id < 5), "active_window": True,
                "record_identity_hash": record_hash,
            })
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("reconstructed record table is empty")
    # Join post-close opportunity diagnostics for attribution only; zeta itself is
    # reconstructed from persisted pre-update zeta vectors.
    opp = pd.read_parquet(run / "opportunity_ema_diagnostics.parquet")
    latest = opp[["window_id", "client_id", "stratum_id", "pi_hat_opp"]].rename(
        columns={"stratum_id": "opportunity_stratum", "pi_hat_opp": "pi_opp_hat_postclose"}
    )
    frame = frame.merge(latest, on=["window_id", "client_id", "opportunity_stratum"], how="left")
    frame["pi_opp_hat"] = frame.pop("pi_opp_hat_postclose")
    frame["pi_floor_hit"] = frame["pi_opp_hat"].fillna(np.inf) <= pi_min + EPS
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    return frame


def _rate(frame: pd.DataFrame, event: str) -> tuple[int, int, float]:
    return int(frame[event].sum()), len(frame), float(frame[event].mean()) if len(frame) else np.nan


def definitions(frame: pd.DataFrame, output: Path) -> pd.DataFrame:
    populations = {
        "risk_micro": frame,
        "observed_micro": frame.loc[frame["observed"] == 1],
        "attempt_risk_micro": frame.loc[frame["attempted"] == 1],
        "attempt_observed_micro": frame.loc[(frame["attempted"] == 1) & (frame["observed"] == 1)],
        "client_window_macro": frame,
        "window_risk_macro": frame,
        "window_observed_macro": frame.loc[frame["observed"] == 1],
    }
    rows: list[dict] = []
    for event in ("true_exceed", "exact_boundary", "at_or_above"):
        for name, population in populations.items():
            if name == "client_window_macro":
                parts = population.groupby(["window_id", "client_id"], sort=True)[event].mean()
                numerator, denominator, value = float(parts.sum()), len(parts), float(parts.mean())
                aggregation = "client-window macro over attempted clients"
            elif name.startswith("window_"):
                parts = population.groupby("window_id", sort=True)[event].mean()
                numerator, denominator, value = float(parts.sum()), len(parts), float(parts.mean())
                aggregation = "active-window macro"
            else:
                numerator, denominator, value = _rate(population, event)
                aggregation = "record micro"
            rows.append({
                "metric_name": f"c_{name}_{event}", "population": name,
                "aggregation": aggregation, "comparison_operator": event,
                "numerator": numerator, "denominator": denominator, "value": value,
                "threshold": 0.05, "pass_under_5_percent": bool(value <= .05),
                "intended_use": "diagnostic; production gate remains unchanged",
            })
    result = pd.DataFrame(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output.with_suffix(".csv"), index=False)
    output.write_text(json.dumps(result.to_dict(orient="records"), indent=2) + "\n", encoding="utf-8")
    return result


def decomposition(frame: pd.DataFrame, output: Path) -> None:
    def summarize(keys: list[str]) -> pd.DataFrame:
        g = frame.groupby(keys, dropna=False)
        result = g.agg(
            row_count=("unit_id", "size"), observed_count=("observed", "sum"),
            exceed_count=("true_exceed", "sum"), exceed_rate=("true_exceed", "mean"),
            p_floor_share=("p_floor_hit", "mean"), opportunity_floor_share=("pi_floor_hit", "mean"),
            mean_zeta=("zeta_hat", "mean"), p95_zeta=("zeta_hat", lambda x: x.quantile(.95)),
            mean_raw_weight=("raw_weight_u", "mean"), p95_raw_weight=("raw_weight_u", lambda x: x.quantile(.95)),
        ).reset_index()
        return result
    output.mkdir(parents=True, exist_ok=True)
    summarize(["window_id"]).to_parquet(output / "E1_WEIGHT_SAFETY_BY_WINDOW.parquet", index=False)
    by_block = frame.assign(window_block=((frame.window_id // 20) + 1).astype(int))
    summarize_block = by_block.groupby("window_block").agg(
        risk_true_exceed_rate=("true_exceed", "mean"),
        obs_true_exceed_rate=("true_exceed", lambda s: np.nan), # filled below
        p_floor_hit_rate=("p_floor_hit", "mean"), pi_floor_hit_rate=("pi_floor_hit", "mean"),
        median_zeta=("zeta_hat", "median"), p95_zeta=("zeta_hat", lambda x: x.quantile(.95)),
        p99_zeta=("zeta_hat", lambda x: x.quantile(.99)), median_raw_weight=("raw_weight_u", "median"),
        p95_raw_weight=("raw_weight_u", lambda x: x.quantile(.95)), p99_raw_weight=("raw_weight_u", lambda x: x.quantile(.99)),
    ).reset_index()
    obs = by_block.loc[by_block.observed == 1].groupby("window_block").true_exceed.mean()
    summarize_block["obs_true_exceed_rate"] = summarize_block.window_block.map(obs)
    summarize_block.to_csv(output / "E1_WEIGHT_SAFETY_BY_20WINDOW_BLOCK.csv", index=False)
    summarize(["client_id"]).to_csv(output / "E1_WEIGHT_SAFETY_BY_CLIENT.csv", index=False)
    summarize(["opportunity_stratum"]).to_csv(output / "E1_WEIGHT_SAFETY_BY_STRATUM.csv", index=False)
    summarize(["target_group"]).to_csv(output / "E1_WEIGHT_SAFETY_BY_TARGET_GROUP.csv", index=False)
    summarize(["warmup"]).to_csv(output / "E1_WEIGHT_SAFETY_WARMUP_COMPARISON.csv", index=False)
    top = frame.loc[frame.true_exceed].sort_values("raw_weight_u", ascending=False).head(100)
    top.to_csv(output / "E1_WEIGHT_SAFETY_TOP_EXCEED_RECORDS.csv", index=False)
    cause = np.select(
        [top.p_floor_hit, top.pi_floor_hit, top.zeta_hat >= 1.0],
        ["P_FLOOR_DOMINANT", "PI_OPP_FLOOR_DOMINANT", "LARGE_TARGET_RATIO"],
        default="OTHER",
    )
    top = top.assign(cause_category=cause)
    causes = top.groupby("cause_category").agg(
        count=("unit_id", "size"), mean_excess_amount=("excess_amount", "mean")
    ).reset_index()
    total_exceed = int(frame.true_exceed.sum())
    causes["share_of_exceed"] = causes["count"] / total_exceed if total_exceed else 0.0
    causes["share_of_all_records"] = causes["count"] / len(frame)
    causes.to_csv(output / "E1_WEIGHT_SAFETY_CAUSE_ATTRIBUTION.csv", index=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/diagnostics")
    args = parser.parse_args()
    run, out = _run_path(args.run_dir), args.output_dir
    records = reconstruct(run, out / "E1_WEIGHT_SAFETY_RECORD_LEVEL.parquet")
    metrics = definitions(records, out / "E1_WEIGHT_SAFETY_CLIP_DEFINITIONS.json")
    decomposition(records, out)
    reported = json.loads((run / "metrics_run.json").read_text())["first_stage_clip_rate"]
    current = records.groupby(["window_id", "client_id"]).at_or_above.mean().groupby("window_id").mean().mean()
    audit = {
        "run_dir": str(run.relative_to(ROOT)).replace("\\", "/"),
        "reported_first_stage_clip_rate": reported,
        "recomputed_production_at_or_above_macro": float(current),
        "reproduction_match": bool(abs(current - reported) <= 1e-12),
        "record_count": len(records),
        "record_identity_hash": _hash_frame(records, ["window_id", "client_id", "unit_id"]),
        "clipped_weight_hash": _hash_frame(records, ["window_id", "client_id", "unit_id", "clipped_weight_a"]),
        "metrics": metrics.to_dict(orient="records"),
    }
    (out / "E1_WEIGHT_SAFETY_RECONSTRUCTION_AUDIT.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    if not audit["reproduction_match"]:
        raise RuntimeError("DIAG-G1 failed: current clip rate did not reproduce")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
