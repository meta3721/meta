#!/usr/bin/env python3
"""Cross-check positive pi target support against all official risk sets."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

from raven_mcs.experiments.e1_entry import sensorscope_dataset
from raven_mcs.simulation.event_trace import load_event_trace
from raven_mcs.utils.serialization import dump_json, load_yaml


def crosscheck_support(
    target: pd.DataFrame,
    events: pd.DataFrame,
    station_to_client: dict[str, str],
    unit_to_stratum: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    risk: Counter[tuple[str, str]] = Counter()
    observed: Counter[tuple[str, str]] = Counter()
    usable: Counter[tuple[str, str]] = Counter()
    event_mapping_violations = 0
    for event in events.itertuples():
        client = str(event.client_id)
        strata = getattr(event, "opportunity_strata", None)
        risk_ids = getattr(event, "risk_set_unit_ids", None)
        if strata is None:
            if unit_to_stratum is None:
                raise ValueError("unit_to_stratum is required for raw EventTrace")
            strata = [
                unit_to_stratum[str(unit_id)]
                for unit_id in risk_ids
            ]
        outcomes = (
            [event.O[str(unit_id)] for unit_id in risk_ids]
            if isinstance(event.O, dict)
            else event.O
        )
        for stratum, outcome in zip(strata, outcomes):
            stratum = str(stratum)
            key = (client, stratum)
            risk[key] += 1
            if int(outcome) == 1:
                observed[key] += 1
                if int(event.U) == 1:
                    usable[key] += 1
            station = stratum.split("::", 1)[0]
            if station_to_client.get(station) != client:
                event_mapping_violations += 1
    positive = target.loc[
        target["pi_k_s_tar"].astype(float) > 0,
        ["client_id", "opportunity_stratum", "pi_k_s_tar"],
    ].copy()
    rows = []
    for row in positive.itertuples():
        key = (str(row.client_id), str(row.opportunity_stratum))
        rows.append({
            "client_id": key[0],
            "stratum_id": key[1],
            "pi_target": float(row.pi_k_s_tar),
            "in_eventtrace_risk_support": risk[key] > 0,
            "risk_record_count": risk[key],
            "observed_count": observed[key],
            "usable_count": usable[key],
            "violation": risk[key] == 0,
        })
    frame = pd.DataFrame(rows)
    summary = {
        "positive_target_pairs": int(len(frame)),
        "unsupported_positive_target_pairs": int(frame["violation"].sum()),
        "eventtrace_pair_not_in_frozen_mapping": event_mapping_violations,
    }
    return frame, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E1_balanced")
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    args = parser.parse_args()
    if args.experiment != "E1_balanced":
        raise ValueError("support audit is frozen to E1_balanced")
    root = Path(__file__).resolve().parents[1]
    target = pd.read_parquet(
        root / "configs/frozen/e1_pi_target_client_stratum.parquet",
    )
    mapping = load_yaml(
        root / "configs/frozen/e1_sensorscope_clients.yaml",
    )["station_to_client"]
    atomic = sensorscope_dataset(root).atomic_df
    valid_strata = set(
        atomic[
            "opportunity_stratum"
        ].astype(str)
    )
    unit_to_stratum = atomic.set_index(
        atomic["unit_id"].astype(str),
    )["opportunity_stratum"].astype(str).to_dict()
    output = root / "outputs/audits"
    output.mkdir(parents=True, exist_ok=True)
    reports = {}
    hard_gate = True
    for seed in args.seeds:
        trace, _ = load_event_trace(
            root / f"outputs/event_traces/e1_balanced_seed{seed}",
        )
        frame, summary = crosscheck_support(
            target, trace.events, mapping, unit_to_stratum,
        )
        frame.insert(0, "seed", seed)
        invalid = sum(
            str(stratum) not in valid_strata
            for unit_ids in trace.events["risk_set_unit_ids"]
            for stratum in (
                unit_to_stratum[str(unit_id)] for unit_id in unit_ids
            )
        )
        summary.update({
            "station_client_mismatch": summary[
                "eventtrace_pair_not_in_frozen_mapping"
            ],
            "invalid_stratum": int(invalid),
        })
        summary["hard_gate_pass"] = all(
            summary[key] == 0 for key in (
                "unsupported_positive_target_pairs",
                "eventtrace_pair_not_in_frozen_mapping",
                "station_client_mismatch",
                "invalid_stratum",
            )
        )
        hard_gate &= bool(summary["hard_gate_pass"])
        reports[str(seed)] = summary
        frame.to_parquet(
            output / f"e1_r3_support_crosscheck_seed{seed}.parquet",
            index=False,
        )
    dump_json({
        "seeds": reports,
        "hard_gate_pass": hard_gate,
    }, output / "e1_r3_support_crosscheck_summary.json")
    if not hard_gate:
        raise RuntimeError("positive target support crosscheck failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
