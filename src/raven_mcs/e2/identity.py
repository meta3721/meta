"""Read-only E1 target identity loaders for E2 numeric scenarios."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from raven_mcs.data.target import GroupMapper, TargetBuilder
from raven_mcs.experiments.e1_entry import add_e1_groups, sensorscope_dataset
from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import dump_json, load_json, load_yaml

ROOT = Path(__file__).resolve().parents[3]
IDENTITY_PATH = ROOT / "configs/frozen/e2_numeric/e1_target_identity.json"
ATOMIC_WEIGHT_PATH = ROOT / "configs/frozen/e2_numeric/e1_atomic_target_weights.parquet"
HEAD_TAIL_PATH = ROOT / "configs/frozen/e2_numeric/e1_head_tail_mapping.parquet"
SUPPORTED_PATH = ROOT / "configs/frozen/e2_numeric/e1_supported_test_units.parquet"
UNIFORM_FORBIDDEN = "fixed_atomic_uniform_over_supported_groups"


class E2IdentityError(RuntimeError):
    """Raised when E1 identity inheritance fails."""


def _canonical_group_id(value: Any) -> str:
    """Normalize group ids so int/float/str forms compare equal."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        raise E2IdentityError("group id is missing")
    if isinstance(value, (bool, np.bool_)):
        return str(value)
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        as_float = float(value)
        if as_float.is_integer():
            return str(int(as_float))
        return repr(as_float)
    text = str(value).strip()
    try:
        as_float = float(text)
        if as_float.is_integer():
            return str(int(as_float))
    except ValueError:
        pass
    return text


