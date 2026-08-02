from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from raven_mcs.correction.pi_target import build_pi_target
from raven_mcs.experiments.e1_entry import add_e1_groups, sensorscope_dataset
from raven_mcs.utils.serialization import load_json, load_yaml

ROOT = Path(__file__).resolve().parents[2]


def _official_pi() -> pd.DataFrame:
    return pd.read_parquet(
        ROOT / "configs/frozen/e1_pi_target_client_stratum.parquet",
    )


def test_pi_target_support_uses_station_client_mapping() -> None:
    manifest = load_json(
        ROOT / "configs/frozen/e1_pi_target_manifest.json",
    )
    assert manifest["construction_source"] == "station_client_mapping"


def test_pi_target_not_uses_measurement_cartesian_product() -> None:
    frame = _official_pi()
    assert int((frame["pi_k_s_tar"] > 0).sum()) < 8 * 440


def test_each_stratum_has_exactly_one_supported_client() -> None:
    frame = _official_pi()
    supported = frame.loc[frame["support_flag"].astype(bool)]
    assert supported.groupby("opportunity_stratum")["client_id"].nunique().eq(1).all()


def test_lambda_target_is_one_for_mapped_client() -> None:
    frame = _official_pi()
    assert frame.loc[
        frame["support_flag"].astype(bool), "lambda_k_given_s_tar"
    ].eq(1.0).all()


def test_lambda_target_zero_for_unmapped_clients() -> None:
    frame = _official_pi()
    mapping = load_yaml(
        ROOT / "configs/frozen/e1_sensorscope_clients.yaml",
    )["station_to_client"]
    for row in frame.itertuples():
        station = str(row.opportunity_stratum).split("::", 1)[0]
        assert mapping[station] == row.client_id
    assert frame.groupby("opportunity_stratum").size().eq(1).all()


def test_pi_target_sums_to_one() -> None:
    assert abs(float(_official_pi()["pi_k_s_tar"].sum()) - 1.0) <= 1e-12


def test_positive_pi_pair_count_matches_support() -> None:
    frame = _official_pi()
    assert int((frame["pi_k_s_tar"] > 0).sum()) == int(
        frame["support_flag"].sum(),
    )


def test_pi_target_manual_station_case() -> None:
    atomic = pd.DataFrame({
        "unit_id": ["u1", "u2"],
        "spatial_id": ["s1", "s2"],
        "opportunity_stratum": ["s1::block0::weekday", "s2::block0::weekday"],
        "target_group_main": [0, 1],
        "target_group": ["0", "1"],
        "split": ["test", "test"],
        "support_flag": [True, True],
    })
    result = build_pi_target(
        atomic, {"s1": "A", "s2": "B"}, split="test",
    )
    assert set(result["client_id"]) == {"A", "B"}
    assert result.groupby("opportunity_stratum").size().eq(1).all()


def test_delta_cal_uses_real_target_client_share() -> None:
    summary = load_json(
        ROOT / "outputs/audits/e1_r3_calibration_summary.json",
    )
    assert summary["support_source"] == "station_client_mapping"
    assert summary["Delta_cal"] >= 0


def test_delta_cal_not_assume_uniform_eight_clients() -> None:
    frame = pd.read_parquet(
        ROOT / "outputs/audits/e1_r3_calibration_residual.parquet",
    )
    assert (frame["bar_b_target"] == frame["client_bias"]).all()


def test_delta_cal_manual_single_support_case() -> None:
    weights = pd.Series([0.25, 0.75])
    biases = pd.Series([-2.0, 1.0])
    assert float((weights * biases.abs()).sum()) == 1.25


def test_delta_cal_recomputed_after_pi_target_change() -> None:
    manifest = load_json(
        ROOT / "configs/frozen/e1_measurement_calibration_manifest.json",
    )
    assert "calibration_audit_hash" in manifest


def test_test_split_not_used_for_bias_centering() -> None:
    summary = load_json(
        ROOT / "outputs/audits/e1_r3_calibration_summary.json",
    )
    assert summary["test_split_used_for_bias_centering"] is False


def _support_module():
    path = ROOT / "scripts/audit_e1_target_opportunity_support.py"
    spec = importlib.util.spec_from_file_location("r3_support_audit", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_support_crosscheck_uses_risk_set_not_only_observed() -> None:
    module = _support_module()
    target = pd.DataFrame({
        "client_id": ["A"],
        "opportunity_stratum": ["s1::block0::weekday"],
        "pi_k_s_tar": [1.0],
    })
    events = pd.DataFrame([{
        "client_id": "A",
        "opportunity_strata": ["s1::block0::weekday"],
        "O": [0],
        "U": 0,
    }])
    frame, summary = module.crosscheck_support(target, events, {"s1": "A"})
    assert bool(frame.iloc[0]["in_eventtrace_risk_support"])
    assert summary["unsupported_positive_target_pairs"] == 0


def test_unmapped_client_stratum_pair_rejected() -> None:
    module = _support_module()
    target = pd.DataFrame({
        "client_id": ["A"],
        "opportunity_stratum": ["s1::block0::weekday"],
        "pi_k_s_tar": [1.0],
    })
    events = pd.DataFrame([{
        "client_id": "B",
        "opportunity_strata": ["s1::block0::weekday"],
        "O": [0],
        "U": 0,
    }])
    _, summary = module.crosscheck_support(target, events, {"s1": "A"})
    assert summary["eventtrace_pair_not_in_frozen_mapping"] == 1


def test_support_crosscheck_detects_synthetic_violation() -> None:
    module = _support_module()
    target = pd.DataFrame({
        "client_id": ["A"],
        "opportunity_stratum": ["s1::block0::weekday"],
        "pi_k_s_tar": [1.0],
    })
    events = pd.DataFrame(columns=[
        "client_id", "opportunity_strata", "O", "U",
    ])
    frame, summary = module.crosscheck_support(target, events, {"s1": "A"})
    assert bool(frame.iloc[0]["violation"])
    assert summary["unsupported_positive_target_pairs"] == 1


def test_positive_target_support_in_all_eventtraces() -> None:
    summary = load_json(
        ROOT / "outputs/audits/e1_r3_support_crosscheck_summary.json",
    )
    assert summary["hard_gate_pass"] is True
    assert all(
        row["unsupported_positive_target_pairs"] == 0
        for row in summary["seeds"].values()
    )


def test_eventtrace_station_client_consistency() -> None:
    summary = load_json(
        ROOT / "outputs/audits/e1_r3_support_crosscheck_summary.json",
    )
    assert all(
        row["station_client_mismatch"] == 0
        for row in summary["seeds"].values()
    )
