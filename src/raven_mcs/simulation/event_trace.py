"""Immutable EventTrace tables + hash identity (Phase 4 / G1)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import dump_json, load_json

REQUIRED_EVENT_COLUMNS = (
    "window_id",
    "client_id",
    "risk_set_unit_ids",
    "opportunity_features",
    "observed_unit_ids",
    "O",
    "registration_time",
    "downloaded_version",
    "model_age",
    "tau",
    "device_profile",
    "network_profile",
    "compute_success",
    "compute_duration",
    "network_success",
    "network_duration",
    "arrival_time",
    "U",
    "raw_workload",
    "oracle_p",
    "oracle_q",
    "hidden_confounder",
)


class EventTraceError(ValueError):
    pass


@dataclass(frozen=True)
class EventTraceMetadata:
    dataset: str
    seed: int
    num_windows: int
    num_clients: int
    s_max: int = 5
    generator: str = "synthetic-eventtrace-v1"
    notes: tuple[str, ...] = ()


@dataclass
class EventTrace:
    events: pd.DataFrame
    metadata: EventTraceMetadata
    extras: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        missing = [c for c in REQUIRED_EVENT_COLUMNS if c not in self.events.columns]
        if missing:
            raise EventTraceError(f"EventTrace missing columns: {missing}")
        if self.events.empty:
            raise EventTraceError("EventTrace has no rows")
        if self.events[["window_id", "client_id"]].duplicated().any():
            raise EventTraceError("EventTrace rows must be unique on (window_id, client_id)")
        if not set(self.events["U"].dropna().unique()).issubset({0, 1, True, False, 0.0, 1.0}):
            raise EventTraceError("U must be boolean/0/1")
        if (self.events["oracle_p"] <= 0).any() or (self.events["oracle_q"] <= 0).any():
            raise EventTraceError("oracle p/q must be positive")
        downloaded = self.events["downloaded_version"].to_numpy(dtype=int)
        windows = self.events["window_id"].to_numpy(dtype=int)
        tau = self.events["tau"].to_numpy(dtype=int)
        if (
            np.any(downloaded < 0)
            or np.any(downloaded > windows)
            or np.any(tau < 0)
            or np.any(tau > int(self.metadata.num_windows))
            or np.any(tau != windows - downloaded)
        ):
            raise EventTraceError(
                "downloaded_version/tau must satisfy 0 <= tau = "
                "window_id - downloaded_version <= num_windows"
            )
        model_age = self.events["model_age"].to_numpy(dtype=float)
        if not np.allclose(model_age, tau.astype(float), rtol=0.0, atol=0.0):
            raise EventTraceError("model_age must equal tau")
        usable = self.events["U"].to_numpy(dtype=int) == 1
        if np.any(usable & (tau > int(self.metadata.s_max))):
            raise EventTraceError("U=1 requires tau <= s_max")
        if np.any((tau > int(self.metadata.s_max)) & usable):
            raise EventTraceError("expired updates must be unusable")


def synthesize_event_trace(
    *,
    num_windows: int = 5,
    num_clients: int = 3,
    units_per_client: int = 4,
    seed: int = 26001,
    observation_rate: float = 0.3,
    usable_rate: float = 0.7,
) -> EventTrace:
    """Deterministic synthetic EventTrace for G1/G2 unit tests."""
    rng = np.random.default_rng(int(seed))
    rows: list[dict[str, Any]] = []
    for window_id in range(int(num_windows)):
        for client_index in range(int(num_clients)):
            client_id = f"client-{client_index:03d}"
            risk = [f"u{client_index}_{window_id}_{j}" for j in range(units_per_client)]
            o_flags = rng.random(units_per_client) < observation_rate
            observed = [unit for unit, flag in zip(risk, o_flags) if flag]
            # Keep successes deterministic-friendly for window-gate fixtures.
            compute_success = True
            network_success = True
            usable = bool(rng.random() < usable_rate)
            rows.append(
                {
                    "window_id": int(window_id),
                    "client_id": client_id,
                    "risk_set_unit_ids": list(risk),
                    "opportunity_features": {
                        "hour_block": int(window_id % 4),
                        "client_bias": float(client_index),
                    },
                    "observed_unit_ids": list(observed),
                    "O": {unit: True for unit in observed},
                    "registration_time": float(window_id) + 0.1 * client_index,
                    "downloaded_version": int(window_id),
                    "model_age": 0,
                    "tau": 0,
                    "device_profile": "synthetic-phone",
                    "network_profile": "synthetic-wifi",
                    "compute_success": compute_success,
                    "compute_duration": float(rng.uniform(0.1, 1.0)),
                    "network_success": network_success,
                    "network_duration": float(rng.uniform(0.05, 0.5)),
                    "arrival_time": float(window_id) + 0.5 + 0.01 * client_index,
                    "U": int(usable),
                    "raw_workload": float(len(observed)),
                    "oracle_p": float(observation_rate),
                    "oracle_q": float(usable_rate),
                    "hidden_confounder": 0.0,
                }
            )
    events = pd.DataFrame(rows)
    meta = EventTraceMetadata(
        dataset="synthetic",
        seed=int(seed),
        num_windows=int(num_windows),
        num_clients=int(num_clients),
        notes=("Synthetic fixture only; not a paper-trace substitute",),
    )
    trace = EventTrace(events=events, metadata=meta)
    trace.validate()
    return trace


def _frame_for_parquet(events: pd.DataFrame) -> pd.DataFrame:
    frame = events.copy()
    for column in ("risk_set_unit_ids", "opportunity_features", "observed_unit_ids", "O"):
        frame[column] = frame[column].map(
            lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"))
        )
    return frame


def compute_trace_hash(events_sha256: str, metadata_sha256: str, metadata: Mapping[str, Any]) -> str:
    return sha256_json(
        {
            "events_sha256": events_sha256,
            "metadata_sha256": metadata_sha256,
            "metadata": dict(metadata),
        }
    )


def freeze_event_trace(trace: EventTrace, output_dir: Path) -> dict[str, Any]:
    """Write immutable parquet+metadata and return identity including trace hash."""
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite EventTrace directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    trace.validate()
    events_path = output_dir / "events.parquet"
    meta_path = output_dir / "metadata.json"
    _frame_for_parquet(trace.events).to_parquet(events_path, index=False)
    meta_dict = asdict(trace.metadata)
    dump_json(meta_dict, meta_path)
    events_sha = sha256_file(events_path)
    meta_sha = sha256_file(meta_path)
    identity = {
        "events_sha256": events_sha,
        "metadata_sha256": meta_sha,
        "trace_hash": compute_trace_hash(events_sha, meta_sha, meta_dict),
        "metadata": meta_dict,
    }
    dump_json(identity, output_dir / "trace_identity.json")
    return identity


def load_event_trace(trace_dir: Path) -> tuple[EventTrace, dict[str, Any]]:
    trace_dir = Path(trace_dir)
    identity = load_json(trace_dir / "trace_identity.json")
    raw_meta = load_json(trace_dir / "metadata.json")
    if isinstance(raw_meta.get("notes"), list):
        raw_meta["notes"] = tuple(raw_meta["notes"])
    meta = EventTraceMetadata(**raw_meta)
    frame = pd.read_parquet(trace_dir / "events.parquet")
    for column in ("risk_set_unit_ids", "opportunity_features", "observed_unit_ids", "O"):
        frame[column] = frame[column].map(json.loads)
    trace = EventTrace(events=frame, metadata=meta)
    trace.validate()
    return trace, identity


def verify_event_trace_hash(trace_dir: Path, expected_hash: str | None = None) -> list[str]:
    """G1 helper: recompute payload hashes and compare to frozen identity."""
    trace_dir = Path(trace_dir)
    identity_path = trace_dir / "trace_identity.json"
    if not identity_path.exists():
        return [f"Missing trace identity: {identity_path}"]
    identity = load_json(identity_path)
    errors: list[str] = []
    events_hash = sha256_file(trace_dir / "events.parquet")
    meta_hash = sha256_file(trace_dir / "metadata.json")
    if events_hash != identity.get("events_sha256"):
        errors.append("events.parquet hash mismatch")
    if meta_hash != identity.get("metadata_sha256"):
        errors.append("metadata.json hash mismatch")
    recomputed = compute_trace_hash(
        events_hash, meta_hash, identity.get("metadata", {})
    )
    if recomputed != identity.get("trace_hash"):
        errors.append("trace_hash mismatch against payload hashes")
    if expected_hash is not None and expected_hash != identity.get("trace_hash"):
        errors.append("caller expected_hash does not match frozen identity")
    return errors


def assert_methods_share_trace(method_trace_hashes: Mapping[str, str]) -> None:
    values = set(method_trace_hashes.values())
    if len(values) != 1:
        raise EventTraceError(
            f"Methods disagree on EventTrace hash: {dict(method_trace_hashes)}"
        )
