"""G6 step 1: freeze g* from train-side public objects. No method scoring."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DATASETS = ("sensorscope", "uair")


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _train_pools(atomic, spatial_to_client: dict[str, str]):
    pools: dict[tuple[str, str], list[str]] = {}
    train = atomic.loc[atomic["split"].astype(str) == "train"]
    for row in train.itertuples(index=False):
        client = spatial_to_client.get(str(row.spatial_id))
        if client is None:
            continue
        key = (client, str(row.opportunity_stratum))
        pools.setdefault(key, []).append(str(row.unit_id))
    client_ids = sorted({c for c, _ in pools})
    strata_by_client: dict[str, list[str]] = {}
    for client, stratum in pools:
        strata_by_client.setdefault(client, []).append(stratum)
    for client in strata_by_client:
        strata_by_client[client] = sorted(set(strata_by_client[client]))
    return client_ids, strata_by_client


def _mu4_from_frozen(artifact: dict) -> list[float]:
    from raven_mcs.e3.semantic_alignment.target_semantics import parse_time_block

    mu4 = np.zeros(4, dtype=np.float64)
    for group, mass in artifact["mu"].items():
        mu4[parse_time_block(str(group))] += float(mass)
    total = float(mu4.sum())
    if total <= 0:
        raise RuntimeError("frozen mu 4-block marginal is empty")
    mu4 = mu4 / total
    return [float(x) for x in mu4]


def _pi4_from_train_generator(atomic, spatial_to_client: dict[str, str]) -> tuple[list[float], dict]:
    from raven_mcs.e3.real_runner.generator_r3 import _block_from_stratum, build_joint_pi_opp

    client_ids, strata_by_client = _train_pools(atomic, spatial_to_client)
    joint = build_joint_pi_opp(client_ids, strata_by_client)
    pi4 = np.zeros(4, dtype=np.float64)
    for (_client, stratum), mass in joint.items():
        pi4[_block_from_stratum(stratum)] += float(mass)
    total = float(pi4.sum())
    if total <= 0:
        raise RuntimeError("frozen pi_opp 4-block marginal is empty")
    pi4 = pi4 / total
    meta = {
        "n_clients": len(client_ids),
        "n_joint_pairs": len(joint),
        "theta_align": 1.25,
        "tail_blocks": [2, 3],
        "split": "train",
        "constructor": "build_joint_pi_opp",
    }
    return [float(x) for x in pi4], meta


def compute_one(dataset: str) -> dict:
    from raven_mcs.e3.canary.dataset_load import load_paper_dataset, load_spatial_to_client
    from raven_mcs.e3.target_pair.target_wiring import load_frozen_target_artifact

    artifact = load_frozen_target_artifact(ROOT, dataset)
    ds = load_paper_dataset(ROOT, dataset)
    spatial_to_client = load_spatial_to_client(ROOT, dataset)
    mu4 = _mu4_from_frozen(artifact)
    pi4, pi_meta = _pi4_from_train_generator(ds.atomic_df, spatial_to_client)
    gaps = [mu4[g] - pi4[g] for g in range(4)]
    g_star = int(np.argmax(np.asarray(gaps)))  # lowest index on ties
    return {
        "dataset": dataset,
        "g_star": g_star,
        "mu_4": {f"block{g}": mu4[g] for g in range(4)},
        "pi_opp_4": {f"block{g}": pi4[g] for g in range(4)},
        "gap_mu_minus_piopp": {f"block{g}": gaps[g] for g in range(4)},
        "mu_source": "frozen_target_artifact_marginalized_by_parse_time_block",
        "mu_note": "P2 public target (TEST-support construction in the sealed artifact), not G3 EventTrace mu_test",
        "pi_opp_source": "build_joint_pi_opp on train-split client-stratum support",
        "pi_opp_meta": pi_meta,
        "artifact_path": artifact.get("_artifact_path"),
        "artifact_sha256": artifact.get("_artifact_sha256"),
        "tie_break": "lowest_g",
    }


def main() -> None:
    payload = {
        "gate": "G6",
        "protocol": "post_review/G6_cannot_copy_endpoint/PROTOCOL.md",
        "scored": False,
        "datasets": {},
    }
    for dataset in DATASETS:
        payload["datasets"][dataset] = compute_one(dataset)
    payload["compute_gstar_sha256"] = _sha_file(Path(__file__))
    out = OUT / "GSTAR.json"
    if out.is_file():
        raise RuntimeError(f"GSTAR.json already exists; refuse overwrite: {out}")
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({ds: rec["g_star"] for ds, rec in payload["datasets"].items()}))


if __name__ == "__main__":
    main()
