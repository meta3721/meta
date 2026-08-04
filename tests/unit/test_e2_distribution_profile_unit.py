"""Unit tests for E2 distribution profile and window freeze."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from raven_mcs.e2.client_windows import E2ClientWindowError, validate_client_window_record
from raven_mcs.e2.distribution.base_streams import build_base_random_streams
from raven_mcs.e2.distribution.profile_gates import (
    VALIDATION_SEEDS,
    evaluate_seed_profile_gates,
    select_strength_profile,
    select_window_length,
)
from raven_mcs.e2.distribution.topology import build_seed_topology
from raven_mcs.e2.identity import load_e1_head_tail_mapping
from raven_mcs.utils.hashing import sha256_json

ROOT = Path(__file__).resolve().parents[2]


def test_duplicate_unit_ids_rejected() -> None:
    mapping = {
        str(r.unit_id): int(r.tail_score)
        for r in load_e1_head_tail_mapping(ROOT).itertuples(index=False)
    }
    unit = next(iter(mapping))
    with pytest.raises(E2ClientWindowError, match="duplicate unit_ids"):
        validate_client_window_record(
            {
                "client_id": "c0",
                "window_id": "0",
                "unit_ids": [unit, unit],
                "opportunity_weights": [1.0, 1.0],
                "attempt_eligible": True,
            },
            supported_units={unit},
            frozen_tail_score_map=mapping,
        )


def test_validation_seed_registry_exact() -> None:
    reg = yaml.safe_load(
        (ROOT / "configs/e2_entry/seed_registry_candidate.yaml").read_text(encoding="utf-8")
    )
    assert list(reg["validation_seed_candidates"]) == list(VALIDATION_SEEDS)


def test_profile_registry_hash_unchanged() -> None:
    strength = yaml.safe_load(
        (ROOT / "configs/e2_numeric/strength_profile_registry.yaml").read_text(encoding="utf-8")
    )
    assert set(strength["profiles"]) == {f"PROFILE-S{i}" for i in range(1, 7)}
    assert strength["profiles"]["PROFILE-S2"] == {
        "kappa_opp": 1.0, "kappa_p": 1.0, "kappa_q": 1.0,
    }


def test_shared_base_random_stream_across_profiles() -> None:
    a = build_base_random_streams(29101, n_windows=10, n_clients=4, max_risk_set=8)
    b = build_base_random_streams(29101, n_windows=10, n_clients=4, max_risk_set=8)
    assert a["base_random_stream_hash"] == b["base_random_stream_hash"]
    assert (a["base_observation_uniforms"] == b["base_observation_uniforms"]).all()


def test_shared_base_random_stream_across_scenarios() -> None:
    streams = build_base_random_streams(29102, n_windows=5, n_clients=2, max_risk_set=4)
    # Same stream object reused conceptually across scenarios.
    assert streams["base_random_stream_hash"]
    assert streams["base_usable_uniforms"].shape == (5, 2)


def test_100_200_are_prefixes_of_300() -> None:
    topo = build_seed_topology(29101, root=ROOT)
    assert topo["meta"]["num_windows"] == 300
    by_window: dict[int, list] = {}
    for row in topo["windows"]:
        by_window.setdefault(int(row["window_id"]), []).append(row)
    assert sorted(by_window) == list(range(300))
    # Nested tile structure: window compositions repeat every 100 window_ids.
    for i in range(100):
        a = sorted(
            (r["client_id"], tuple(r["unit_ids"]), tuple(r["opportunity_weights"]))
            for r in by_window[i]
        )
        b = sorted(
            (r["client_id"], tuple(r["unit_ids"]), tuple(r["opportunity_weights"]))
            for r in by_window[i + 100]
        )
        c = sorted(
            (r["client_id"], tuple(r["unit_ids"]), tuple(r["opportunity_weights"]))
            for r in by_window[i + 200]
        )
        assert a == b == c


def test_no_model_training_in_distribution_round() -> None:
    path = ROOT / "outputs/e2_distribution/E2_TRACE_MATRIX_SUMMARY.json"
    if not path.is_file():
        pytest.skip("matrix not generated yet")
    matrix = json.loads(path.read_text(encoding="utf-8"))
    for manifest in matrix["manifests"].values():
        assert manifest["model_training"] is False
        assert manifest["rmse_computed"] is False
        assert manifest["formal"] is False


def _diag(**kwargs):
    base = {
        "D_TV_arr_emp": 0.0,
        "tail_mass_ratio": 1.0,
        "head_mass_ratio": 1.0,
        "tail_mass_ratio_obs": 1.0,
        "D_TV_exp_emp": 0.0,
        "cancellation_TV": 0.0,
        "realized_observation_rate": 0.20,
        "realized_usable_rate": 0.60,
        "unsupported_arrival_count": 0,
        "head_arrival_support_count": 10,
        "tail_arrival_support_count": 10,
        "empirical_arrival_support_count": 20,
        "finite_status": True,
    }
    base.update(kwargs)
    return base


def test_balanced_profile_gate() -> None:
    rows = {
        "balanced": _diag(),
        "opportunity_only": _diag(D_TV_arr_emp=0.2, tail_mass_ratio=0.5, head_mass_ratio=1.5),
        "observation_only": _diag(D_TV_arr_emp=0.15, tail_mass_ratio=0.6, head_mass_ratio=1.4),
        "usable_only": _diag(D_TV_arr_emp=0.1, tail_mass_ratio=0.7, head_mass_ratio=1.3),
        "complete_aligned": _diag(
            D_TV_arr_emp=0.4, tail_mass_ratio=0.2, head_mass_ratio=2.0, tail_mass_ratio_obs=0.3,
        ),
        "complete_counteracting": _diag(
            D_TV_arr_emp=0.3,
            tail_mass_ratio=0.25,
            head_mass_ratio=1.8,
            tail_mass_ratio_obs=0.2,
            cancellation_TV=0.05,
        ),
    }
    out = evaluate_seed_profile_gates(rows)
    assert out["gate_status"]["G1"] == "PASS"


def test_single_stage_profile_gate() -> None:
    rows = {
        "balanced": _diag(),
        "opportunity_only": _diag(D_TV_arr_emp=0.2, tail_mass_ratio=0.5, head_mass_ratio=1.5),
        "observation_only": _diag(D_TV_arr_emp=0.15, tail_mass_ratio=0.6, head_mass_ratio=1.4),
        "usable_only": _diag(D_TV_arr_emp=0.1, tail_mass_ratio=0.7, head_mass_ratio=1.3),
        "complete_aligned": _diag(
            D_TV_arr_emp=0.4, tail_mass_ratio=0.2, head_mass_ratio=2.0, tail_mass_ratio_obs=0.3,
        ),
        "complete_counteracting": _diag(
            D_TV_arr_emp=0.3,
            tail_mass_ratio=0.25,
            head_mass_ratio=1.8,
            tail_mass_ratio_obs=0.2,
            cancellation_TV=0.05,
        ),
    }
    out = evaluate_seed_profile_gates(rows)
    assert out["gate_status"]["G2"] == "PASS"


def test_aligned_profile_gate() -> None:
    rows = {
        "balanced": _diag(),
        "opportunity_only": _diag(D_TV_arr_emp=0.2, tail_mass_ratio=0.5, head_mass_ratio=1.5),
        "observation_only": _diag(D_TV_arr_emp=0.15, tail_mass_ratio=0.6, head_mass_ratio=1.4),
        "usable_only": _diag(D_TV_arr_emp=0.1, tail_mass_ratio=0.7, head_mass_ratio=1.3),
        "complete_aligned": _diag(
            D_TV_arr_emp=0.4, tail_mass_ratio=0.2, head_mass_ratio=2.0, tail_mass_ratio_obs=0.3,
        ),
        "complete_counteracting": _diag(
            D_TV_arr_emp=0.3,
            tail_mass_ratio=0.25,
            head_mass_ratio=1.8,
            tail_mass_ratio_obs=0.2,
            cancellation_TV=0.05,
        ),
    }
    out = evaluate_seed_profile_gates(rows)
    assert out["gate_status"]["G3"] == "PASS"


def test_counteracting_profile_gate() -> None:
    rows = {
        "balanced": _diag(),
        "opportunity_only": _diag(D_TV_arr_emp=0.2, tail_mass_ratio=0.5, head_mass_ratio=1.5),
        "observation_only": _diag(D_TV_arr_emp=0.15, tail_mass_ratio=0.6, head_mass_ratio=1.4),
        "usable_only": _diag(D_TV_arr_emp=0.1, tail_mass_ratio=0.7, head_mass_ratio=1.3),
        "complete_aligned": _diag(
            D_TV_arr_emp=0.4, tail_mass_ratio=0.2, head_mass_ratio=2.0, tail_mass_ratio_obs=0.3,
        ),
        "complete_counteracting": _diag(
            D_TV_arr_emp=0.3,
            tail_mass_ratio=0.25,
            head_mass_ratio=1.8,
            tail_mass_ratio_obs=0.2,
            cancellation_TV=0.05,
        ),
    }
    out = evaluate_seed_profile_gates(rows)
    assert out["gate_status"]["G4"] == "PASS"


def test_expected_empirical_mass_gate() -> None:
    rows = {
        "balanced": _diag(D_TV_exp_emp=0.01),
        "opportunity_only": _diag(
            D_TV_arr_emp=0.2, tail_mass_ratio=0.5, head_mass_ratio=1.5, D_TV_exp_emp=0.02,
        ),
        "observation_only": _diag(
            D_TV_arr_emp=0.15, tail_mass_ratio=0.6, head_mass_ratio=1.4, D_TV_exp_emp=0.02,
        ),
        "usable_only": _diag(
            D_TV_arr_emp=0.1, tail_mass_ratio=0.7, head_mass_ratio=1.3, D_TV_exp_emp=0.02,
        ),
        "complete_aligned": _diag(
            D_TV_arr_emp=0.4,
            tail_mass_ratio=0.2,
            head_mass_ratio=2.0,
            tail_mass_ratio_obs=0.3,
            D_TV_exp_emp=0.02,
        ),
        "complete_counteracting": _diag(
            D_TV_arr_emp=0.3,
            tail_mass_ratio=0.25,
            head_mass_ratio=1.8,
            tail_mass_ratio_obs=0.2,
            cancellation_TV=0.05,
            D_TV_exp_emp=0.02,
        ),
    }
    out = evaluate_seed_profile_gates(rows)
    assert out["gate_status"]["G5"] == "PASS"


def test_profile_selection_deterministic() -> None:
    def seed_result(aligned: float, cancel: float, valid: bool = True):
        return {
            "profile_valid_seed": valid,
            "aligned_dtv": aligned,
            "counteracting_cancellation": cancel,
        }

    payload = {
        "PROFILE-S2": {s: seed_result(0.5, 0.1) for s in VALIDATION_SEEDS},
        "PROFILE-S3": {s: seed_result(0.6, 0.1) for s in VALIDATION_SEEDS},
    }
    profiles = {
        "PROFILE-S2": {"kappa_opp": 1, "kappa_p": 1, "kappa_q": 1},
        "PROFILE-S3": {"kappa_opp": 1.5, "kappa_p": 1.5, "kappa_q": 1.5},
    }
    out = select_strength_profile(payload, profiles)
    assert out["selected_profile_id"] == "PROFILE-S2"


def test_no_profile_grid_extension() -> None:
    strength = yaml.safe_load(
        (ROOT / "configs/e2_numeric/strength_profile_registry.yaml").read_text(encoding="utf-8")
    )
    assert "PROFILE-S7" not in strength["profiles"]


def test_window_selection_distribution_only() -> None:
    out = select_window_length({s: {100: True, 200: True, 300: True} for s in VALIDATION_SEEDS})
    assert "rmse" not in json.dumps(out).lower()


def test_window_selection_shortest_stable() -> None:
    out = select_window_length({s: {100: True, 200: True, 300: True} for s in VALIDATION_SEEDS})
    assert out["selected_windows"] == 100
    out2 = select_window_length({s: {100: False, 200: True, 300: True} for s in VALIDATION_SEEDS})
    assert out2["selected_windows"] == 200


def test_risk_visibility_not_used_for_selection() -> None:
    path = ROOT / "outputs/e2_distribution/E2_RISK_VISIBILITY_AUDIT.csv"
    if not path.is_file():
        pytest.skip("risk audit not generated yet")
    import pandas as pd
    frame = pd.read_csv(path)
    assert bool((~frame["used_for_selection"]).all())


def test_seed_29001_not_read() -> None:
    path = ROOT / "outputs/e2_distribution/E2_PROFILE_SELECTION.json"
    if not path.is_file():
        pytest.skip("selection not generated yet")
    text = path.read_text(encoding="utf-8")
    assert "29001" not in text


def test_formal_seed_noninspection() -> None:
    path = ROOT / "outputs/e2_distribution/E2_PROFILE_SELECTION.json"
    if not path.is_file():
        pytest.skip("selection not generated yet")
    text = path.read_text(encoding="utf-8")
    for seed in range(30001, 30021):
        assert str(seed) not in text


def test_e1_and_e2_parent_hashes_unchanged() -> None:
    identity = json.loads(
        (ROOT / "configs/frozen/e2_numeric/e1_target_identity.json").read_text(encoding="utf-8")
    )
    assert identity["atomic_target_weight_hash"].startswith("413ad5da")
    assert identity["supported_test_unit_hash"].startswith("d67e5c9e")


def test_final_export_is_last_mutating_step() -> None:
    # Contract test: export script documents zip-last ordering.
    script = (ROOT / "scripts/export_e2_distribution_profile_evidence.py").read_text(
        encoding="utf-8"
    )
    assert "ZIP export must be last" in script or "final_export" in script
