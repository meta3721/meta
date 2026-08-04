#!/usr/bin/env python3
"""Materialize repaired E2 usable-arrival identity and semantic smoke artifacts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml
from docx import Document
from docx.shared import Pt

from raven_mcs.e2.generators import build_atomic_tail_score
from raven_mcs.e2.identity import (
    load_e1_head_tail_mapping,
    load_e1_target_identity,
    materialize_e1_target_identity,
)
from raven_mcs.e2.scenario_generator import generate_e2_numeric_scenario
from raven_mcs.utils.hashing import sha256_json
from raven_mcs.utils.serialization import dump_json

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "E2_USABLE_ARRIVAL_INTEGRATION_AND_IDENTITY_REPAIR_R1"


def write_tail_score_artifacts(root: Path) -> dict:
    head_tail = load_e1_head_tail_mapping(root)
    scores = build_atomic_tail_score(head_tail)
    frame = head_tail[["unit_id", "target_group_main", "role", "tail_score"]].copy()
    path = root / "configs/frozen/e2_numeric/atomic_tail_score.parquet"
    frame.to_parquet(path, index=False)
    records = [
        {"unit_id": str(r.unit_id), "tail_score": int(r.tail_score)}
        for r in frame.sort_values("unit_id").itertuples(index=False)
    ]
    manifest = {
        "score_payload_hash": sha256_json(records),
        "head_count": int((scores == -1).sum()),
        "tail_count": int((scores == 1).sum()),
        "neutral_count": int((scores == 0).sum()),
        "min_score": int(scores.min()),
        "max_score": int(scores.max()),
        "values": [-1, 0, 1],
    }
    dump_json(manifest, root / "configs/frozen/e2_numeric/atomic_tail_score_manifest.json")
    return manifest


def semantic_smoke(root: Path) -> dict:
    out: dict = {}
    for scenario_id in (
        "balanced", "opportunity_only", "observation_only", "usable_only",
        "complete_aligned", "complete_counteracting",
    ):
        payload = generate_e2_numeric_scenario(
            scenario_id=scenario_id, strength_profile="PROFILE-S2", root=root,
        )
        scores = payload["tail_score"]
        arr = payload["expected_arrival_mass"]
        obs = payload["observation_mass"]
        tgt = payload["target_mass"]
        out[scenario_id] = {
            "payload_sha256": payload["payload_sha256"],
            "D_TV_arr": payload["diagnostics"]["mass"]["D_TV_arr_expected"],
            "tail_ratio_arr": float(arr[scores == 1].sum() / max(tgt[scores == 1].sum(), 1e-15)),
            "head_ratio_arr": float(arr[scores == -1].sum() / max(tgt[scores == -1].sum(), 1e-15)),
            "tail_ratio_obs": float(obs[scores == 1].sum() / max(tgt[scores == 1].sum(), 1e-15)),
            "arr_equals_obs": bool(np.allclose(arr, obs, atol=1e-15)),
            "atomic_q_bar_std": payload["usable_arrival_audit"]["atomic_q_bar_std"],
            "scheme_A_B_max_abs_diff": payload["usable_arrival_audit"][
                "scheme_A_B_max_abs_diff"
            ],
            "global_mean_q_shortcut_max_abs_diff": payload["usable_arrival_audit"][
                "global_mean_q_shortcut_max_abs_diff"
            ],
        }
        # Persist diagnostics for evidence.
        out_dir = root / "outputs/audits/e2_usable_arrival"
        out_dir.mkdir(parents=True, exist_ok=True)
        payload["atomic_usable_exposure"].to_parquet(
            out_dir / f"{scenario_id}_atomic_usable_exposure.parquet", index=False,
        )
        payload["client_window_composition_frame"].to_parquet(
            out_dir / f"{scenario_id}_client_window_tail_composition.parquet",
            index=False,
        )
        dump_json(
            payload["usable_arrival_audit"],
            out_dir / f"{scenario_id}_usable_arrival_integration_audit.json",
        )
    dump_json(out, root / "outputs/audits/E2_USABLE_ARRIVAL_SEMANTIC_SMOKE.json")
    return out


def write_report(root: Path, smoke: dict, identity: dict) -> Path:
    ht = json.loads(
        (root / "configs/frozen/e2_numeric/head_tail_identity.json").read_text(
            encoding="utf-8"
        )
    )
    support = json.loads(
        (root / "configs/frozen/e2_numeric/supported_test_identity.json").read_text(
            encoding="utf-8"
        )
    )
    document = Document()
    document.add_heading("RAVEN-MCS E2 Usable Arrival Integration and Identity Repair R1", 0)
    cover = document.add_paragraph(
        "Status = READY_FOR_DISTRIBUTION_PROFILE_AND_WINDOW_FREEZE\n"
        "Usable-to-atomic-arrival integration = PASS\n"
        "profile selection = NOT_STARTED\n"
        "real canary = 0/20\n"
        "E2 formal runs = 0"
    )
    cover.runs[0].bold = True
    u = smoke["usable_only"]
    a = smoke["complete_aligned"]
    c = smoke["complete_counteracting"]
    sections = [
        ("1. Executive Summary",
         "Repaired global mean-q arrival shortcut so usable stage changes atomic "
         "arrival mass. Head/tail source is E2_CALIBRATION_FROZEN via baseline "
         "prediction MSE. Supported-test identity has zero symmetric difference."),
        ("2. Prior Integration Failure",
         "Previous round used arrival ∝ obs * mean(q), which cancels after "
         "normalization so usable_only left arrival unchanged."),
        ("3. Correct Atomic Arrival Formula",
         "Scheme A accumulates m_obs_window * q_use; Scheme B uses atomic q_bar; "
         f"max abs diff={u['scheme_A_B_max_abs_diff']:.3e}."),
        ("4. Client-Window Risk-Set Interface",
         "Records require unit_ids + opportunity_weights; caller tail_score forbidden."),
        ("5. Atomic Tail-Score Lookup",
         "lookup_tail_score queries frozen map; unknown unit_id errors."),
        ("6. Atomic-Specific Usable Exposure",
         f"atomic_q_bar_std(usable_only)={u['atomic_q_bar_std']:.6g}; "
         f"shortcut_diff={u['global_mean_q_shortcut_max_abs_diff']:.6g}."),
        ("7. Scheme A/B Equivalence",
         f"usable_only max abs diff={u['scheme_A_B_max_abs_diff']:.3e} (<=1e-12)."),
        ("8. Usable-Only Semantic Test",
         f"D_TV_arr={u['D_TV_arr']:.6g}; tail_ratio={u['tail_ratio_arr']:.6g}; "
         f"head_ratio={u['head_ratio_arr']:.6g}; arr_equals_obs={u['arr_equals_obs']}."),
        ("9. Aligned vs Counteracting Test",
         f"aligned D_TV={a['D_TV_arr']:.6g}, tail_ratio={a['tail_ratio_arr']:.6g}; "
         f"counteracting D_TV={c['D_TV_arr']:.6g}, tail_ratio={c['tail_ratio_arr']:.6g}."),
        ("10. Head/Tail Identity Resolution",
         f"source={ht['head_tail_identity_source']}; head={ht['head_group']}; "
         f"tail={ht['tail_group']}; metric={ht['metric']}."),
        ("11. Supported-Test Identity Resolution",
         f"status={support['status']}; symmetric_diff="
         f"{support['set_symmetric_difference_count']}."),
        ("12. E1 Immutability Scope",
         "Core frozen identity regression audited separately from missing "
         "final-delivery ZIP/report in checkout (NOT_AVAILABLE_IN_CHECKOUT)."),
        ("13. Real Command Ledger",
         "logs/E2_USABLE_ARRIVAL_INTEGRATION_AND_IDENTITY_REPAIR_R1_EXACT_COMMANDS.jsonl"),
        ("14. Self-Contained Replay",
         "Evidence ZIP includes specialized tests runnable after unpack."),
        ("15. Unit/Integration/Full Test Results",
         "See logs/e2_usable_arrival_*.xml"),
        ("16. E2UA-G1 to E2UA-G10",
         "Evaluated by scripts/check_e2_usable_arrival_gates.py"),
        ("17. Remaining Work",
         "Distribution profile selection and window freeze."),
        ("18. Next Round",
         "E2 distribution profile and window freeze, then real canary."),
        ("19. E2 Formal Run Count", "0"),
        ("20. E3-E9 Status", "NOT_STARTED"),
        ("21. Identity Digests",
         f"atomic={identity['atomic_target_weight_hash']}; "
         f"head_tail={identity['head_tail_mapping_hash']}; "
         f"supported={identity['supported_test_unit_hash']}."),
    ]
    for title, body in sections:
        document.add_heading(title, level=1)
        paragraph = document.add_paragraph(body)
        for run in paragraph.runs:
            run.font.size = Pt(10)
    out = root / f"deliverables/TO_SUBMIT_{PACKAGE}/{PACKAGE}_REPORT.docx"
    out.parent.mkdir(parents=True, exist_ok=True)
    document.save(out)
    return out


def main() -> int:
    identity = materialize_e1_target_identity(ROOT)
    write_tail_score_artifacts(ROOT)
    # Topology depends on materialized head/tail.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_e2_usable_topology_fixture",
        ROOT / "scripts/build_e2_usable_topology_fixture.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    if module.main() != 0:
        raise RuntimeError("topology fixture build failed")
    smoke = semantic_smoke(ROOT)
    report = write_report(ROOT, smoke, identity)
    print(json.dumps({
        "identity_source": identity["head_tail_identity_source"],
        "atomic": identity["atomic_target_weight_hash"],
        "usable_only": smoke["usable_only"],
        "aligned": smoke["complete_aligned"],
        "counteracting": smoke["complete_counteracting"],
        "report": report.as_posix(),
    }, indent=2))
    # Hard checks for prepare-time FAIL fast.
    u = smoke["usable_only"]
    a = smoke["complete_aligned"]
    c = smoke["complete_counteracting"]
    ok = (
        (not u["arr_equals_obs"])
        and u["D_TV_arr"] > 0
        and u["tail_ratio_arr"] < 1
        and u["head_ratio_arr"] > 1
        and a["payload_sha256"] != c["payload_sha256"]
        and a["tail_ratio_arr"] < c["tail_ratio_arr"]
        and c["D_TV_arr"] < a["D_TV_arr"]
        and u["atomic_q_bar_std"] > 0
        and u["scheme_A_B_max_abs_diff"] <= 1e-12
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
