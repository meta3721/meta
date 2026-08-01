#!/usr/bin/env python3
"""Evidence-based P10-R1 gates R1-G1 through R1-G8."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
AUDITS = ROOT / "outputs" / "audits"
REQUIRED = (
    "manifest.json", "resolved_config.yaml", "event_trace_ref.json",
    "metrics_window.parquet", "metrics_run.json", "predictions_test.parquet",
    "arrival_weights_test.parquet", "propensity_diagnostics.parquet",
    "solver_diagnostics.parquet", "system_metrics.json", "smoke_checks.json",
    "checkpoints", "stdout.log", "stderr.log",
)
MANIFEST_HASH_FIELDS = (
    "config_hash", "data_hash", "event_trace_hash", "target_group_hash",
    "environment_hash",
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _config_hash(path: Path) -> str:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _same_predictions(left: Path, right: Path) -> bool:
    keys = ["method", "unit_id"]
    a = pd.read_parquet(left / "predictions_test.parquet").sort_values(keys)
    b = pd.read_parquet(right / "predictions_test.parquet").sort_values(keys)
    return (
        a[keys].reset_index(drop=True).equals(b[keys].reset_index(drop=True))
        and np.allclose(a["y_pred"], b["y_pred"], rtol=0.0, atol=1e-10)
    )


def _same_metrics(left: Path, right: Path) -> bool:
    a = _json(left / "metrics_run.json")["methods"]
    b = _json(right / "metrics_run.json")["methods"]
    fields = ("RMSE_mu", "RMSE_rho", "Gap_mis", "target_arrival_l1_gap")
    return set(a) == set(b) and all(
        np.allclose(
            [a[method][field] for field in fields],
            [b[method][field] for field in fields],
            rtol=0.0,
            atol=1e-12,
        )
        for method in a
    )


def _find_comparison(run_dir: Path, manifest: dict) -> Path | None:
    candidates: list[Path] = []
    for path in run_dir.parent.iterdir():
        if path == run_dir or not (path / "manifest.json").exists():
            continue
        other = _json(path / "manifest.json")
        if (
            other.get("seed") == manifest.get("seed")
            and other.get("config_hash") == manifest.get("config_hash")
            and other.get("event_trace_hash") == manifest.get("event_trace_hash")
            and (path / "predictions_test.parquet").exists()
        ):
            candidates.append(path)
    return sorted(candidates)[-1] if candidates else None


def check(run_dir: Path, comparison: Path | None = None) -> dict[str, tuple[bool, str]]:
    manifest = _json(run_dir / "manifest.json")
    metrics = _json(run_dir / "metrics_run.json")
    predictions = pd.read_parquet(run_dir / "predictions_test.parquet")
    weights = pd.read_parquet(run_dir / "arrival_weights_test.parquet")

    window = _json(AUDITS / "p10_r1_window_audit.json")
    g1 = (
        not window.get("uses_modulo", True)
        and all(window.get(name) == 0 for name in (
            "overlap_count", "out_of_order_count", "future_leakage_count",
            "tau_consistency_violations", "duplicate_unit_assignments",
            "unassigned_unit_count",
        ))
    )

    per_method_weight = weights.groupby("method")["arrival_weight"].sum()
    per_method_l1 = weights.groupby("method").apply(
        lambda frame: float(np.abs(frame["arrival_weight"] - frame["target_weight"]).sum()),
        include_groups=False,
    )
    g2 = (
        np.isfinite(weights["arrival_intensity"]).all()
        and (weights["arrival_intensity"] >= 0).all()
        and (weights["arrival_weight"] >= 0).all()
        and all(abs(value - 1.0) <= 1e-12 for value in per_method_weight)
        and all(value > 1e-6 for value in per_method_l1)
        and bool(weights["arrival_weight"].nunique() > 1)
    )

    recomputed: dict[str, tuple[float, float]] = {}
    for method, frame in predictions.groupby("method"):
        error2 = (frame["y_pred"].to_numpy() - frame["y_true"].to_numpy()) ** 2
        recomputed[method] = (
            float(np.sqrt(np.sum(frame["target_weight"] * error2))),
            float(np.sqrt(np.sum(frame["arrival_weight"] * error2))),
        )
    g3 = all(
        abs(value["Gap_mis"] - (value["RMSE_mu"] - value["RMSE_rho"])) <= 1e-12
        and np.allclose(
            [value["RMSE_mu"], value["RMSE_rho"]],
            recomputed[method],
            rtol=0.0,
            atol=1e-12,
        )
        for method, value in metrics["methods"].items()
    )

    q_scan = pd.read_csv(AUDITS / "p10_r1_q_feature_scan.csv")
    q_columns = {
        "file", "line", "variable", "match_pattern", "classification",
        "action", "reviewer_note",
    }
    g4 = q_columns.issubset(q_scan.columns) and not q_scan[
        "classification"
    ].astype(str).str.startswith("UNREVIEWED").any()

    diagnostic = pd.read_parquet(
        AUDITS / "p10_r1_fedavg_twostage_diagnostic.parquet",
    )
    g5 = (
        not diagnostic.empty
        and (diagnostic["l1_local_weight_diff"] > 1e-10).any()
        and (diagnostic["l1_beta_vs_fedavg_diff"] > 1e-10).any()
        and (~diagnostic["model_hash_equal"]).any()
        and (diagnostic["prediction_max_abs_diff"] > 1e-10).all()
    )

    groups = yaml.safe_load(
        (ROOT / "configs" / "frozen" / "e1_sensorscope_groups.yaml")
        .read_text(encoding="utf-8")
    )
    reach = _json(AUDITS / "p10_r1_group_reachability.json")
    reach_hash = hashlib.sha256(
        (AUDITS / "p10_r1_group_reachability.json").read_bytes()
    ).hexdigest()
    g6 = (
        groups.get("group_count") in {4, 8}
        and groups.get("validation_audit_hash") == reach_hash
        and reach.get("unsupported_positive_target_groups") == 0
        and np.isfinite(reach.get("epsilon_reach", np.nan))
        and reach.get("epsilon_reach_feasible") is True
        and not reach.get("fine_grained_groups_used_for_main_debt", True)
    )

    missing = [name for name in REQUIRED if not (run_dir / name).exists()]
    trace_ref = _json(run_dir / "event_trace_ref.json")
    checkpoints = list((run_dir / "checkpoints").glob("*.pt")) if not missing else []
    hash_fields = all(isinstance(manifest.get(name), str) and len(manifest[name]) == 64
                      for name in MANIFEST_HASH_FIELDS)
    g7 = (
        not missing
        and hash_fields
        and _config_hash(run_dir / "resolved_config.yaml") == manifest["config_hash"]
        and trace_ref.get("event_trace_hash") == manifest["event_trace_hash"]
        and hashlib.sha256(
            (ROOT / "configs" / "frozen" / "e1_sensorscope_groups.yaml").read_bytes()
        ).hexdigest() == manifest["target_group_hash"]
        and len(checkpoints) == 3
        and not pd.read_parquet(run_dir / "metrics_window.parquet").empty
        and "raven" in set(pd.read_parquet(run_dir / "solver_diagnostics.parquet")["method"])
    )

    comparison = comparison or _find_comparison(run_dir, manifest)
    g8 = bool(
        comparison
        and _json(comparison / "manifest.json").get("event_trace_hash")
        == manifest.get("event_trace_hash")
        and _json(comparison / "manifest.json").get("config_hash")
        == manifest.get("config_hash")
        and _same_predictions(run_dir, comparison)
        and _same_metrics(run_dir, comparison)
    )

    return {
        "R1-G1": (g1, "chronology, assignment, and tau evidence"),
        "R1-G2": (g2, "atomic arrival weights and non-uniformity"),
        "R1-G3": (g3, "metrics recomputed from prediction rows"),
        "R1-G4": (g4, "runtime q feature audit"),
        "R1-G5": (g5, "FedAvg/TwoStage controlled path differences"),
        "R1-G6": (g6, "frozen reachable main groups"),
        "R1-G7": (g7, f"artifact and hash consistency; missing={missing}"),
        "R1-G8": (g8, f"comparison={comparison}"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--compare-run", type=Path)
    args = parser.parse_args()
    result = check(args.run_dir.resolve(), args.compare_run)
    for gate, (passed, detail) in result.items():
        print(f"{gate}={'PASS' if passed else 'FAIL'} {detail}")
    manifest_path = args.run_dir / "manifest.json"
    manifest = _json(manifest_path)
    manifest["hard_gate_status"]["r1_gates"] = {
        gate: "PASS" if passed else "FAIL"
        for gate, (passed, _) in result.items()
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return 0 if all(passed for passed, _ in result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
