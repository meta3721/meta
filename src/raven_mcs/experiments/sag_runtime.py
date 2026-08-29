"""Shared EventTrace + target wiring for SAG G0/G1 (reuses E3 sealed assets)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from raven_mcs.correction.pi_target import build_pi_target
from raven_mcs.e3.canary.dataset_load import load_paper_dataset, load_spatial_to_client
from raven_mcs.e3.real_runner.generator_r3 import build_joint_pi_opp
from raven_mcs.e3.stratum_seal.remap import apply_sealed_opportunity_stratum
from raven_mcs.e3.target_pair.target_wiring import production_target_bundle
from raven_mcs.simulation.event_trace import EventTrace, load_event_trace


METHODS = ("raven", "raven_wo_design", "raven_sag")

SEALED_EVENTTRACE = Path("artifacts/e3_formal_runs_r1/eventtraces")


def eventtrace_dir(root: Path, dataset: str, seed: int) -> Path:
    return Path(root) / SEALED_EVENTTRACE / dataset / f"seed{seed}" / "training_eventtrace"


def slice_event_trace(trace: EventTrace, max_windows: int | None) -> EventTrace:
    if max_windows is None:
        return trace
    n = int(max_windows)
    events = trace.events.loc[trace.events["window_id"].astype(int) < n].copy()
    meta = replace(trace.metadata, num_windows=n)
    sliced = EventTrace(events=events.reset_index(drop=True), metadata=meta)
    sliced.validate()
    return sliced


def prepare_sag_bundle(
    *,
    root: Path,
    dataset: str,
    seed: int,
    max_windows: int | None = None,
) -> dict[str, Any]:
    """Load sealed SensorScope/U-Air EventTrace, target, and pi maps.

    Does not regenerate traces. Truncation is in-memory for smoke only.
    """
    root = Path(root)
    ds = load_paper_dataset(root, dataset)
    mapping = load_spatial_to_client(root, dataset)
    et_dir = eventtrace_dir(root, dataset, seed)
    if not (et_dir / "trace_identity.json").is_file():
        raise FileNotFoundError(f"sealed EventTrace missing: {et_dir}")
    trace, identity = load_event_trace(et_dir)
    trace = slice_event_trace(trace, max_windows)

    bundle = production_target_bundle(
        root=root,
        dataset_name=dataset,
        dataset=ds,
        fixture_artifact=None,
    )
    if bundle["uses_repeatable_time_of_day_mapper"]:
        raise RuntimeError("TARGET_WIRING_ERROR: RepeatableTimeOfDayMapper fallback active")
    n_groups = int(bundle["n_groups_runtime"])
    target_mu = bundle["mu"]

    atomic_sealed, stratum_meta = apply_sealed_opportunity_stratum(
        ds.atomic_df, dataset=dataset, root=root,
    )
    sealed_by_unit = {
        str(r.unit_id): str(r.opportunity_stratum)
        for r in atomic_sealed.itertuples(index=False)
    }
    ds._atomic_df = ds._atomic_df.copy()
    ds._atomic_df["opportunity_stratum"] = [
        sealed_by_unit.get(str(uid), str(s))
        for uid, s in zip(
            ds._atomic_df["unit_id"].tolist(),
            ds._atomic_df["opportunity_stratum"].tolist(),
        )
    ]
    atomic_for_pi = atomic_sealed.copy()
    if "target_group_main" not in atomic_for_pi.columns:
        atomic_for_pi["target_group_main"] = atomic_for_pi["target_group"].astype(str)

    train = atomic_sealed.loc[atomic_sealed["split"].astype(str) == "train"]
    strata_by_client: dict[str, list[str]] = {}
    for r in train.itertuples(index=False):
        client = mapping.get(str(r.spatial_id))
        if client is None:
            continue
        strata_by_client.setdefault(client, []).append(str(r.opportunity_stratum))
    for client in strata_by_client:
        strata_by_client[client] = sorted(set(strata_by_client[client]))
    pi_opp_joint = build_joint_pi_opp(sorted(strata_by_client), strata_by_client)
    pi_frame = build_pi_target(atomic_for_pi, mapping, split="test")
    pi_target = {
        (str(r.client_id), str(r.opportunity_stratum)): float(r.pi_k_s_tar)
        for r in pi_frame.itertuples()
    }
    return {
        "dataset": ds,
        "dataset_name": dataset,
        "spatial_to_client": mapping,
        "trace": trace,
        "identity": identity,
        "eventtrace_dir": et_dir,
        "target_mu": target_mu,
        "n_groups": n_groups,
        "pi_target": pi_target,
        "pi_opp_joint": pi_opp_joint,
        "stratum_meta": stratum_meta,
        "atomic_sealed": atomic_sealed,
        "head_tail": bundle["head_tail"],
        "target_artifact_path": bundle["artifact_path"],
        "target_artifact_sha256": bundle["artifact_sha256"],
    }
