#!/usr/bin/env python3
"""Generate and freeze an immutable EventTrace for a given dataset/scenario/seed.

Usage:
    python scripts/generate_event_trace.py dataset=sensorscope scenario=balanced seed=26001
    python scripts/generate_event_trace.py --help
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.simulation.event_trace import (
    EventTrace,
    EventTraceMetadata,
    freeze_event_trace,
    synthesize_event_trace,
)
from raven_mcs.simulation.observation_generator import (
    ObservationConfig,
    generate_observations_for_trace,
)
from raven_mcs.simulation.opportunity_generator import (
    OpportunityConfig,
    generate_opportunity_stream,
)
from raven_mcs.simulation.usable_generator import (
    UsableConfig,
    generate_q_oracle,
    generate_usable_events,
)
from raven_mcs.utils.config import resolve_run_config
from raven_mcs.utils.serialization import dump_json, load_yaml


def _full_trace(
    dataset: str,
    scenario_name: str,
    seed: int,
    num_windows: int,
) -> EventTrace:
    """Build a controlled EventTrace from atomic_units + scenario config."""
    # Load scenario config
    scenario_cfg = load_yaml(_ROOT / "configs" / "scenario" / f"{scenario_name}.yaml")

    num_clients = 50
    opportunity_skew = float(scenario_cfg.get("opportunity_skew", 1.0))
    obs_rate = float(scenario_cfg.get("mean_observation_rate", 0.20))
    usable_rate = float(scenario_cfg.get("mean_usable_rate", 0.60))
    drift_period = scenario_cfg.get("drift_period")
    drift_magnitude = float(scenario_cfg.get("drift_magnitude", 0.0))

    # Generate opportunity stream
    opp_cfg = OpportunityConfig(
        num_clients=num_clients,
        num_windows=num_windows,
        risk_set_mean=7,
        opportunity_skew=opportunity_skew,
        drift_period=drift_period,
        drift_magnitude=drift_magnitude,
        seed=seed,
    )
    dummy_atomic = pd.DataFrame(
        {"unit_id": [f"u{i:06d}" for i in range(1000)], "opportunity_stratum": np.tile(np.arange(4), 250)}
    )
    opp_stream = generate_opportunity_stream(dummy_atomic, opp_cfg)

    # Generate usable events
    use_cfg = UsableConfig(
        mean_usable_rate=usable_rate,
        window_duration=1.0,
        max_staleness=5,
        seed=seed,
    )
    cs, cd, ns, nd, at, U = generate_usable_events(num_clients, num_windows, use_cfg)
    q_oracle = generate_q_oracle(num_clients, num_windows, use_cfg)

    # Generate observations
    obs_cfg = ObservationConfig(
        mean_observation_rate=obs_rate,
        seed=seed,
    )
    total_entries = len(opp_stream)
    O_flat, p_oracle, _, _ = generate_observations_for_trace(total_entries, obs_cfg)

    # Assemble EventTrace rows
    rows: list[dict] = []
    for idx, row in opp_stream.iterrows():
        w = int(row["window_id"])
        k = int(row["client_id"].replace("c", ""))
        risk_units = row["risk_set_unit_ids"]
        n_risk = len(risk_units)
        o_start = idx * 4  # approximate mapping
        o_flags = {u: bool(O_flat[min(o_start + i, len(O_flat) - 1)]) for i, u in enumerate(risk_units)}
        observed = [u for u, flag in o_flags.items() if flag]

        downloaded_version = max(0, w - (k % 6))
        tau = w - downloaded_version
        rows.append({
            "window_id": w,
            "client_id": row["client_id"],
            "risk_set_unit_ids": risk_units,
            "opportunity_features": row["opportunity_features"],
            "observed_unit_ids": observed,
            "O": o_flags,
            "registration_time": float(w) + 0.1,
            "downloaded_version": downloaded_version,
            "model_age": tau,
            "tau": tau,
            "device_profile": "synthetic-phone",
            "network_profile": "synthetic-wifi",
            "compute_success": bool(cs[w, k]),
            "compute_duration": float(cd[w, k]),
            "network_success": bool(ns[w, k]),
            "network_duration": float(nd[w, k]),
            "arrival_time": float(w) + 0.5 + 0.01 * k,
            "U": int(bool(U[w, k])),
            "raw_workload": float(len(observed)),
            "oracle_p": float(p_oracle[min(idx, len(p_oracle) - 1)]),
            "oracle_q": float(q_oracle[w, k]),
            "hidden_confounder": 0.0,
        })

    events = pd.DataFrame(rows)
    meta = EventTraceMetadata(
        dataset=dataset,
        seed=seed,
        num_windows=num_windows,
        num_clients=num_clients,
    )
    trace = EventTrace(events=events, metadata=meta)
    trace.validate()
    return trace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and freeze an immutable EventTrace.")
    parser.add_argument("--dataset", default="sensorscope")
    parser.add_argument("--scenario", default="balanced")
    parser.add_argument("--seed", type=int, default=26001)
    parser.add_argument("--num-windows", type=int, default=100)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/event_traces"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    print(f"Generating EventTrace: dataset={args.dataset} scenario={args.scenario} seed={args.seed} windows={args.num_windows}")

    trace = _full_trace(
        dataset=args.dataset,
        scenario_name=args.scenario,
        seed=args.seed,
        num_windows=args.num_windows,
    )

    out = args.output_dir / f"{args.dataset}_{args.scenario}_seed{args.seed}"
    if args.dry_run:
        print(f"[dry-run] Would write to: {out}")
        return 0

    identity = freeze_event_trace(trace, out)
    print(f"EventTrace frozen: {out}")
    print(f"trace_hash: {identity['trace_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
