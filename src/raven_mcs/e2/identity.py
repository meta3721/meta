"""Read-only E1/E2 target identity loaders for E2 numeric scenarios."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import dump_json, load_json, load_yaml

ROOT = Path(__file__).resolve().parents[3]
IDENTITY_PATH = ROOT / "configs/frozen/e2_numeric/e1_target_identity.json"
ATOMIC_WEIGHT_PATH = ROOT / "configs/frozen/e2_numeric/e1_atomic_target_weights.parquet"
HEAD_TAIL_PATH = ROOT / "configs/frozen/e2_numeric/head_tail_mapping.parquet"
LEGACY_HEAD_TAIL_PATH = ROOT / "configs/frozen/e2_numeric/e1_head_tail_mapping.parquet"
SUPPORTED_PATH = ROOT / "configs/frozen/e2_numeric/e1_supported_test_units.parquet"
UNIFORM_FORBIDDEN = "fixed_atomic_uniform_over_supported_groups"
CALIBRATION_SPLIT = "validation"
BASELINE_METHOD = "flamf_timealign_adapted"
BASELINE_SEED = 27101


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
    from raven_mcs.data.target import GroupMapper, TargetBuilder
    from raven_mcs.experiments.e1_entry import add_e1_groups, sensorscope_dataset

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
    # Preserve actual support flags from TargetBuilder/dataset for supported units.
    support = masses.support_flag.reindex(frame["unit_id"]).fillna(False)
    frame["support_flag"] = support.to_numpy(dtype=bool)
    if not bool(frame["support_flag"].all()):
        raise E2IdentityError("TargetBuilder test support contains unsupported atoms")
    return frame


def _resolve_baseline_checkpoint(root: Path) -> Path:
    pattern = (
        root / "outputs/e1_r2/validation/baseline_runs" / BASELINE_METHOD
    )
    matches = sorted(pattern.glob("*/checkpoints/final.pt"))
    preferred = [
        path for path in matches
        if f"_{BASELINE_SEED}_" in path.parent.parent.name
    ]
    if preferred:
        return preferred[0]
    if matches:
        return matches[0]
    raise E2IdentityError(
        "BLOCKED_HEAD_TAIL_IDENTITY: no frozen baseline checkpoint available "
        f"under {pattern}"
    )


def build_e2_calibration_frozen_head_tail(
    root: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """H2: freeze head/tail from baseline calibration prediction MSE.

    Uses frozen flamf_timealign_adapted theta and validation-split
    mean((prediction - target)^2) by group. Never uses train-label variance
    and never uses the test split.
    """
    import torch
    from raven_mcs.experiments.e1_entry import add_e1_groups, sensorscope_dataset
    from raven_mcs.models.common_ndmf import deterministic_common_ndmf
    from raven_mcs.models.features import extract_features

    root = Path(root or ROOT)
    checkpoint = _resolve_baseline_checkpoint(root)
    dataset = sensorscope_dataset(root)
    grouped = add_e1_groups(dataset.atomic_df)
    theta = torch.load(checkpoint, map_location="cpu", weights_only=False)
    model = deterministic_common_ndmf(dataset.num_spatial, seed=BASELINE_SEED)
    model.load_state_dict(theta)
    model.eval()

    units = dataset.get_atomic_units(split=CALIBRATION_SPLIT)
    if not units:
        raise E2IdentityError("calibration split is empty")
    spatial = [unit.spatial_id for unit in units]
    absolute = [unit.absolute_time for unit in units]
    indices = [unit.time_index for unit in units]
    sp, hour, wday, trend = extract_features(
        spatial,
        absolute,
        indices,
        dict(dataset._spatial_to_idx),
        int(dataset.atomic_df["time_index"].max()) + 1,
    )
    with torch.no_grad():
        y_pred = model(sp, hour, wday, trend).cpu().numpy().astype(np.float64)
    y_true = np.asarray([unit.target_value for unit in units], dtype=np.float64)
    unit_ids = [str(unit.unit_id) for unit in units]
    group_index = grouped.set_index("unit_id")["target_group_main"]
    groups = np.asarray(
        [_canonical_group_id(group_index.at[unit_id]) for unit_id in unit_ids]
    )
    pred_hash = sha256_json({
        "unit_ids": unit_ids,
        "y_pred": y_pred.tolist(),
        "y_true": y_true.tolist(),
        "split": CALIBRATION_SPLIT,
    })
    split_ids = (
        grouped.loc[grouped["split"].astype(str) == CALIBRATION_SPLIT, "unit_id"]
        .astype(str)
        .sort_values()
        .tolist()
    )
    split_hash = sha256_json(split_ids)

    rows = []
    for group in sorted(set(groups.tolist())):
        mask = groups == group
        mse = float(np.mean(np.square(y_pred[mask] - y_true[mask])))
        rows.append({
            "target_group_main": group,
            "count": int(mask.sum()),
            "calibration_prediction_mse": mse,
            "metric": "mean((prediction-target)^2)",
            "split": CALIBRATION_SPLIT,
        })
    difficulty = pd.DataFrame(rows).sort_values(
        ["calibration_prediction_mse", "target_group_main"],
        ascending=[True, True],
    ).reset_index(drop=True)
    if len(difficulty) < 2:
        raise E2IdentityError("insufficient groups for head/tail freeze")
    head_group = _canonical_group_id(difficulty.iloc[0]["target_group_main"])
    tail_group = _canonical_group_id(difficulty.iloc[-1]["target_group_main"])
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
    mapping = atomic[["unit_id", "target_group_main"]].copy()
    mapping["target_group_main"] = mapping["target_group_main"].map(_canonical_group_id)
    mapping["role"] = roles
    mapping["tail_score"] = (
        mapping["role"].map({"tail": 1, "head": -1, "neutral": 0}).astype(np.int8)
    )
    if (mapping["role"] == "head").sum() == 0 or (mapping["role"] == "tail").sum() == 0:
        raise E2IdentityError("head/tail freeze empty after mapping")

    meta = {
        "head_tail_identity_source": "E2_CALIBRATION_FROZEN",
        "e1_frozen_head_tail_available": False,
        "calibration_split": CALIBRATION_SPLIT,
        "calibration_split_hash": split_hash,
        "baseline_method": BASELINE_METHOD,
        "baseline_seed_identity": BASELINE_SEED,
        "baseline_checkpoint": checkpoint.relative_to(root).as_posix(),
        "baseline_checkpoint_hash": sha256_file(checkpoint),
        "prediction_payload_hash": pred_hash,
        "metric": "mean((prediction-target)^2)",
        "forbidden_metric": "train_label_variance",
        "head_group": head_group,
        "tail_group": tail_group,
        "uses_test_split": False,
        "uses_formal_outcomes": False,
    }
    return mapping.sort_values("unit_id").reset_index(drop=True), difficulty, meta


def build_calibration_only_head_tail(root: Path | None = None) -> pd.DataFrame:
    """Back-compat wrapper returning only the head/tail mapping frame."""
    mapping, _, _ = build_e2_calibration_frozen_head_tail(root)
    return mapping


def audit_supported_test_identity(root: Path | None = None) -> dict[str, Any]:
    from raven_mcs.data.target import GroupMapper, TargetBuilder
    from raven_mcs.experiments.e1_entry import add_e1_groups, sensorscope_dataset

    root = Path(root or ROOT)
    atomic = recompute_e1_atomic_target_weights(root)
    e2_units = set(atomic["unit_id"].astype(str))
    dataset = sensorscope_dataset(root)
    grouped = add_e1_groups(dataset.atomic_df)
    masses = TargetBuilder(
        group_mapper=GroupMapper(column="target_group_main"),
    ).build(grouped, split="test")
    e1_units = set(masses.atom_mass.index.astype(str))
    support_true = set(
        grouped.loc[
            (grouped["split"].astype(str) == "test")
            & grouped["support_flag"].astype(bool),
            "unit_id",
        ].astype(str)
    )
    # Cross-check against E1 atomic target identity (same unit set).
    expected_hash = load_json(root / "configs/frozen/e1_pi_target_manifest.json")[
        "atomic_target_weight_hash"
    ]
    missing = sorted(e1_units - e2_units)
    extra = sorted(e2_units - e1_units)
    sym = sorted(e1_units.symmetric_difference(e2_units))
    support_missing = sorted(support_true - e2_units)
    support_extra = sorted(e2_units - support_true)
    status = (
        "PASS"
        if not sym and not support_missing and not support_extra
        else "FAIL"
    )
    payload = {
        "source_type": "e1_targetbuilder_test_support",
        "source_file": "data/processed/sensorscope/atomic_units.parquet",
        "source_rule": (
            "TargetBuilder(group_mapper=target_group_main).build(split='test') "
            "with support_flag==True; unit set equals E1 atomic target weights"
        ),
        "E1_reference_hash": expected_hash,
        "E2_reconstructed_hash": sha256_json(
            atomic[["unit_id", "support_flag", "target_group_main"]]
            .sort_values("unit_id")
            .to_dict(orient="records")
        ),
        "set_symmetric_difference_count": len(sym),
        "missing_unit_count": len(missing),
        "extra_unit_count": len(extra),
        "support_flag_symmetric_difference_count": len(
            sorted(support_true.symmetric_difference(e2_units))
        ),
        "status": status,
    }
    dump_json(payload, root / "configs/frozen/e2_numeric/supported_test_identity.json")
    return payload


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

    head_tail, difficulty, ht_meta = build_e2_calibration_frozen_head_tail(root)
    head_tail.to_parquet(HEAD_TAIL_PATH, index=False)
    head_tail.to_parquet(LEGACY_HEAD_TAIL_PATH, index=False)
    difficulty.to_parquet(
        out_dir / "group_calibration_difficulty.parquet", index=False,
    )
    head_tail_hash = sha256_json(
        head_tail[["unit_id", "role", "tail_score"]].to_dict(orient="records")
    )
    head_tail_identity = {
        **ht_meta,
        "head_tail_mapping_file": HEAD_TAIL_PATH.relative_to(root).as_posix(),
        "head_tail_mapping_hash": head_tail_hash,
        "group_calibration_difficulty_file": (
            "configs/frozen/e2_numeric/group_calibration_difficulty.parquet"
        ),
        "group_calibration_difficulty_hash": sha256_json(
            difficulty.to_dict(orient="records")
        ),
        "head_unit_count": int((head_tail["role"] == "head").sum()),
        "tail_unit_count": int((head_tail["role"] == "tail").sum()),
    }
    dump_json(head_tail_identity, out_dir / "head_tail_identity.json")

    supported = atomic[["unit_id", "support_flag", "target_group_main"]].copy()
    supported.to_parquet(SUPPORTED_PATH, index=False)
    supported_hash = sha256_json(
        supported.sort_values("unit_id").to_dict(orient="records")
    )
    support_audit = audit_supported_test_identity(root)
    if support_audit["status"] != "PASS":
        raise E2IdentityError("supported-test identity audit failed")

    group_path = root / "configs/frozen/e1_sensorscope_groups.yaml"
    client_path = root / "configs/frozen/e1_sensorscope_clients.yaml"
    pi_path = root / "configs/frozen/e1_pi_target_client_stratum.parquet"
    protocol_path = root / "configs/frozen/e1_r2_protocol.yaml"
    group_cfg = load_yaml(group_path)
    client_cfg = load_yaml(client_path)
    pi_manifest = load_json(root / "configs/frozen/e1_pi_target_manifest.json")

    identity = {
        "schema_version": 2,
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
        "head_tail_identity_source": "E2_CALIBRATION_FROZEN",
        "head_tail_construction": (
            "E2_CALIBRATION_FROZEN: validation-split baseline prediction MSE "
            "extremes; not E1 runtime R_g; not train-label variance"
        ),
        "client_mapping_file": client_path.relative_to(root).as_posix(),
        "client_mapping_hash": sha256_json({
            str(k): str(v) for k, v in sorted(client_cfg["station_to_client"].items())
        }),
        "supported_test_unit_file": SUPPORTED_PATH.relative_to(root).as_posix(),
        "supported_test_unit_hash": supported_hash,
        "supported_test_identity_file": (
            "configs/frozen/e2_numeric/supported_test_identity.json"
        ),
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
    if not path.is_file() and LEGACY_HEAD_TAIL_PATH.is_file():
        path = LEGACY_HEAD_TAIL_PATH
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
    source = identity.get("head_tail_identity_source")
    if source not in {"E1_FROZEN", "E2_CALIBRATION_FROZEN"}:
        raise E2IdentityError("head_tail_identity_source must be explicit")
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
    audit_path = root / "configs/frozen/e2_numeric/supported_test_identity.json"
    if audit_path.is_file():
        audit = load_json(audit_path)
        if int(audit.get("set_symmetric_difference_count", 1)) != 0:
            raise E2IdentityError("supported-test symmetric difference nonzero")
    return _readonly_frame(frame)


def reject_uniform_target_fallback(value: str | None) -> None:
    if value == UNIFORM_FORBIDDEN:
        raise E2IdentityError(
            "deprecated placeholder fixed_atomic_uniform_over_supported_groups "
            "is forbidden at runtime; reuse E1 atomic target weights"
        )
