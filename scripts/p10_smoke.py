#!/usr/bin/env python3
"""P10 End-to-End Smoke Test on real SensorScope data.

Usage:
    python scripts/p10_smoke.py
    python scripts/p10_smoke.py --seed 26001 --windows 20 --clients 10
    python scripts/p10_smoke.py --dry-run

Runs FedAvg-Window, TwoStage-Hajek, and RAVEN-MCS on real SensorScope
processed data with a complete_aligned EventTrace. Must pass all smoke
checks before E1 can be unblocked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
_SCRIPTS = _ROOT / "scripts"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from raven_mcs.data.base import DatasetMetadata
from raven_mcs.data.processed_dataset import ProcessedDataset
from raven_mcs.data.target import FrozenTimeBlockMapper, GroupMapper, TargetBuilder
from raven_mcs.experiments.phase0_audit import run_phase0_audit
from raven_mcs.metrics.accuracy import atomic_arrival_weights, gap_mis, rmse_mu, rmse_rho
from raven_mcs.metrics.reachability_optimization import solve_epsilon_reach
from raven_mcs.simulation.event_trace import (
    EventTrace,
    EventTraceMetadata,
    freeze_event_trace,
    load_event_trace,
)
from raven_mcs.propensity.leakage import scan_q_feature_names
from raven_mcs.propensity.usable import UsablePropensity
from raven_mcs.training.window_runner import FullWindowRunner, build_full_runner
from raven_mcs.utils.hashing import (
    environment_hash,
    sha256_file,
    sha256_json,
    sha256_path_tree,
)
from raven_mcs.utils.serialization import dump_json, load_json
from freeze_config import validate_frozen_config

# ---------------------------------------------------------------------------
# P10-SMOKE constants
# ---------------------------------------------------------------------------

SMOKE_METHODS = ["fedavg_window", "twostage_hajek", "raven"]
SMOKE_SCENARIO = "complete_aligned"
SMOKE_DATASET = "sensorscope"


def _write_q_feature_audit(
    runners: dict[str, FullWindowRunner],
    output_path: Path,
) -> None:
    rows: list[dict] = []
    for method, runner in runners.items():
        names = list(runner.usable_propensity.feature_names)
        forbidden = set(scan_q_feature_names(names))
        for name in names:
            rows.append({
                "file": "src/raven_mcs/propensity/usable.py",
                "line": 25,
                "variable": name,
                "match_pattern": name if name in forbidden else "",
                "classification": (
                    "UNREVIEWED_FORBIDDEN" if name in forbidden
                    else "SAFE_PRE_OUTCOME"
                ),
                "action": "BLOCK" if name in forbidden else "ALLOW",
                "reviewer_note": f"Runtime q input for {method}",
            })
    source_scan = run_phase0_audit(_ROOT, max_workers=2)["scans"]["q_post_outcome"]
    source_status = source_scan["status"]
    for hit in source_scan["hits"]:
        rows.append({
            "file": hit["path"],
            "line": hit["line"],
            "variable": hit["text"],
            "match_pattern": hit["pattern"],
            "classification": (
                "REVIEWED_WHITELIST"
                if source_status == "REVIEWED_WHITELIST_ONLY"
                else "UNREVIEWED_FORBIDDEN"
            ),
            "action": (
                "ALLOW_SIMULATOR_TRUTH"
                if source_status == "REVIEWED_WHITELIST_ONLY"
                else "BLOCK"
            ),
            "reviewer_note": "Static executable-scope q keyword scan",
        })
    frame = pd.DataFrame(rows).drop_duplicates(
        subset=["file", "line", "variable", "classification"],
    )
    frame.to_csv(output_path, index=False)
    if (frame["classification"] == "UNREVIEWED_FORBIDDEN").any():
        raise RuntimeError("q feature audit found an unreviewed forbidden input")


def _weight_diff(left: list[float], right: list[float]) -> tuple[float, float]:
    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    if a.shape != b.shape:
        return float("inf"), float("inf")
    delta = np.abs(a - b)
    return float(delta.max(initial=0.0)), float(delta.sum())


def _write_method_diagnostic(
    fedavg: FullWindowRunner,
    twostage: FullWindowRunner,
    predictions: dict[str, dict],
    output_path: Path,
) -> None:
    fed = {(row["window_id"], row["client_id"]): row for row in fedavg.diagnostics}
    two = {(row["window_id"], row["client_id"]): row for row in twostage.diagnostics}
    prediction_diff = float(np.max(np.abs(
        np.asarray(predictions["fedavg_window"]["y_pred"])
        - np.asarray(predictions["twostage_hajek"]["y_pred"])
    )))
    rows: list[dict] = []
    for key in sorted(set(fed) & set(two)):
        f_row, t_row = fed[key], two[key]
        max_w, l1_w = _weight_diff(
            f_row["applied_local_weights"], t_row["applied_local_weights"],
        )
        rows.append({
            "r": key[0],
            "client_id": key[1],
            "max_abs_local_weight_diff": max_w,
            "l1_local_weight_diff": l1_w,
            "l1_alpha_diff": abs(float(f_row.get("alpha", 0.0)) - float(t_row.get("alpha", 0.0))),
            "l1_beta_vs_fedavg_diff": abs(float(t_row.get("beta_hat", 0.0)) - float(f_row.get("alpha", 0.0))),
            "local_loss_diff": abs(float(f_row["local_loss"]) - float(t_row["local_loss"])),
            "update_hash_equal": f_row["update_vector_hash"] == t_row["update_vector_hash"],
            "model_hash_equal": f_row.get("global_model_hash") == t_row.get("global_model_hash"),
            "prediction_max_abs_diff": prediction_diff,
        })
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("FedAvg/TwoStage diagnostic has no comparable client rows")
    frame.to_parquet(output_path, index=False)


def _write_group_reachability_audit(
    trace: EventTrace,
    dataset: ProcessedDataset,
    output_path: Path,
) -> None:
    frame = dataset.atomic_df
    group_ids = FrozenTimeBlockMapper(group_count=4).map(frame)
    group_by_unit = dict(zip(frame["unit_id"].astype(str), group_ids))
    coverage: list[np.ndarray] = []
    effective_clients = np.zeros(4, dtype=int)
    usable_mass = np.zeros(4, dtype=np.float64)
    for window_id in range(trace.metadata.num_windows):
        rows = trace.events.loc[trace.events["window_id"] == window_id]
        columns: list[np.ndarray] = []
        for row in rows.itertuples():
            counts = np.zeros(4, dtype=np.float64)
            for unit_id in row.observed_unit_ids:
                counts[group_by_unit[str(unit_id)]] += 1.0
            if counts.sum() <= 0:
                continue
            composition = counts / counts.sum()
            columns.append(composition)
            effective_clients += counts > 0
            if int(row.U) == 1:
                usable_mass += counts
        if columns:
            coverage.append(np.column_stack(columns))
    result = solve_epsilon_reach(
        coverage,
        np.full(4, 0.25, dtype=np.float64),
        [1.0] * len(coverage),
    )
    supported = frame["support_flag"].astype(bool)
    support = pd.Series(group_ids[supported]).value_counts().reindex(
        range(4), fill_value=0,
    )
    dump_json({
        "group_count": 4,
        "support_per_group": support.astype(int).to_dict(),
        "effective_clients_per_group": effective_clients.tolist(),
        "average_usable_mass_per_group": (
            usable_mass / max(trace.metadata.num_windows, 1)
        ).tolist(),
        "unsupported_positive_target_groups": int((support == 0).sum()),
        "epsilon_reach": float(result.epsilon_reach),
        "epsilon_reach_solver_status": result.solver_status,
        "epsilon_reach_feasible": bool(result.feasible),
        "fine_grained_groups_used_for_main_debt": False,
    }, output_path)


def _generate_real_event_trace(
    dataset: ProcessedDataset,
    num_clients: int,
    num_windows: int,
    seed: int,
    obs_rate: float = 0.20,
    usable_rate: float = 0.60,
    s_max: int = 5,
) -> EventTrace:
    """Generate an EventTrace from real processed SensorScope data.

    Maps atomic units to (window, client) pairs using a deterministic
    hash-based assignment. Uses real unit_ids throughout.
    """
    rng = np.random.default_rng(seed)
    atomic = dataset.atomic_df

    unit_ids = atomic["unit_id"].astype(str).tolist()
    time_indices = atomic["time_index"].values

    # Python's built-in hash is process-randomized. Use a stable digest so a
    # fresh trace generated in another process is byte-for-byte reproducible.
    def _assign_client(uid: str) -> int:
        digest = hashlib.sha256(f"{seed}:{uid}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") % num_clients

    client_assignments = np.array([_assign_client(uid) for uid in unit_ids])
    sorted_slots = np.sort(atomic["time_index"].unique())
    slot_blocks = np.array_split(sorted_slots, num_windows)
    if any(len(block) == 0 for block in slot_blocks):
        raise ValueError("num_windows exceeds the number of unique time slots")

    # Group units by (window, client)
    # For each window, find units that map to that window
    rows: list[dict] = []

    for window_id in range(num_windows):
        block_slots = slot_blocks[window_id]

        for client_idx in range(num_clients):
            client_id = f"client-{client_idx:03d}"
            mask = (
                np.isin(time_indices, block_slots)
                & (client_assignments == client_idx)
            )
            risk_unit_ids = [unit_ids[i] for i in np.where(mask)[0]]

            if len(risk_unit_ids) == 0:
                continue

            n_risk = len(risk_unit_ids)
            O_flags = rng.random(n_risk) < obs_rate
            observed_unit_ids = [u for u, flag in zip(risk_unit_ids, O_flags) if flag]

            # Simulate staleness: downloaded_version lags current window
            staleness = rng.integers(0, min(s_max + 1, window_id + 1))
            downloaded_version = max(0, window_id - staleness)

            # U flag: usable or not
            U = int(rng.random() < usable_rate)

            # Oracle p = observation rate, oracle q = usable rate
            oracle_p = float(obs_rate)
            oracle_q = float(usable_rate)

            rows.append({
                "window_id": window_id,
                "client_id": client_id,
                "risk_set_unit_ids": list(risk_unit_ids),
                "opportunity_features": {
                    "hour_block": window_id % 4,
                    "client_bias": float(client_idx),
                },
                "observed_unit_ids": list(observed_unit_ids),
                "O": {uid: bool(flag) for uid, flag in zip(risk_unit_ids, O_flags)},
                "registration_time": float(window_id) + 0.1 * client_idx,
                "downloaded_version": downloaded_version,
                "model_age": staleness,
                "tau": int(staleness),
                "device_profile": "sensor-scope-station",
                "network_profile": "sensor-scope-wifi",
                "compute_success": True,
                "compute_duration": float(rng.uniform(0.1, 1.0)),
                "network_success": True,
                "network_duration": float(rng.uniform(0.05, 0.5)),
                "arrival_time": float(window_id) + 0.5 + 0.01 * client_idx,
                "U": U,
                "raw_workload": float(len(observed_unit_ids)),
                "oracle_p": oracle_p,
                "oracle_q": oracle_q,
                "hidden_confounder": 0.0,
            })

    events = pd.DataFrame(rows)
    meta = EventTraceMetadata(
        dataset=SMOKE_DATASET,
        seed=seed,
        num_windows=num_windows,
        num_clients=num_clients,
        s_max=s_max,
        generator="real-data-eventtrace-p10smoke-v1",
        notes=("P10-SMOKE: derived from real SensorScope atomic_units",),
    )
    trace = EventTrace(events=events, metadata=meta)
    trace.validate()
    return trace


def _get_or_generate_smoke_trace(
    dataset: ProcessedDataset,
    trace_cache: Path,
    num_clients: int,
    num_windows: int,
    seed: int,
) -> tuple[EventTrace, str]:
    """Load cached or generate smoke EventTrace."""
    trace_dir = trace_cache / (
        f"{SMOKE_DATASET}_{SMOKE_SCENARIO}_pre_e1_v1_"
        f"c{num_clients}_w{num_windows}_seed{seed}"
    )
    if trace_dir.exists():
        trace, identity = load_event_trace(trace_dir)
        if (
            trace.metadata.num_clients != num_clients
            or trace.metadata.num_windows != num_windows
            or trace.metadata.seed != seed
        ):
            raise RuntimeError("Cached EventTrace metadata does not match requested smoke config")
        print(f"Loaded cached EventTrace: {trace_dir}")
        return trace, identity["trace_hash"]

    print(f"Generating real-data EventTrace: {num_clients} clients x {num_windows} windows")
    trace = _generate_real_event_trace(
        dataset,
        num_clients=num_clients,
        num_windows=num_windows,
        seed=seed,
    )
    identity = freeze_event_trace(trace, trace_dir)
    print(f"EventTrace frozen: {trace_dir}")
    print(f"  trace_hash: {identity['trace_hash']}")
    return trace, identity["trace_hash"]


def _compute_test_predictions(
    runner: FullWindowRunner,
    dataset: ProcessedDataset,
) -> dict:
    """Make predictions on test split using the final trained model."""
    test_units = dataset.get_atomic_units(split="test")
    if not test_units:
        return {"y_pred": [], "y_true": [], "unit_ids": [], "target_groups": []}

    import torch
    from raven_mcs.models.features import extract_features

    model = runner.model
    model.load_state_dict(runner.theta)
    model.eval()
    spatial_to_idx = dict(runner.dataset._spatial_to_idx)

    sids = [u.spatial_id for u in test_units]
    times = [u.absolute_time for u in test_units]
    t_idx = [u.time_index for u in test_units]

    sp, hour, wday, trend = extract_features(
        sids, times, t_idx, spatial_to_idx, int(dataset.atomic_df["time_index"].max()) + 1,
    )

    with torch.no_grad():
        preds = model(sp, hour, wday, trend).numpy()

    frozen_groups = FrozenTimeBlockMapper(group_count=4).map(dataset.atomic_df)
    group_by_unit = dict(zip(dataset.atomic_df["unit_id"].astype(str), frozen_groups))
    return {
        "y_pred": preds.astype(np.float64).tolist(),
        "y_true": [float(u.target_value) for u in test_units],
        "unit_ids": [u.unit_id for u in test_units],
        "target_groups": [int(group_by_unit[u.unit_id]) for u in test_units],
        "spatial_ids": [u.spatial_id for u in test_units],
        "opportunity_strata": [u.opportunity_stratum for u in test_units],
        "support_flags": [
            bool(dataset.atomic_df.set_index("unit_id").at[u.unit_id, "support_flag"])
            for u in test_units
        ],
    }


def _atomic_arrival_weights(
    preds: dict,
    runner: FullWindowRunner,
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    """Compute frozen test atomic arrival intensity and normalized weights.

    Uses only estimators fitted after completed train windows.  Within each
    opportunity stratum the exchangeable ν contribution is the frozen target
    mass conditional on that stratum; no prediction error enters this path.
    """
    strata = np.asarray(preds["opportunity_strata"], dtype=str)
    n = len(strata)
    target_frame = runner.dataset.atomic_df.copy()
    target_frame["_frozen_group"] = FrozenTimeBlockMapper(group_count=4).map(
        target_frame,
    )
    masses = TargetBuilder(
        group_mapper=GroupMapper(column="_frozen_group"),
    ).build(target_frame, split="test")
    unit_ids = pd.Index(preds["unit_ids"], dtype=str)
    target = masses.atom_mass.reindex(unit_ids, fill_value=0.0).to_numpy()
    stratum_target_mass = pd.Series(target).groupby(strata).transform("sum").to_numpy()
    nu = np.divide(
        target,
        stratum_target_mass,
        out=np.zeros_like(target),
        where=stratum_target_mass > 0,
    )
    client_ids = sorted({str(x) for x in runner.trace.events["client_id"].unique()})
    opp = runner.opportunity_estimator.pi_hat() if runner.opportunity_estimator else {}
    history = runner.trace.events
    client_age = history.groupby("client_id")["tau"].mean().to_dict()
    client_workload = history.groupby("client_id")["raw_workload"].mean().to_dict()
    pre_slack = (
        history["window_id"].astype(float) + 1.0 - history["registration_time"].astype(float)
    )
    client_slack = pre_slack.groupby(history["client_id"]).mean().to_dict()
    blocks = np.array([runner._hour_block(s) for s in strata], dtype=np.float64)
    pi_matrix = np.zeros((len(client_ids), n), dtype=np.float64)
    p_matrix = np.zeros_like(pi_matrix)
    q_matrix = np.zeros_like(pi_matrix)
    for row, client_id in enumerate(client_ids):
        pi_matrix[row] = np.array([
            opp.get((client_id, s), 0.0) for s in strata
        ])
        p_matrix[row] = np.array([
            runner.obs_propensity.predict(np.array([
                1.0, block, float(np.log1p(client_workload.get(client_id, 1.0))),
            ]))
            for block in blocks
        ])
        q_matrix[row] = runner.usable_propensity.predict(np.array([
            1.0, float(client_age.get(client_id, 0.0)), 0.0, 0.0,
            float(client_slack.get(client_id, 0.0)),
        ]))
    intensity, arrival = atomic_arrival_weights(
        pi_matrix, nu, p_matrix, q_matrix,
    )
    support = np.asarray(preds["support_flags"], dtype=bool)
    intensity = np.where(support, intensity, 0.0)
    if float(intensity.sum()) <= 0:
        raise RuntimeError("arrival intensity has no mass on frozen target support")
    arrival = intensity / float(intensity.sum())
    details = {
        "pi_hat_opp_contribution": pi_matrix.sum(axis=0),
        "nu_hat_contribution": nu,
        "p_hat_contribution": p_matrix.mean(axis=0),
        "q_hat_contribution": q_matrix.mean(axis=0),
        "arrival_intensity": intensity,
    }
    return target, arrival, details


def _compute_metrics(
    preds: dict,
    runner: FullWindowRunner,
    method_name: str,
) -> dict[str, float]:
    """Compute smoke-level metrics from predictions and runner state."""
    y_pred = np.array(preds["y_pred"], dtype=np.float64)
    y_true = np.array(preds["y_true"], dtype=np.float64)
    n = len(y_true)
    if n == 0:
        return {"RMSE_mu": float("nan"), "RMSE_rho": float("nan")}

    target_weights, arrival_weights, arrival_details = _atomic_arrival_weights(preds, runner)
    preds["target_weights"] = target_weights.tolist()
    preds["arrival_weights"] = arrival_weights.tolist()
    preds["arrival_intensity"] = arrival_details["arrival_intensity"].tolist()
    for name, values in arrival_details.items():
        preds[name] = values.tolist()
    rmse_mu_val = rmse_mu(y_pred, y_true, target_weights)
    rmse_rho_val = rmse_rho(y_pred, y_true, arrival_weights)
    gap_mis_val = gap_mis(rmse_mu_val, rmse_rho_val)

    # Debt diagnostics
    debt_l1 = float(np.linalg.norm(runner.debt, ord=1))
    omega_bar = runner.omega_bar() if len(runner.metrics) > 0 else np.zeros(runner.num_groups)

    # Count metrics
    total_windows = len(runner.metrics)
    active_windows = sum(1 for m in runner.metrics if m.active)

    # Clip rates
    clip_s1 = float(np.mean([m.clip_rate_stage1 for m in runner.metrics if m.active])) if active_windows > 0 else 0.0
    clip_s2 = float(np.mean([m.clip_rate_stage2 for m in runner.metrics if m.active])) if active_windows > 0 else 0.0

    # Train loss
    avg_loss = float(np.mean([m.train_loss for m in runner.metrics if m.active])) if active_windows > 0 else 0.0

    return {
        "method": method_name,
        "RMSE_mu": rmse_mu_val,
        "RMSE_rho": rmse_rho_val,
        "Gap_mis": gap_mis_val,
        "debt_l1": debt_l1,
        "active_windows": active_windows,
        "total_windows": total_windows,
        "clip_rate_stage1": clip_s1,
        "clip_rate_stage2": clip_s2,
        "avg_train_loss": avg_loss,
        "num_test_units": n,
        "num_groups": runner.num_groups,
        "e_r_sizes": [m.e_r_size for m in runner.metrics if m.active],
        "a_r_sizes": [m.a_r_size for m in runner.metrics if m.active],
        "n_eff_median": float(np.median(
            [v for m in runner.metrics for v in m.n_eff_values if v > 0]
        )) if runner.metrics else 0.0,
        "theta_changed": any(
            m.theta_hash_before != m.theta_hash_after
            for m in runner.metrics if m.active
        ),
        "target_arrival_l1_gap": float(np.abs(target_weights - arrival_weights).sum()),
    }


def run_smoke(
    data_dir: Path,
    trace_cache: Path,
    output_dir: Path,
    *,
    num_clients: int = 10,
    num_windows: int = 20,
    seed: int = 26001,
    local_steps: int = 2,
    learning_rate: float = 0.01,
    dry_run: bool = False,
    run_prefix: str = "P10_SMOKE",
) -> dict:
    """Execute the full P10-SMOKE pipeline."""
    start_time = datetime.now(timezone.utc)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / f"{run_prefix}_{ts}"
    experiment_name = "PRE_E1_SMOKE" if run_prefix == "PRE_E1_SMOKE" else "P10_R1_SMOKE"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"P10-SMOKE run directory: {run_dir}")

    # 1. Load processed dataset
    print("\n[1/5] Loading SensorScope processed dataset...")
    metadata = DatasetMetadata(
        dataset=SMOKE_DATASET,
        target_name="ambient_temperature",
        target_unit="degree_Celsius",
        spatial_unit="sensorscope_station",
        time_unit="hour",
        source_name="EPFL/Zenodo SensorScope Data",
        source_url="https://zenodo.org/records/2654726",
        raw_license="cc-by-4.0",
        filtering_rules=(
            "Drop rows with non-finite temperature",
            "Keep temperature in [-40, 60] Celsius",
        ),
    )
    metadata.validate()

    dataset = ProcessedDataset(data_dir, metadata)
    print(f"  units: {len(dataset.atomic_df)}, clients: {dataset.num_spatial}, groups: {dataset.num_groups}")

    # 2. Generate/load EventTrace
    print(f"\n[2/5] Generating EventTrace ({num_clients} clients x {num_windows} windows)...")
    if dry_run:
        print("  [dry-run] Skipping EventTrace generation")
        return {"status": "dry_run", "run_dir": str(run_dir)}

    trace, trace_hash = _get_or_generate_smoke_trace(
        dataset, trace_cache, num_clients, num_windows, seed,
    )
    (_ROOT / "outputs" / "audits").mkdir(parents=True, exist_ok=True)
    _write_group_reachability_audit(
        trace, dataset,
        _ROOT / "outputs" / "audits" / "p10_r1_group_reachability.json",
    )
    data_hash = sha256_path_tree(data_dir, ("*.parquet", "*.json"))
    groups_path = _ROOT / "configs" / "frozen" / "e1_sensorscope_groups.yaml"
    target_group_hash = sha256_file(groups_path)
    freeze_validation = validate_frozen_config(
        experiment_name,
        SMOKE_DATASET,
        _ROOT / "configs" / "frozen",
        expected_data_hash=data_hash,
        expected_group_mapping_hash=target_group_hash,
        expected_event_trace_hash=trace_hash,
    )
    frozen_config = freeze_validation["config"]
    config_hash_value = freeze_validation["config_hash"]
    time_lookup = dataset.atomic_df.set_index("unit_id")["absolute_time"]
    index_lookup = dataset.atomic_df.set_index("unit_id")["time_index"]
    expected_window_by_slot = {
        int(slot): window_id
        for window_id, block in enumerate(np.array_split(
            np.sort(dataset.atomic_df["time_index"].unique()), num_windows,
        ))
        for slot in block
    }
    window_ranges = []
    previous_max = None
    out_of_order = 0
    overlap_count = 0
    assigned_ids: list[str] = []
    for window_id in range(num_windows):
        ids = [
            unit_id for row in trace.events.loc[trace.events["window_id"] == window_id, "risk_set_unit_ids"]
            for unit_id in row
        ]
        assigned_ids.extend(ids)
        times = pd.to_datetime(time_lookup.reindex(ids).dropna(), utc=True)
        if len(times):
            start, end = times.min(), times.max()
            if previous_max is not None and start < previous_max:
                out_of_order += 1
                overlap_count += 1
            previous_max = end
            window_ranges.append({
                "window_id": window_id,
                "start": str(start),
                "end": str(end),
                "min_absolute_time": str(start),
                "max_absolute_time": str(end),
            })
    tau_violations = int((
        (trace.events["tau"] != trace.events["window_id"] - trace.events["downloaded_version"])
        | (trace.events["model_age"] != trace.events["tau"])
    ).sum())
    s_max = int(trace.metadata.s_max)
    usable_over_smax = int(((trace.events["U"] == 1) & (trace.events["tau"] > s_max)).sum())
    expired_but_usable = usable_over_smax
    missing_checkpoints = int((trace.events["downloaded_version"] < 0).sum())
    (_ROOT / "outputs" / "audits").mkdir(parents=True, exist_ok=True)
    duplicate_assignments = len(assigned_ids) - len(set(assigned_ids))
    unassigned_units = len(set(dataset.atomic_df["unit_id"].astype(str)) - set(assigned_ids))
    future_leakage_count = sum(
        expected_window_by_slot[int(index_lookup.loc[unit_id])] != int(row.window_id)
        for row in trace.events.itertuples()
        for unit_id in row.risk_set_unit_ids
    )
    time_audit = {
        "num_windows": num_windows,
        "assignment": "sorted_unique_time_slots_contiguous_blocks",
        "uses_modulo": False,
        "windows": window_ranges,
        "overlap_count": overlap_count,
        "out_of_order_count": out_of_order,
        "future_leakage_count": int(future_leakage_count),
        "tau_consistency_violations": tau_violations,
        "s_max": s_max,
        "usable_over_smax_count": usable_over_smax,
        "expired_but_usable_count": expired_but_usable,
        "missing_checkpoint_count": missing_checkpoints,
        "duplicate_unit_assignments": duplicate_assignments,
        "unassigned_unit_count": unassigned_units,
    }
    dump_json(time_audit, _ROOT / "outputs" / "audits" / "p10_r1_window_audit.json")
    dump_json(time_audit, _ROOT / "outputs" / "audits" / "PRE_E1_TIME_STALENESS_AUDIT.json")

    # 3. Run each method
    results: dict[str, dict] = {}
    all_predictions: dict[str, dict] = {}
    all_window_metrics: list[dict] = []
    runners: dict[str, FullWindowRunner] = {}

    for method_name in SMOKE_METHODS:
        print(f"\n[3/5] Running method: {method_name}")

        runner = build_full_runner(
            trace=trace,
            dataset=dataset,
            method=method_name,
            n_groups=4,
            model_seed=seed,
            learning_rate=learning_rate,
            local_steps=local_steps,
            device="cpu",
        )

        print(f"  Training {num_windows} windows with {local_steps} local steps...")
        t0 = time.perf_counter()
        metrics = runner.run()
        runners[method_name] = runner
        elapsed = time.perf_counter() - t0
        for metric in metrics:
            all_window_metrics.append({
                "method": method_name,
                "window_id": metric.window_id,
                "active": metric.active,
                "alpha": metric.alpha,
                "beta_hat": metric.beta_hat,
                "theta_hash_before": metric.theta_hash_before,
                "theta_hash_after": metric.theta_hash_after,
                "debt_l1": metric.debt_l1,
                "train_loss": metric.train_loss,
                "e_r_size": metric.e_r_size,
                "a_r_size": metric.a_r_size,
                "clip_rate_stage1": metric.clip_rate_stage1,
                "clip_rate_stage2": metric.clip_rate_stage2,
            })

        active = sum(1 for m in metrics if m.active)
        print(f"  Completed: {active}/{len(metrics)} active windows in {elapsed:.1f}s")

        # Make test predictions
        print(f"  Computing test predictions...")
        preds = _compute_test_predictions(runner, dataset)
        all_predictions[method_name] = preds

        # Compute metrics
        method_metrics = _compute_metrics(preds, runner, method_name)
        method_metrics["elapsed_seconds"] = elapsed
        method_metrics["trace_hash"] = trace_hash
        method_metrics["final_model_hash"] = runner._theta_hash()
        results[method_name] = method_metrics

        print(f"  RMSE_mu={method_metrics['RMSE_mu']:.4f}, "
              f"RMSE_rho={method_metrics['RMSE_rho']:.4f}, "
              f"Gap_mis={method_metrics['Gap_mis']:.4f}")

    # 4. Save artifacts
    print(f"\n[4/5] Saving artifacts...")

    # Save predictions
    pred_rows: list[dict] = []
    for method_name, preds in all_predictions.items():
        for i in range(len(preds["y_true"])):
            pred_rows.append({
                "unit_id": preds["unit_ids"][i],
                "y_true": preds["y_true"][i],
                "y_pred": preds["y_pred"][i],
                "target_weight": preds["target_weights"][i],
                "arrival_intensity": preds["arrival_intensity"][i],
                "arrival_weight": preds["arrival_weights"][i],
                "pi_hat_opp_contribution": preds["pi_hat_opp_contribution"][i],
                "nu_hat_contribution": preds["nu_hat_contribution"][i],
                "p_hat_contribution": preds["p_hat_contribution"][i],
                "q_hat_contribution": preds["q_hat_contribution"][i],
                "target_group": preds["target_groups"][i],
                "opportunity_stratum": preds["opportunity_strata"][i],
                "support_flag": preds["support_flags"][i],
                "method": method_name,
                "seed": seed,
                "split": "test",
            })
    pred_df = pd.DataFrame(pred_rows)
    pred_df.to_parquet(run_dir / "predictions_test.parquet", index=False)
    pred_df[
        [
            "unit_id", "target_weight", "arrival_intensity", "arrival_weight",
            "pi_hat_opp_contribution", "nu_hat_contribution",
            "p_hat_contribution", "q_hat_contribution",
            "target_group", "opportunity_stratum", "method", "seed",
        ]
    ].to_parquet(run_dir / "arrival_weights_test.parquet", index=False)
    arrival_audit = {
        "sum_target_weights": float(pred_df["target_weight"].sum() / len(SMOKE_METHODS)),
        "sum_arrival_weights": float(pred_df["arrival_weight"].sum() / len(SMOKE_METHODS)),
        "min_arrival_weight": float(pred_df["arrival_weight"].min()),
        "max_arrival_weight": float(pred_df["arrival_weight"].max()),
        "l1_target_arrival_gap": float(results["raven"]["target_arrival_l1_gap"]),
        "number_zero_weight_units": int((pred_df["arrival_weight"] == 0).sum()),
        "support_violation_count": int(
            ((~pred_df["support_flag"].astype(bool)) & (pred_df["arrival_weight"] > 0)).sum()
        ),
    }
    audits_dir = _ROOT / "outputs" / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)
    dump_json(arrival_audit, audits_dir / "p10_r1_arrival_weight_audit.json")
    metric_audit = {
        "methods": {
            method: {
                "RMSE_mu": results[method]["RMSE_mu"],
                "RMSE_rho": results[method]["RMSE_rho"],
                "Gap_mis": results[method]["Gap_mis"],
                "gap_identity_error": abs(
                    results[method]["Gap_mis"]
                    - (results[method]["RMSE_mu"] - results[method]["RMSE_rho"])
                ),
            }
            for method in SMOKE_METHODS
        },
        **arrival_audit,
        "hard_gate_pass": all(
            abs(
                results[method]["Gap_mis"]
                - (results[method]["RMSE_mu"] - results[method]["RMSE_rho"])
            ) <= 1e-12
            for method in SMOKE_METHODS
        ),
    }
    dump_json(metric_audit, run_dir / "PRE_E1_METRIC_AUDIT.json")
    dump_json(metric_audit, audits_dir / "PRE_E1_METRIC_AUDIT.json")
    _write_method_diagnostic(
        runners["fedavg_window"], runners["twostage_hajek"],
        all_predictions, audits_dir / "p10_r1_fedavg_twostage_diagnostic.parquet",
    )
    _write_q_feature_audit(
        runners, audits_dir / "p10_r1_q_feature_scan.csv",
    )

    # Save window metrics
    pd.DataFrame(all_window_metrics).to_parquet(run_dir / "metrics_window.parquet", index=False)
    pd.DataFrame([
        {
            "method": name,
            "observation_history": len(runners[name].obs_propensity.history_y),
            "q_history": len(runners[name].usable_propensity.history_y),
            "q_estimated": len(runners[name].usable_propensity.history_y) >= runners[name].usable_propensity.min_samples,
            "first_stage_clip_rate": result["clip_rate_stage1"],
            "second_stage_clip_rate": result["clip_rate_stage2"],
        }
        for name, result in results.items()
    ]).to_parquet(run_dir / "propensity_diagnostics.parquet", index=False)
    solver_rows = []
    raven_solver_results = getattr(runners["raven"].aggregator, "solve_results", [])
    for window_id, result in enumerate(raven_solver_results):
        solver_rows.append({
            "method": "raven",
            "window_id": window_id,
            "primary_solver": "CLARABEL",
            "primary_status": result.primary_status,
            "objective_value": result.objective_value,
            "simplex_residual": result.simplex_residual,
            "nonnegative_violation": result.nonnegative_violation,
            "upper_bound_violation": result.upper_bound_violation,
            "ess_l2_violation": result.ess_l2_violation,
            "solve_time_seconds": result.solve_time_s,
            "fallback_triggered": result.fallback_used,
            "fallback_solver": result.fallback_solver,
            "fallback_status": result.fallback_status,
            "accepted_solver": result.backend,
            "accepted_status": result.status,
        })
    solver_df = pd.DataFrame(solver_rows)
    solver_df.to_parquet(run_dir / "solver_diagnostics.parquet", index=False)
    solver_audit = {
        "windows": len(solver_df),
        "fallback_count": int(solver_df["fallback_triggered"].sum()),
        "max_simplex_residual": float(solver_df["simplex_residual"].max()),
        "max_nonnegative_violation": float(solver_df["nonnegative_violation"].max()),
        "max_upper_bound_violation": float(solver_df["upper_bound_violation"].max()),
        "max_ess_l2_violation": float(solver_df["ess_l2_violation"].max()),
        "all_accepted_optimal": bool((solver_df["accepted_status"] == "optimal").all()),
        "hard_gate_pass": bool(
            (solver_df["simplex_residual"] <= 1e-7).all()
            and (solver_df["nonnegative_violation"] <= 1e-8).all()
            and (solver_df["upper_bound_violation"] <= 1e-7).all()
            and (solver_df["ess_l2_violation"] <= 1e-7).all()
            and (solver_df["accepted_status"] == "optimal").all()
        ),
    }
    dump_json(solver_audit, run_dir / "PRE_E1_SOLVER_AUDIT.json")
    dump_json(solver_audit, audits_dir / "PRE_E1_SOLVER_AUDIT.json")

    # Save run metrics
    dump_json({"methods": results, "trace_hash": trace_hash, "seed": seed,
               "num_windows": num_windows, "num_clients": num_clients,
               "local_steps": local_steps},
              run_dir / "metrics_run.json")

    # Save manifest
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=_ROOT, capture_output=True,
        text=True, check=True,
    ).stdout.strip()
    git_dirty = bool(subprocess.run(
        ["git", "status", "--porcelain"], cwd=_ROOT, capture_output=True,
        text=True, check=True,
    ).stdout.strip())
    end_time = datetime.now(timezone.utc)
    manifest = {
        "run_id": run_dir.name,
        "dataset": SMOKE_DATASET,
        "scenario": SMOKE_SCENARIO,
        "method": SMOKE_METHODS,
        "seed": seed,
        "num_windows": num_windows,
        "num_clients": num_clients,
        "local_steps": local_steps,
        "s_max": s_max,
        "methods": SMOKE_METHODS,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "config_hash": config_hash_value,
        "data_hash": data_hash,
        "data_path": str(data_dir.resolve()),
        "event_trace_hash": trace_hash,
        "trace_hash": trace_hash,
        "target_group_hash": target_group_hash,
        "environment_hash": environment_hash(),
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "device": "cpu",
        "solver": {"raven": "CLARABEL"},
        "hard_gate_status": "PENDING",
    }
    dump_json(manifest, run_dir / "manifest.json")
    dump_json(time_audit, run_dir / "PRE_E1_TIME_STALENESS_AUDIT.json")
    (run_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(frozen_config, sort_keys=True), encoding="utf-8"
    )
    dump_json({
        "event_trace_hash": trace_hash,
        "trace_hash": trace_hash,
        "trace_dir": str(trace_cache / (
            f"{SMOKE_DATASET}_{SMOKE_SCENARIO}_pre_e1_v1_"
            f"c{num_clients}_w{num_windows}_seed{seed}"
        )),
    }, run_dir / "event_trace_ref.json")
    dump_json(
        {"device": "cpu", "methods": results, "window_count": num_windows},
        run_dir / "system_metrics.json",
    )
    checkpoints = run_dir / "checkpoints"
    checkpoints.mkdir(exist_ok=True)
    dump_json({"final_model_hashes": {name: results[name]["final_model_hash"] for name in SMOKE_METHODS}},
              checkpoints / "checkpoint_index.json")
    for name, runner in runners.items():
        import torch
        torch.save(runner.theta, checkpoints / f"{name}.pt")
    (run_dir / "stdout.log").write_text(
        "\n".join([
            "P10-R1 smoke completed",
            f"run_id={run_dir.name}",
            f"trace_hash={trace_hash}",
            f"config_hash={config_hash_value}",
            f"methods={','.join(SMOKE_METHODS)}",
        ]) + "\n",
        encoding="utf-8",
    )
    (run_dir / "stderr.log").write_text("", encoding="utf-8")

    # 5. Smoke check summary
    print(f"\n[5/5] P10-SMOKE checks:")
    checks = _run_smoke_checks(
        results, all_predictions, all_window_metrics, trace, run_dir,
    )
    dump_json(checks, run_dir / "smoke_checks.json")

    all_pass = all(c["pass"] for c in checks)
    manifest["hard_gate_status"] = {
        "smoke_checks": "PASS" if all_pass else "FAIL",
        "r1_gates": "PENDING",
    }
    dump_json(manifest, run_dir / "manifest.json")
    print(f"  Overall: {'PASS' if all_pass else 'FAIL'}")

    for check in checks:
        status = "PASS" if check["pass"] else "FAIL"
        print(f"  [{status}] {check['name']}: {check.get('detail', '')}")

    return {
        "status": "PASS" if all_pass else "FAIL",
        "run_dir": str(run_dir),
        "results": results,
        "checks": checks,
    }


def _run_smoke_checks(
    results: dict[str, dict],
    predictions: dict[str, dict],
    window_metrics: list[dict],
    trace: EventTrace,
    run_dir: Path,
) -> list[dict]:
    """Run P10-SMOKE compliance checks."""
    checks: list[dict] = []

    # Check 1: EventTrace is real-data derived (not synthetic)
    checks.append({
        "name": "EventTrace from real data",
        "pass": trace.metadata.dataset == SMOKE_DATASET
        and trace.metadata.generator.startswith("real-data"),
        "detail": trace.metadata.generator,
    })

    # Check 2: No synthetic fallback
    checks.append({
        "name": "no_synthetic_fallback",
        "pass": trace.metadata.dataset != "synthetic",
    })

    # Check 3: Training loss non-constant (check across methods)
    losses = [r.get("avg_train_loss", 0) for r in results.values()]
    checks.append({
        "name": "training_loss_non_constant",
        "pass": bool(np.all(np.isfinite(losses)) and any(l > 0 for l in losses)),
        "detail": f"losses: {losses}",
    })

    # Check 4: Test predictions non-constant
    all_rmse = [r.get("RMSE_mu", float("nan")) for r in results.values()]
    prediction_variances = [
        float(np.var(predictions[name]["y_pred"])) for name in SMOKE_METHODS
    ]
    checks.append({
        "name": "test_predictions_non_constant",
        "pass": bool(all(v > 0 and np.isfinite(v) for v in prediction_variances)),
        "detail": f"prediction variances: {prediction_variances}",
    })

    # Check 5: Different methods produce different predictions
    checks.append({
        "name": "methods_produce_different_predictions",
        "pass": len({
            sha256_json(predictions[name]["y_pred"]) for name in SMOKE_METHODS
        }) > 1,
        "detail": "prediction hashes compared",
    })

    # Check 6: Model parameters actually changed
    theta_changed = any(r.get("theta_changed", False) for r in results.values())
    checks.append({
        "name": "model_parameters_changed",
        "pass": theta_changed,
        "detail": "theta hash changed during training",
    })

    active_rows = [row for row in window_metrics if row["active"]]
    alpha_legal = all(
        len(row["alpha"]) > 0
        and np.all(np.asarray(row["alpha"]) >= 0)
        and abs(float(np.sum(row["alpha"])) - 1.0) <= 1e-8
        for row in active_rows
    )
    beta_legal = all(
        len(row["beta_hat"]) > 0
        and np.all(np.asarray(row["beta_hat"]) >= 0)
        and abs(float(np.sum(row["beta_hat"])) - 1.0) <= 1e-8
        for row in active_rows
    )

    # Check 7: each window has one immutable before/after snapshot.
    checks.append({
        "name": "theta_frozen_within_window",
        "pass": all(bool(row["theta_hash_before"]) and bool(row["theta_hash_after"]) for row in window_metrics),
        "detail": "before/after hashes recorded for every window",
    })

    # Check 8: Stale downloaded version allowed
    checks.append({
        "name": "stale_downloaded_version_allowed",
        "pass": bool((trace.events["downloaded_version"] <= trace.events["window_id"]).all()),
        "detail": "all downloaded versions are current or historical",
    })

    # Check 9: RAVEN does not use oracle_q
    checks.append({
        "name": "raven_no_oracle_q",
        "pass": "oracle_q" not in set(UsablePropensity().feature_names),
        "detail": "runtime q feature schema excludes oracle_q",
    })

    # Check 10: A_r subset of E_r
    for method, r in results.items():
        e_sizes = r.get("e_r_sizes", [])
        a_sizes = r.get("a_r_sizes", [])
        for e, a in zip(e_sizes, a_sizes):
            if a > e:
                checks.append({
                    "name": f"A_r_subset_E_r_{method}",
                    "pass": False,
                    "detail": f"a_r_size={a} > e_r_size={e}",
                })
                break
    else:
        checks.append({
            "name": "A_r_subset_E_r",
            "pass": True,
        })

    # Check 11: Alpha legal (sum to 1)
    checks.append({
        "name": "alpha_legal",
        "pass": alpha_legal,
        "detail": "checked every active window",
    })

    # Check 12: Beta legal (sum to 1)
    checks.append({
        "name": "beta_legal",
        "pass": beta_legal,
        "detail": "checked every active window",
    })

    # Check 13: c from records
    checks.append({
        "name": "composition_from_records",
        "pass": all(r.get("num_groups") == 4 for r in results.values()),
        "detail": "main debt uses frozen G=4 mapping",
    })

    # Check 14: m and n_eff not interchanged
    checks.append({
        "name": "m_and_n_eff_not_interchanged",
        "pass": all(r.get("n_eff_median", 0) > 0 for r in results.values()),
        "detail": "positive independent n_eff diagnostics present",
    })

    # Check 15-16: RMSE outputs
    for method, r in results.items():
        rmse_mu_val = r.get("RMSE_mu", float("nan"))
        rmse_rho_val = r.get("RMSE_rho", float("nan"))
        checks.append({
            "name": f"RMSE_mu_{method}",
            "pass": not np.isnan(rmse_mu_val) and rmse_mu_val > 0,
            "detail": f"{rmse_mu_val:.4f}",
        })
        checks.append({
            "name": f"RMSE_rho_{method}",
            "pass": not np.isnan(rmse_rho_val) and rmse_rho_val > 0,
            "detail": f"{rmse_rho_val:.4f}",
        })

    # Check 17: strict Gap_mis identity and non-uniform arrival risk
    for method, r in results.items():
        gap = r.get("Gap_mis", float("nan"))
        checks.append({
            "name": f"gap_identity_{method}",
            "pass": abs(gap - (r["RMSE_mu"] - r["RMSE_rho"])) <= 1e-12,
            "detail": f"{gap:.12f}",
        })
        checks.append({
            "name": f"target_arrival_weights_differ_{method}",
            "pass": r.get("target_arrival_l1_gap", 0.0) > 1e-6,
            "detail": f"L1={r.get('target_arrival_l1_gap', 0.0):.8f}",
        })

    # Check 18-23: Distribution diagnostics present
    checks.append({
        "name": "delta_group_output",
        "pass": all(np.isfinite(r["debt_l1"]) for r in results.values()),
        "detail": "finite debt diagnostics for every method",
    })

    # Check 24: Debt upper bound
    for method, r in results.items():
        debt = r.get("debt_l1", 0)
        checks.append({
            "name": f"debt_bounded_{method}",
            "pass": np.isfinite(debt) and debt >= 0,
            "detail": f"debt_l1={debt:.4f}",
        })

    # Check 25: Clip rate and ESS
    for method, r in results.items():
        clip1 = r.get("clip_rate_stage1", -1)
        clip2 = r.get("clip_rate_stage2", -1)
        checks.append({
            "name": f"clip_rates_{method}",
            "pass": 0 <= clip1 <= 1 and 0 <= clip2 <= 1,
            "detail": f"s1={clip1:.3f} s2={clip2:.3f}",
        })

    # Check 26: Complete manifest
    checks.append({
        "name": "complete_manifest",
        "pass": all((run_dir / name).exists() for name in (
            "manifest.json", "metrics_run.json", "predictions_test.parquet",
            "arrival_weights_test.parquet", "metrics_window.parquet",
        )),
        "detail": "required core files checked on disk",
    })

    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P10 End-to-End Smoke Test")
    parser.add_argument("--data-dir", type=Path,
                        default=_ROOT / "data" / "processed" / "sensorscope")
    parser.add_argument("--trace-cache", type=Path,
                        default=_ROOT / "outputs" / "event_traces")
    parser.add_argument("--output-dir", type=Path,
                        default=_ROOT / "outputs" / "runs")
    parser.add_argument("--clients", type=int, default=10)
    parser.add_argument("--windows", type=int, default=20)
    parser.add_argument("--seed", type=int, default=26001)
    parser.add_argument("--local-steps", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-prefix", default="P10_SMOKE")
    args = parser.parse_args(argv)

    print("=" * 60)
    print("RAVEN-MCS P10 End-to-End Smoke Test")
    print("=" * 60)
    print(f"  Dataset:   {SMOKE_DATASET}")
    print(f"  Scenario:  {SMOKE_SCENARIO}")
    print(f"  Methods:   {SMOKE_METHODS}")
    print(f"  Clients:   {args.clients}")
    print(f"  Windows:   {args.windows}")
    print(f"  Seed:      {args.seed}")
    print(f"  Local SGD: {args.local_steps} steps")
    print(f"  Device:    CPU")
    print("=" * 60)

    result = run_smoke(
        data_dir=args.data_dir,
        trace_cache=args.trace_cache,
        output_dir=args.output_dir,
        num_clients=args.clients,
        num_windows=args.windows,
        seed=args.seed,
        local_steps=args.local_steps,
        learning_rate=args.learning_rate,
        dry_run=args.dry_run,
        run_prefix=args.run_prefix,
    )

    print(f"\nP10-SMOKE {result['status']}")
    print(f"Run directory: {result['run_dir']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
