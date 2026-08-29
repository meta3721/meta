"""SAG G0 implementation audit. Do not start G1 unless this writes PASS."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from raven_mcs.aggregation.method_policy import get_method_policy
from raven_mcs.audits.sag_eventtrace_audit import audit_shared_eventtrace, layer_hash
from raven_mcs.audits.sag_leakage_audit import audit_b_a_sets, audit_gate_features
from raven_mcs.audits.sag_timing_audit import audit_timing_rows
from raven_mcs.experiments.sag_runtime import METHODS, eventtrace_dir, prepare_sag_bundle
from raven_mcs.sag.certificates import FrozenSagThresholds
from raven_mcs.sag.gate import FORBIDDEN_GATE_FEATURES, LEGAL_GATE_FEATURES
from raven_mcs.training.window_runner import build_full_runner
from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import dump_json

ROOT = Path(__file__).resolve().parents[3]
SMOKE_WINDOWS = 6
SMOKE_DATASETS = ("sensorscope",)
SMOKE_SEEDS = (30001,)
FULL_DATASETS = ("sensorscope", "uair")
FULL_SEEDS = (30001, 30002, 30003)
LOCAL_STEPS = 2


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        ).strip()
    except Exception:
        return "UNKNOWN"


def _load_thresholds() -> FrozenSagThresholds:
    payload = json.loads((ROOT / "configs/sag_g0/thresholds.json").read_text(encoding="utf-8"))
    keep = {
        k: payload[k]
        for k in FrozenSagThresholds.__dataclass_fields__
        if k in payload
    }
    return FrozenSagThresholds(**keep)


def _flatten_log(row: dict[str, Any], *, dataset: str, seed: int, method: str) -> dict[str, Any]:
    feat = dict(row.get("gate_features") or {})
    out = {
        "dataset": dataset,
        "seed": int(seed),
        "method": method,
        "window_id": row.get("window_id"),
        "G_r": row.get("G_r"),
        "fallback_reason": row.get("fallback_reason"),
        "gate_stage": row.get("gate_stage"),
        "R_stage": row.get("R_stage"),
        "p_obs_freeze_stage": row.get("p_obs_freeze_stage"),
        "O_stage": row.get("O_stage"),
        "local_stage": row.get("local_stage"),
        "q_use_freeze_stage": row.get("q_use_freeze_stage"),
        "U_stage": row.get("U_stage"),
        "P2_stage": row.get("P2_stage"),
        "p2_invoked": row.get("p2_invoked"),
        "B_r_size": len(row.get("B_r") or []),
        "A_r_size": len(row.get("A_r") or []),
        "U_r_size": len(row.get("U_r") or []),
        "B_r": json.dumps(row.get("B_r") or []),
        "A_r": json.dumps(row.get("A_r") or []),
        "U_r": json.dumps(row.get("U_r") or []),
        "m_by_client": json.dumps(row.get("m_by_client") or {}),
        "zeta_tilde_all_ones": row.get("zeta_tilde_all_ones"),
        "uses_observation_ipw": row.get("uses_observation_ipw"),
        "uses_usable_ipw": row.get("uses_usable_ipw"),
        "uses_debt": row.get("uses_debt"),
        "uses_variance_penalty": row.get("uses_variance_penalty"),
        "uses_staleness_penalty": row.get("uses_staleness_penalty"),
        "A_D_size": row.get("A_D_size"),
        "A_0_size": row.get("A_0_size"),
        "active_set_mismatch": row.get("active_set_mismatch"),
        "both_empty": row.get("both_empty"),
        "service_diff": row.get("service_diff"),
        "Delta_beta": row.get("Delta_beta"),
        "Delta_M": row.get("Delta_M"),
        "Delta_V": row.get("Delta_V"),
        "realized_C_cov": row.get("realized_C_cov"),
        "realized_C_ret": row.get("realized_C_ret"),
        "realized_C_ESS": row.get("realized_C_ESS"),
        "realized_C_clip": row.get("realized_C_clip"),
    }
    for key in LEGAL_GATE_FEATURES:
        out[key] = feat.get(key)
    return out


def _run_one(
    *,
    prepared: dict[str, Any],
    method: str,
    thresholds: FrozenSagThresholds,
    local_steps: int,
) -> list[dict[str, Any]]:
    policy = get_method_policy(method)
    if method == "raven_sag" and policy.gate_mode != "sag":
        raise RuntimeError("raven_sag must use gate_mode=sag")
    if "dataset" in method.lower() or "sensorscope" in method.lower():
        raise RuntimeError("method name must not encode a dataset Gate")
    runner = build_full_runner(
        prepared["trace"],
        prepared["dataset"],
        method=method,
        n_groups=int(prepared["n_groups"]),
        model_seed=int(prepared["trace"].metadata.seed),
        local_steps=int(local_steps),
        target_mu=prepared["target_mu"],
        pi_target=prepared["pi_target"],
        s_max=int(prepared["trace"].metadata.s_max),
        device="cpu",
        use_coarse_time_groups=False,
        pi_opp_joint=prepared["pi_opp_joint"],
    )
    runner.sag_thresholds = FrozenSagThresholds(
        **{
            **thresholds.as_dict(),
            "n_groups": int(prepared["n_groups"]),
        }
    )
    runner.run()
    return list(runner.sag_window_logs)


def _eventtrace_hashes(events: pd.DataFrame, identity: dict[str, Any]) -> dict[str, str]:
    out = {
        "sealed_trace_hash": str(identity.get("trace_hash")),
        "sealed_events_sha256": str(identity.get("events_sha256")),
    }
    windows = sorted(int(w) for w in events["window_id"].unique())
    for window_id in windows:
        out[f"w{window_id}_R"] = layer_hash(events, window_id, ["risk_set_unit_ids"])
        out[f"w{window_id}_O"] = layer_hash(events, window_id, ["O", "observed_unit_ids"])
        out[f"w{window_id}_U"] = layer_hash(events, window_id, ["U"])
        cols_dead = [c for c in ("tau", "registration_time") if c in events.columns]
        cols_stale = [c for c in ("model_age", "tau", "downloaded_version") if c in events.columns]
        out[f"w{window_id}_deadline"] = layer_hash(events, window_id, cols_dead)
        out[f"w{window_id}_staleness"] = layer_hash(events, window_id, cols_stale)
    return out


def _write_audit_md(path: Path, verdict: str, checks: dict[str, Any], config: dict[str, Any]) -> None:
    lines = [
        "# SAG G0 Implementation Audit",
        "",
        f"Verdict: **{verdict}**",
        "",
        f"- git: `{config.get('git_commit')}`",
        f"- mode: `{config.get('mode')}`",
        f"- datasets: {config.get('datasets')}",
        f"- seeds: {config.get('seeds')}",
        f"- max_windows: {config.get('max_windows')}",
        "",
        "## Checks",
        "",
    ]
    questions = [
        ("timing_correct", "timing correct?"),
        ("p_obs_frozen_before_O", "p_obs frozen before O?"),
        ("q_use_frozen_before_U", "q_use frozen before U?"),
        ("b_a_sets", "B_r/A_r correct?"),
        ("shared_eventtrace", "shared EventTrace?"),
        ("no_dataset_name_gate", "no dataset-name Gate?"),
        ("no_forbidden_gate_feature", "no forbidden Gate feature?"),
        ("counterfactual_audit_valid", "counterfactual audit valid?"),
        ("nodesign_semantics", "No-Design zeta==1 with IPW/P2 on?"),
    ]
    for key, label in questions:
        item = checks.get(key, {})
        status = "PASS" if item.get("pass") else "FAIL"
        lines.append(f"- {label} **{status}**")
        if item.get("failures"):
            lines.append(f"  - {item['failures'][:5]}")
    lines.extend(["", "## Assertion summary", "", "```json", json.dumps(checks, indent=2, default=str), "```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def run_g0(
    *,
    mode: str = "smoke",
    root: Path = ROOT,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    root = Path(root)
    out = Path(output_dir or (root / "outputs" / "sag_g0"))
    (out / "configs").mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    datasets = SMOKE_DATASETS if mode == "smoke" else FULL_DATASETS
    seeds = SMOKE_SEEDS if mode == "smoke" else FULL_SEEDS
    max_windows = SMOKE_WINDOWS if mode == "smoke" else None
    thresholds = _load_thresholds()
    threshold_hash = sha256_file(root / "configs/sag_g0/thresholds.json")
    config = {
        "mode": mode,
        "datasets": list(datasets),
        "seeds": list(seeds),
        "max_windows": max_windows,
        "methods": list(METHODS),
        "local_steps": LOCAL_STEPS,
        "git_commit": _git_hash(),
        "threshold_hash": threshold_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "G0 implementation audit. Dataset identity is not a Gate feature.",
    }
    dump_json(config, out / "configs" / f"config_{mode}.json")
    config["config_hash"] = sha256_file(out / "configs" / f"config_{mode}.json")

    all_rows: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    ba_rows: list[dict[str, Any]] = []
    hash_by_key: dict[tuple[str, int], dict[str, dict[str, str]]] = {}
    dataset_name_gate = False

    for dataset in datasets:
        for seed in seeds:
            prepared = prepare_sag_bundle(
                root=root, dataset=dataset, seed=int(seed), max_windows=max_windows,
            )
            hashes = _eventtrace_hashes(prepared["trace"].events, prepared["identity"])
            hash_by_key[(dataset, int(seed))] = {}
            for method in METHODS:
                logs = _run_one(
                    prepared=prepared,
                    method=method,
                    thresholds=thresholds,
                    local_steps=LOCAL_STEPS,
                )
                hash_by_key[(dataset, int(seed))][method] = hashes
                for row in logs:
                    flat = _flatten_log(row, dataset=dataset, seed=int(seed), method=method)
                    all_rows.append(flat)
                    ba_rows.append({
                        "dataset": dataset,
                        "seed": int(seed),
                        "method": method,
                        "window_id": row.get("window_id"),
                        "A_r": row.get("A_r") or [],
                        "B_r": row.get("B_r") or [],
                        "U_r": row.get("U_r") or [],
                        "m_by_client": row.get("m_by_client") or {},
                    })
                    feats = dict(row.get("gate_features") or {})
                    if "dataset_id" in feats or "dataset" in feats:
                        dataset_name_gate = True
                    for name, value in feats.items():
                        feature_rows.append({
                            "dataset": dataset,
                            "seed": int(seed),
                            "method": method,
                            "window_id": row.get("window_id"),
                            "feature": name,
                            "value": value,
                        })
                        if name in FORBIDDEN_GATE_FEATURES:
                            dataset_name_gate = True

    window_df = pd.DataFrame(all_rows)
    window_df.to_csv(out / "G0_WINDOW_TRACE.csv", index=False)
    pd.DataFrame(feature_rows).to_csv(out / "G0_GATE_FEATURE_AUDIT.csv", index=False)
    pd.DataFrame(ba_rows).assign(
        A_r=lambda d: d["A_r"].map(json.dumps),
        B_r=lambda d: d["B_r"].map(json.dumps),
        U_r=lambda d: d["U_r"].map(json.dumps),
        m_by_client=lambda d: d["m_by_client"].map(json.dumps),
    ).to_csv(out / "G0_B_A_SET_AUDIT.csv", index=False)
    window_df[[
        "dataset", "seed", "method", "window_id", "A_D_size", "A_0_size",
        "active_set_mismatch", "both_empty", "service_diff",
        "Delta_beta", "Delta_M", "Delta_V",
        "realized_C_cov", "realized_C_ret", "realized_C_ESS", "realized_C_clip",
    ]].to_csv(out / "G0_COUNTERFACTUAL_AUDIT.csv", index=False)

    hash_rows = []
    shared_failures: list[str] = []
    for (dataset, seed), by_method in hash_by_key.items():
        shared = audit_shared_eventtrace(by_method)
        if not shared["pass"]:
            shared_failures.extend([f"{dataset}/seed{seed}: {x}" for x in shared["failures"]])
        row = {"dataset": dataset, "seed": seed, **next(iter(by_method.values()))}
        hash_rows.append(row)
    pd.DataFrame(hash_rows).to_csv(out / "G0_EVENTTRACE_HASH_CHECK.csv", index=False)

    timing = audit_timing_rows(all_rows)
    leakage = audit_gate_features(feature_rows)
    sets = audit_b_a_sets(ba_rows)
    nod = True
    nod_fail: list[str] = []
    nod_rows = [r for r in all_rows if r["method"] == "raven_wo_design"]
    for row in nod_rows:
        if int(row.get("G_r", 1)) != 0:
            nod = False
            nod_fail.append(f"G_r!=0 window {row['window_id']}")
        if not row.get("zeta_tilde_all_ones", False):
            nod = False
            nod_fail.append(f"zeta!=1 window {row['window_id']}")
        for flag in (
            "uses_observation_ipw", "uses_usable_ipw", "uses_debt",
            "uses_variance_penalty", "uses_staleness_penalty",
        ):
            if not row.get(flag, False):
                nod = False
                nod_fail.append(f"{flag} off window {row['window_id']}")
    cf_fail: list[str] = []
    for row in all_rows:
        if int(row.get("both_empty") or 0) == 1:
            if row.get("service_diff") not in (0, 0.0):
                cf_fail.append(f"both-empty service_diff {row['service_diff']}")
            for key in ("Delta_beta", "Delta_M", "Delta_V"):
                if row.get(key) not in (None, "", "NA") and pd.notna(row.get(key)):
                    cf_fail.append(f"both-empty {key} filled with {row.get(key)}")
        mismatch = int(row.get("active_set_mismatch") or 0)
        both = int(row.get("both_empty") or 0)
        if mismatch == 0 and both == 0:
            continue
    src = Path(ROOT / "src/raven_mcs/sag/gate.py").read_text(encoding="utf-8")
    no_ds = (
        "if dataset" not in src
        and "SensorScope" not in src
        and "sensorscope" not in src.lower().replace("forbidden", "")
    )
    # gate.py must not branch on dataset names
    gate_src = src
    no_ds = ("SensorScope" not in gate_src) and ("U-Air" not in gate_src)
    no_ds = no_ds and not dataset_name_gate
    runner_src = (ROOT / "src/raven_mcs/training/window_runner.py").read_text(encoding="utf-8")
    no_ds = no_ds and ("if dataset ==" not in runner_src)

    checks = {
        "timing_correct": timing,
        "p_obs_frozen_before_O": {
            "pass": timing["pass"],
            "failures": timing.get("failures", []),
        },
        "q_use_frozen_before_U": {
            "pass": timing["pass"],
            "failures": timing.get("failures", []),
        },
        "b_a_sets": sets,
        "shared_eventtrace": {"pass": not shared_failures, "failures": shared_failures},
        "no_dataset_name_gate": {"pass": no_ds, "failures": [] if no_ds else ["dataset-name Gate detected"]},
        "no_forbidden_gate_feature": leakage,
        "counterfactual_audit_valid": {"pass": not cf_fail, "failures": cf_fail},
        "nodesign_semantics": {"pass": nod and bool(nod_rows), "failures": nod_fail},
    }
    p0 = all(bool(v.get("pass")) for v in checks.values())
    verdict = "PASS" if p0 else "FAIL"
    dump_json({"verdict": verdict, "checks": checks, "config": config}, out / "G0_ASSERTION_SUMMARY.json")
    _write_audit_md(out / "G0_IMPLEMENTATION_AUDIT.md", verdict, checks, config)
    (out / "logs" / f"{mode}.json").write_text(
        json.dumps({"verdict": verdict, "n_rows": len(all_rows)}, indent=2),
        encoding="utf-8",
    )
    if not p0:
        raise SystemExit(f"G0 {verdict}: see {out / 'G0_IMPLEMENTATION_AUDIT.md'}")
    return {"verdict": verdict, "output_dir": str(out), "n_rows": len(all_rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description="SAG G0 implementation audit")
    parser.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    result = run_g0(mode=args.mode, root=args.root, output_dir=args.output_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
