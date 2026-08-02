from __future__ import annotations

import json
import inspect
from pathlib import Path

import numpy as np
import pandas as pd

from raven_mcs.experiments.e1_entry import (
    frozen_client_mapping_hashes,
    frozen_group_hashes,
    run_official_method,
)
from raven_mcs.models.features import extract_features, utc_weekday_from_unix_hours
from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import load_yaml

ROOT = Path(__file__).resolve().parents[2]


def _unix_hours(text: str) -> float:
    return pd.Timestamp(text).timestamp() / 3600.0


def test_weekday_epoch_thursday() -> None:
    assert int(utc_weekday_from_unix_hours(np.array([0]))[0]) == 3


def test_weekday_known_monday() -> None:
    assert int(utc_weekday_from_unix_hours(
        np.array([_unix_hours("1970-01-05T00:00:00Z")]),
    )[0]) == 0


def test_weekday_known_sunday() -> None:
    assert int(utc_weekday_from_unix_hours(
        np.array([_unix_hours("2026-08-02T00:00:00Z")]),
    )[0]) == 6


def test_weekday_timezone_matches_grouping() -> None:
    protocol = load_yaml(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml",
    )
    assert protocol["target_group_timezone"] == "UTC"


def test_common_ndmf_weekday_feature_correct() -> None:
    _, _, weekday, _ = extract_features(
        ["s"], [_unix_hours("2026-08-02T00:00:00Z")], [0], {"s": 0}, 1,
    )
    assert float(weekday[0]) == 6.0


def test_client_mapping_payload_hash_matches_canonical_payload() -> None:
    payload_hash, _ = frozen_client_mapping_hashes(ROOT)
    cfg = load_yaml(ROOT / "configs/frozen/e1_sensorscope_clients.yaml")
    expected = sha256_json({
        str(key): str(value)
        for key, value in sorted(cfg["station_to_client"].items())
    })
    assert payload_hash == expected


def test_client_mapping_file_hash_matches_bytes() -> None:
    _, file_hash = frozen_client_mapping_hashes(ROOT)
    assert file_hash == sha256_file(
        ROOT / "configs/frozen/e1_sensorscope_clients.yaml",
    )


def test_protocol_status_not_timealign_blocked() -> None:
    protocol = load_yaml(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml",
    )
    assert protocol["authorization_status"] != (
        "BLOCKED_TIMEALIGN_BASELINE_UNRESOLVED"
    )


def test_protocol_status_not_authorized() -> None:
    protocol = load_yaml(
        ROOT / "configs/frozen/e1_sensorscope_balanced.yaml",
    )
    assert protocol["authorization_status"] in {
        "READY_FOR_TEACHER_REVIEW_AFTER_R3",
        "READY_FOR_TEACHER_REVIEW_AFTER_R4",
        "READY_FOR_FINAL_EXECUTION_AUTHORIZATION",
        "AUTHORIZED_FOR_FROZEN_EXECUTION",
    }
    assert protocol["authorization_status"] not in {
        "AUTHORIZED",
        "RUNNING",
        "PASS",
    }
    assert protocol["execution_status"] == "NOT_STARTED"


def test_target_group_payload_and_file_hashes_differ() -> None:
    payload_hash, file_hash = frozen_group_hashes(ROOT)
    assert payload_hash != file_hash


def test_summary_config_hash_is_resolved_config_hash() -> None:
    source = (
        ROOT / "scripts/aggregate_results.py"
    ).read_text(encoding="utf-8")
    assert '"config_hash": manifest["resolved_run_config_hash"]' in source


def test_no_hash_aliasing() -> None:
    source = inspect.getsource(run_official_method)
    assert '"config_hash": resolved_run_config_hash' in source
    assert '"target_group_payload_hash": target_group_payload_hash' in source
    assert '"client_mapping_file_hash": client_mapping_file_hash' in source
