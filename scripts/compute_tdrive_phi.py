#!/usr/bin/env python3
"""Compute T-Drive zero-target-mass fraction phi (TD-R-E3 Phase 1).

Follows post_review/C1_tdrive_rank/HANDOFF_EXECUTOR.md.
Measures only. Does not train. Does not edit the manuscript.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from raven_mcs.utils.hashing import sha256_file  # noqa: E402

OUT = ROOT / "results_tdrive_rank" / "round_v1"
MASTER = ROOT / "tdrive_protocol_seal_r1" / "13_freeze" / "TDRIVE_REAL_MOBILITY_PROTOCOL_MASTER_R1.json"
ATOMIC_PATH = ROOT / "data" / "processed" / "tdrive_speed" / "atomic_units.parquet"
MEAS_PATH = ROOT / "data" / "processed" / "tdrive_speed" / "client_measurements.parquet"
ZERO = 0.0
EXPECTED_TRAIN_UNITS = 285659
G3_TRAIN_R_REF = 0.443
PROCESSED_KEYS = (
    "data/processed/tdrive_speed/atomic_units.parquet",
    "data/processed/tdrive_speed/client_measurements.parquet",
)


def _git_commit() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "UNKNOWN"


def verify_processed_hashes(master: dict) -> list[dict]:
    source = dict(master.get("source_hashes") or {})
    rows = []
    for rel in PROCESSED_KEYS:
        path = ROOT / rel
        if not path.is_file():
            raise FileNotFoundError(rel)
        expected = str(source[rel])
        got = sha256_file(path)
        rows.append(
            {
                "path": rel,
                "expected": expected,
                "got": got,
                "match": got == expected,
            }
        )
    return rows


def verify_source_hashes(master: dict) -> list[dict]:
    source = dict(master.get("source_hashes") or {})
    rows = []
    for rel, expected in source.items():
        if rel in PROCESSED_KEYS:
            continue
        path = ROOT / rel
        if not path.is_file():
            rows.append(
                {
                    "path": rel,
                    "expected": expected,
                    "got": None,
                    "match": False,
                    "note": "missing",
                }
            )
            continue
        got = sha256_file(path)
        rows.append(
            {
                "path": rel,
                "expected": expected,
                "got": got,
                "match": got == expected,
            }
        )
    return rows


def compute_phi() -> dict:
    atomic = pd.read_parquet(ATOMIC_PATH)
    meas = pd.read_parquet(MEAS_PATH, columns=["unit_id"])
    atomic["unit_id"] = atomic["unit_id"].astype(str)
    atomic["split"] = atomic["split"].astype(str)
    atomic["opportunity_stratum"] = atomic["opportunity_stratum"].astype(str)
    meas["unit_id"] = meas["unit_id"].astype(str)

    train = atomic.loc[atomic["split"] == "train", ["unit_id", "opportunity_stratum"]].drop_duplicates(
        "unit_id"
    )
    test = atomic.loc[atomic["split"] == "test", ["unit_id", "opportunity_stratum"]].drop_duplicates(
        "unit_id"
    )
    n_train = int(len(train))
    n_test = int(len(test))
    if n_train != EXPECTED_TRAIN_UNITS:
        raise RuntimeError(
            f"train unique unit count {n_train} != sealed {EXPECTED_TRAIN_UNITS}"
        )
    if n_test <= 0:
        raise RuntimeError("empty test units")

    test_counts = test.groupby("opportunity_stratum").size()
    lambda_s = (test_counts / float(n_test)).to_dict()

    train_s = train["opportunity_stratum"].to_numpy()
    pi_i = [float(lambda_s.get(str(s), 0.0)) for s in train_s]
    n_train_zero = int(sum(1 for v in pi_i if v <= ZERO))
    phi_train_unit = n_train_zero / n_train

    train_strata = sorted(set(str(s) for s in train_s))
    n_train_pairs = int(len(train_strata))
    n_train_pairs_zero = int(sum(1 for s in train_strata if float(lambda_s.get(s, 0.0)) <= ZERO))
    phi_train_pair = n_train_pairs_zero / n_train_pairs if n_train_pairs else float("nan")

    meas_units = set(meas["unit_id"].tolist())
    train_r = train.loc[train["unit_id"].isin(meas_units)]
    n_train_r = int(len(train_r))
    pi_r = [float(lambda_s.get(str(s), 0.0)) for s in train_r["opportunity_stratum"].to_numpy()]
    n_train_r_zero = int(sum(1 for v in pi_r if v <= ZERO))
    phi_train_r = n_train_r_zero / n_train_r if n_train_r else float("nan")

    design_on = bool(n_train_zero == 0)
    scd_method = "raven" if design_on else "raven_wo_design"
    extra_full_design = scd_method != "raven"

    return {
        "n_train_units": n_train,
        "n_train_zero": n_train_zero,
        "phi_train_unit": float(phi_train_unit),
        "n_train_pairs": n_train_pairs,
        "n_train_pairs_zero": n_train_pairs_zero,
        "phi_train_pair": float(phi_train_pair),
        "n_train_R": n_train_r,
        "n_train_R_zero": n_train_r_zero,
        "phi_train_R": float(phi_train_r),
        "n_test_units": n_test,
        "n_lambda_s_positive": int(sum(1 for v in lambda_s.values() if v > ZERO)),
        "n_lambda_s": int(len(lambda_s)),
        "g3_train_R_ref": G3_TRAIN_R_REF,
        "phi_train_R_minus_g3_ref": float(phi_train_r - G3_TRAIN_R_REF),
        "design_on": design_on,
        "scd_method": scd_method,
        "full_design_diagnostic_method": "raven",
        "train_full_design_extra": extra_full_design,
        "rule": "Design_ON iff phi_train_unit == 0",
    }


def freeze_from_phi(phi: dict) -> dict:
    return {
        "experiment_id": "TD-R-E3",
        "phi_definition": "phi_train_unit",
        "phi_train_unit": float(phi["phi_train_unit"]),
        "n_train_zero": int(phi["n_train_zero"]),
        "n_train_units": int(phi["n_train_units"]),
        "rule": "Design_ON iff phi_train_unit == 0",
        "design_on": bool(phi["design_on"]),
        "scd_method": str(phi["scd_method"]),
        "full_design_diagnostic_method": "raven",
        "train_full_design_extra": bool(phi["train_full_design_extra"]),
        "gate_unused": True,
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Frozen from phi. Not from labels or residuals.",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tables").mkdir(parents=True, exist_ok=True)

    master = json.loads(MASTER.read_text(encoding="utf-8"))
    processed = verify_processed_hashes(master)
    if any(not r["match"] for r in processed):
        payload = {"status": "STOP", "reason": "PROCESSED_HASH_MISMATCH", "processed": processed}
        (OUT / "TD_R_PHI.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 2

    phi = compute_phi()
    freeze = freeze_from_phi(phi)
    source_rows = verify_source_hashes(master)
    payload = {
        "experiment_id": "TD-R-E3",
        "status": "PASS",
        "dataset": "tdrive_speed",
        "protocol_id": "TDRIVE_REAL_MOBILITY_PROTOCOL_R1",
        "pi_lookup": "Lambda_s from unique test units, uniform mass, s=opportunity_stratum",
        "zero_test": "pi <= 0.0",
        "processed_hashes": processed,
        "source_hashes_advisory": source_rows,
        "phi": phi,
        "scd_freeze": freeze,
        "git_commit": _git_commit(),
        "computed_utc": datetime.now(timezone.utc).isoformat(),
    }
    (OUT / "TD_R_PHI.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (OUT / "TD_R_SCD_FREEZE.json").write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(
        [
            {
                "dataset": "tdrive_speed",
                "n_train_units": phi["n_train_units"],
                "n_train_zero": phi["n_train_zero"],
                "phi_train_unit": phi["phi_train_unit"],
                "phi_train_pair": phi["phi_train_pair"],
                "phi_train_R": phi["phi_train_R"],
                "scd_method": phi["scd_method"],
                "design_on": phi["design_on"],
            }
        ]
    ).to_csv(OUT / "tables" / "TD_R_PHI.csv", index=False)
    print(json.dumps(freeze, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