def _readonly_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a defensive deep copy (callers must not mutate identity frames)."""
    return frame.copy(deep=True)


def recompute_e1_atomic_target_weights(root: Path | None = None) -> pd.DataFrame:
    root = Path(root or ROOT)
    dataset = sensorscope_dataset(root)
    grouped = add_e1_groups(dataset.atomic_df)
    masses = TargetBuilder(
        group_mapper=GroupMapper(column="target_group_main"),
    ).build(grouped, split="test")
    frame = (
        masses.atom_mass.rename("target_weight")
        .rename_axis("unit_id")
        .reset_index()
        .sort_values("unit_id")
        .reset_index(drop=True)
    )
    frame["unit_id"] = frame["unit_id"].astype(str)
    frame["target_weight"] = frame["target_weight"].astype(np.float64)
    group_map = {
        str(unit): _canonical_group_id(group)
        for unit, group in grouped.set_index("unit_id")["target_group_main"].items()
    }
    frame["target_group_main"] = frame["unit_id"].map(group_map)
    frame["support_flag"] = True
    return frame


def build_calibration_only_head_tail(
    root: Path | None = None,
) -> pd.DataFrame:
    """Deterministic head/tail from train-split group difficulty only.

    E1 evaluates head/tail via R_g at run time; E2 freezes a calibration-only
    partition so scenario directions do not depend on test outcomes.
    """
    root = Path(root or ROOT)
    dataset = sensorscope_dataset(root)
    grouped = add_e1_groups(dataset.atomic_df)
    train = grouped.loc[grouped["split"].astype(str) == "train"].copy()
    train["target_group_main"] = train["target_group_main"].map(_canonical_group_id)
    stats = (
        train.groupby("target_group_main", sort=True)["target_value"]
        .agg(count="count", mse=lambda s: float(np.mean(np.square(s - s.mean()))))
        .reset_index()
    )
    stats["target_group_main"] = stats["target_group_main"].map(_canonical_group_id)
    if len(stats) < 2:
        raise E2IdentityError("insufficient groups for head/tail freeze")
    ranked = stats.sort_values(["mse", "target_group_main"], ascending=[True, True])
    head_group = _canonical_group_id(ranked.iloc[0]["target_group_main"])
    tail_group = _canonical_group_id(ranked.iloc[-1]["target_group_main"])
    if head_group == tail_group:
        raise E2IdentityError("head and tail groups must differ")
    atomic = recompute_e1_atomic_target_weights(root)
    roles = []
    for group in atomic["target_group_main"].map(_canonical_group_id):
        if group == tail_group:
            roles.append("tail")
        elif group == head_group:
            roles.append("head")
        else:
            roles.append("neutral")
    out = atomic[["unit_id", "target_group_main"]].copy()
    out["target_group_main"] = out["target_group_main"].map(_canonical_group_id)
    out["role"] = roles
    out["tail_score"] = out["role"].map({"tail": 1, "head": -1, "neutral": 0}).astype(np.int8)
    if (out["role"] == "head").sum() == 0 or (out["role"] == "tail").sum() == 0:
        raise E2IdentityError(
            f"head/tail freeze empty after mapping "
            f"(head={head_group!r}, tail={tail_group!r})"
        )
    return out.sort_values("unit_id").reset_index(drop=True)


def materialize_e1_target_identity(root: Path | None = None) -> dict[str, Any]:
    root = Path(root or ROOT)
    out_dir = root / "configs/frozen/e2_numeric"
    out_dir.mkdir(parents=True, exist_ok=True)

    atomic = recompute_e1_atomic_target_weights(root)
    atomic.to_parquet(ATOMIC_WEIGHT_PATH, index=False)
    atomic_records = [
        {"unit_id": str(row.unit_id), "target_weight": float(row.target_weight)}
        for row in atomic.itertuples(index=False)
    ]
    atomic_hash = sha256_json(atomic_records)
    expected = load_json(root / "configs/frozen/e1_pi_target_manifest.json")[
        "atomic_target_weight_hash"
    ]
    if atomic_hash != expected:
        raise E2IdentityError(
            f"atomic target hash mismatch: {atomic_hash} != {expected}"
        )

    head_tail = build_calibration_only_head_tail(root)
    head_tail.to_parquet(HEAD_TAIL_PATH, index=False)
    head_tail_hash = sha256_json(
        head_tail[["unit_id", "role", "tail_score"]].to_dict(orient="records")
    )

    supported = atomic[["unit_id", "support_flag", "target_group_main"]].copy()
    supported.to_parquet(SUPPORTED_PATH, index=False)
    supported_hash = sha256_json(
        supported.sort_values("unit_id").to_dict(orient="records")
    )

    group_path = root / "configs/frozen/e1_sensorscope_groups.yaml"
    client_path = root / "configs/frozen/e1_sensorscope_clients.yaml"
    pi_path = root / "configs/frozen/e1_pi_target_client_stratum.parquet"
    protocol_path = root / "configs/frozen/e1_r2_protocol.yaml"
    group_cfg = load_yaml(group_path)
    client_cfg = load_yaml(client_path)
    pi_manifest = load_json(root / "configs/frozen/e1_pi_target_manifest.json")

    identity = {
        "schema_version": 1,
        "e1_formal_execution_commit": "e8bd1fc777431c2609def257a04fba093f0daf24",
        "e1_protocol_file": protocol_path.relative_to(root).as_posix(),
        "e1_protocol_payload_hash": sha256_file(protocol_path),
        "atomic_target_weight_file": ATOMIC_WEIGHT_PATH.relative_to(root).as_posix(),
        "atomic_target_weight_hash": atomic_hash,
        "client_stratum_target_mass_file": pi_path.relative_to(root).as_posix(),
        "client_stratum_target_mass_hash": pi_manifest["client_stratum_target_mass_hash"],
        "target_group_file": group_path.relative_to(root).as_posix(),
        "target_group_payload_hash": group_cfg["mapping_hash"],
        "head_tail_mapping_file": HEAD_TAIL_PATH.relative_to(root).as_posix(),
        "head_tail_mapping_hash": head_tail_hash,
        "head_tail_construction": (
            "calibration-only train-split group MSE extremes; "
            "E1 runtime R_g selection is not a frozen file"
        ),
        "client_mapping_file": client_path.relative_to(root).as_posix(),
        "client_mapping_hash": sha256_json({
            str(k): str(v) for k, v in sorted(client_cfg["station_to_client"].items())
        }),
        "supported_test_unit_file": SUPPORTED_PATH.relative_to(root).as_posix(),
        "supported_test_unit_hash": supported_hash,
        "pi_target_file": pi_path.relative_to(root).as_posix(),
        "pi_target_file_hash": sha256_file(pi_path),
        "total_target_mass": float(atomic["target_weight"].sum()),
        "target_unit_count": int(len(atomic)),
        "head_unit_count": int((head_tail["role"] == "head").sum()),
        "tail_unit_count": int((head_tail["role"] == "tail").sum()),
        "uniform_target_fallback": "FORBIDDEN",
        "deprecated_placeholder": UNIFORM_FORBIDDEN,
    }
    dump_json(identity, IDENTITY_PATH)
    return identity


def load_e1_target_identity(root: Path | None = None) -> Mapping[str, Any]:
    root = Path(root or ROOT)
    path = root / "configs/frozen/e2_numeric/e1_target_identity.json"
    if not path.is_file():
        raise E2IdentityError(f"missing identity file: {path}")
    identity = load_json(path)
    if identity.get("uniform_target_fallback") != "FORBIDDEN":
        raise E2IdentityError("uniform target fallback is not forbidden")
    # Re-verify atomic hash against E1 manifest.
    expected = load_json(root / "configs/frozen/e1_pi_target_manifest.json")[
        "atomic_target_weight_hash"
    ]
    if identity["atomic_target_weight_hash"] != expected:
        raise E2IdentityError("identity atomic hash does not match E1 manifest")
    return copy.deepcopy(identity)


def load_e1_atomic_target_weights(root: Path | None = None) -> pd.DataFrame:
    root = Path(root or ROOT)
    identity = load_e1_target_identity(root)
    path = root / identity["atomic_target_weight_file"]
    frame = pd.read_parquet(path).sort_values("unit_id").reset_index(drop=True)
    records = [
        {"unit_id": str(row.unit_id), "target_weight": float(row.target_weight)}
        for row in frame.itertuples(index=False)
    ]
    digest = sha256_json(records)
    if digest != identity["atomic_target_weight_hash"]:
        raise E2IdentityError("atomic target weights failed hash verification")
    if abs(float(frame["target_weight"].sum()) - 1.0) > 1e-12:
        raise E2IdentityError("atomic target weights do not sum to one")
    return _readonly_frame(frame)


def load_e1_head_tail_mapping(root: Path | None = None) -> pd.DataFrame:
    root = Path(root or ROOT)
    identity = load_e1_target_identity(root)
    path = root / identity["head_tail_mapping_file"]
    frame = pd.read_parquet(path).sort_values("unit_id").reset_index(drop=True)
    digest = sha256_json(
        frame[["unit_id", "role", "tail_score"]].to_dict(orient="records")
    )
    if digest != identity["head_tail_mapping_hash"]:
        raise E2IdentityError("head/tail mapping failed hash verification")
    if set(frame["tail_score"].unique()) - {-1, 0, 1}:
        raise E2IdentityError("tail scores must be in {-1,0,+1}")
    if (frame["role"] == "head").sum() == 0 or (frame["role"] == "tail").sum() == 0:
        raise E2IdentityError("head/tail partitions must be nonempty")
    return _readonly_frame(frame)


def load_e1_supported_test_units(root: Path | None = None) -> pd.DataFrame:
    root = Path(root or ROOT)
    identity = load_e1_target_identity(root)
    path = root / identity["supported_test_unit_file"]
    frame = pd.read_parquet(path).sort_values("unit_id").reset_index(drop=True)
    digest = sha256_json(frame.to_dict(orient="records"))
    if digest != identity["supported_test_unit_hash"]:
        raise E2IdentityError("supported test units failed hash verification")
    if not bool(frame["support_flag"].all()):
        raise E2IdentityError("supported units contain unsupported rows")
    return _readonly_frame(frame)


def reject_uniform_target_fallback(value: str | None) -> None:
    if value == UNIFORM_FORBIDDEN:
        raise E2IdentityError(
            "deprecated placeholder fixed_atomic_uniform_over_supported_groups "
            "is forbidden at runtime; reuse E1 atomic target weights"
        )
