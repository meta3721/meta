"""SAG G1 5-seed diagnostic. Requires G0 full PASS. Does not auto-expand to 10 seeds."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from raven_mcs.e3.delta_cs_rho.delta_cs_v6 import accumulate_delta_cs_v6
from raven_mcs.e3.real_runner.runner import _mu_weights_for_test, _predict
from raven_mcs.experiments.run_sag_g0 import _flatten_log, _load_thresholds
from raven_mcs.experiments.sag_runtime import METHODS, prepare_sag_bundle
from raven_mcs.metrics.accuracy import mae_mu, rmse_mu
from raven_mcs.metrics.distribution import delta_group
from raven_mcs.sag.certificates import FrozenSagThresholds
from raven_mcs.utils.hashing import sha256_file
from raven_mcs.utils.serialization import dump_json

ROOT = Path(__file__).resolve().parents[3]
G1_DATASETS = ("sensorscope", "uair")
G1_SEEDS = (30001, 30002, 30003, 30004, 30005)
LOCAL_STEPS = 2
EPS_PRED = 0.005


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        ).strip()
    except Exception:
        return "UNKNOWN"


def _require_g0_full_pass(root: Path) -> dict[str, Any]:
    summary = Path(root) / "outputs" / "sag_g0" / "G0_ASSERTION_SUMMARY.json"
    if not summary.is_file():
        raise SystemExit("G1 blocked: G0_ASSERTION_SUMMARY.json missing.")
    payload = json.loads(summary.read_text(encoding="utf-8"))
    if payload.get("verdict") != "PASS":
        raise SystemExit(f"G1 blocked: G0 verdict={payload.get('verdict')}")
    if payload.get("config", {}).get("mode") != "full":
        raise SystemExit("G1 blocked: G0 full PASS required (smoke-only is not enough).")
    return payload


def _worst_group_rmse(pred: dict[str, Any], mu_w: np.ndarray) -> float:
    groups = np.asarray(pred["groups"])
    y_true = np.asarray(pred["y_true"], dtype=np.float64)
    y_pred = np.asarray(pred["y_pred"], dtype=np.float64)
    vals: list[float] = []
    for g in np.unique(groups):
        mask = groups == g
        ww = mu_w[mask].copy()
        if ww.size == 0 or float(ww.sum()) <= 0:
            continue
        ww = ww / float(ww.sum())
        vals.append(float(np.sqrt(np.sum(ww * (y_true[mask] - y_pred[mask]) ** 2))))
    return float(np.max(vals)) if vals else float("nan")


def _cover(actual: Any, bound: Any) -> float | None:
    if actual is None or bound is None:
        return None
    try:
        a = float(actual)
        b = float(bound)
    except (TypeError, ValueError):
        return None
    if not (np.isfinite(a) and np.isfinite(b)):
        return None
    return float(a <= b)


def _run_one_with_runner(
    *,
    prepared: dict[str, Any],
    method: str,
    thresholds: FrozenSagThresholds,
    local_steps: int,
):
    from raven_mcs.aggregation.method_policy import get_method_policy
    from raven_mcs.training.window_runner import build_full_runner

    policy = get_method_policy(method)
    if method == "raven_sag" and policy.gate_mode != "sag":
        raise RuntimeError("raven_sag must use gate_mode=sag")
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
        **{**thresholds.as_dict(), "n_groups": int(prepared["n_groups"])}
    )
    window_metrics = runner.run()
    return runner, list(runner.sag_window_logs), window_metrics


def run_g1_main(*, root: Path = ROOT, output_dir: Path | None = None) -> dict[str, Any]:
    root = Path(root)
    g0 = _require_g0_full_pass(root)
    out = Path(output_dir or (root / "outputs" / "sag_g1"))
    (out / "configs").mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    thresholds = _load_thresholds()
    config = {
        "mode": "g1_5seed",
        "datasets": list(G1_DATASETS),
        "seeds": list(G1_SEEDS),
        "methods": list(METHODS),
        "local_steps": LOCAL_STEPS,
        "git_commit": _git_hash(),
        "g0_config_hash": g0.get("config", {}).get("config_hash"),
        "threshold_hash": sha256_file(root / "configs/sag_g0/thresholds.json"),
        "epsilon_pred": EPS_PRED,
        "NAG_NOT_AVAILABLE_IN_G1": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    dump_json(config, out / "configs" / "config_g1_5seed.json")

    method_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    pred_rows: list[dict[str, Any]] = []
    struct_rows: list[dict[str, Any]] = []

    for dataset in G1_DATASETS:
        for seed in G1_SEEDS:
            prepared = prepare_sag_bundle(
                root=root, dataset=dataset, seed=int(seed), max_windows=None,
            )
            metrics_by_method: dict[str, dict[str, Any]] = {}
            for method in METHODS:
                runner, logs, window_metrics = _run_one_with_runner(
                    prepared=prepared,
                    method=method,
                    thresholds=thresholds,
                    local_steps=LOCAL_STEPS,
                )
                pred = _predict(runner, prepared["dataset"], split="test")
                mu_w = _mu_weights_for_test(pred, np.asarray(prepared["target_mu"]))
                rmse = float(rmse_mu(pred["y_pred"], pred["y_true"], mu_w)) if len(mu_w) else float("nan")
                mae = float(mae_mu(pred["y_pred"], pred["y_true"], mu_w)) if len(mu_w) else float("nan")
                worst = _worst_group_rmse(pred, mu_w)
                try:
                    d_g = float(delta_group(runner.omega_bar(), np.asarray(prepared["target_mu"])))
                except Exception:
                    d_g = float("nan")
                _, pair_summary = accumulate_delta_cs_v6(
                    window_metrics=window_metrics,
                    diagnostics=list(runner.diagnostics),
                    atomic=prepared["atomic_sealed"],
                    spatial_to_client=prepared["spatial_to_client"],
                    dataset=dataset,
                    seed=int(seed),
                    scenario="complete_aligned",
                    method=method,
                    eventtrace_hash=str(prepared["identity"].get("trace_hash")),
                    stratum_map_hash=None,
                    target_mass_hash=prepared["target_artifact_sha256"],
                    method_source_hash=None,
                )
                d_cs = pair_summary.get("Delta_c_s")
                on = [row for row in logs if int(row.get("G_r", 0)) == 1]
                off = [row for row in logs if int(row.get("G_r", 0)) == 0]
                mismatch = [row for row in logs if int(row.get("active_set_mismatch") or 0) == 1]
                false_enable = [row for row in on if int(row.get("active_set_mismatch") or 0) == 1]
                false_disable = [row for row in off if int(row.get("active_set_mismatch") or 0) == 0]
                rec = {
                    "dataset": dataset,
                    "seed": int(seed),
                    "method": method,
                    "RMSE_mu": rmse,
                    "MAE_mu": mae,
                    "WorstGroupRMSE": worst,
                    "Delta_group": d_g,
                    "Delta_cs": d_cs,
                    "Gate_ON_rate": (len(on) / len(logs)) if logs else 0.0,
                    "Gate_OFF_rate": (len(off) / len(logs)) if logs else 0.0,
                    "false_enable_rate": (len(false_enable) / len(on)) if on else 0.0,
                    "false_disable_rate": (len(false_disable) / len(off)) if off else float("nan"),
                    "active_set_mismatch_rate": (len(mismatch) / len(logs)) if logs else 0.0,
                    "P_mismatch_given_ON": (len(false_enable) / len(on)) if on else float("nan"),
                    "P_mismatch_given_OFF": (
                        sum(int(r.get("active_set_mismatch") or 0) for r in off) / len(off)
                        if off else float("nan")
                    ),
                }
                metrics_by_method[method] = rec
                method_rows.append(rec)
                for row in logs:
                    window_rows.append(
                        _flatten_log(row, dataset=dataset, seed=int(seed), method=method)
                    )
                common = [
                    row for row in logs
                    if int(row.get("both_empty") or 0) == 0
                    and int(row.get("active_set_mismatch") or 0) == 0
                    and row.get("Delta_beta") is not None
                ]
                if method == "raven_sag":
                    covers = {"beta": [], "M": [], "V": []}
                    widths = {"beta": [], "M": [], "V": []}
                    for row in common:
                        feat = row.get("gate_features") or {}
                        for name, actual_key, bound_key in (
                            ("beta", "Delta_beta", "Delta_beta_UCB"),
                            ("M", "Delta_M", "Delta_M_UCB"),
                            ("V", "Delta_V", "Delta_V_UCB"),
                        ):
                            c = _cover(row.get(actual_key), feat.get(bound_key))
                            if c is not None:
                                covers[name].append(c)
                            try:
                                widths[name].append(float(feat.get(bound_key)))
                            except (TypeError, ValueError):
                                pass
                    joint = []
                    n = min(len(covers["beta"]), len(covers["M"]), len(covers["V"]))
                    for i in range(n):
                        joint.append(covers["beta"][i] * covers["M"][i] * covers["V"][i])
                    coverage_rows.append({
                        "dataset": dataset,
                        "seed": int(seed),
                        "n_common_nonempty": len(common),
                        "coverage_beta": float(np.mean(covers["beta"])) if covers["beta"] else float("nan"),
                        "coverage_M": float(np.mean(covers["M"])) if covers["M"] else float("nan"),
                        "coverage_V": float(np.mean(covers["V"])) if covers["V"] else float("nan"),
                        "coverage_joint": float(np.mean(joint)) if joint else float("nan"),
                        "mean_width_beta": float(np.mean(widths["beta"])) if widths["beta"] else float("nan"),
                        "mean_width_M": float(np.mean(widths["M"])) if widths["M"] else float("nan"),
                        "mean_width_V": float(np.mean(widths["V"])) if widths["V"] else float("nan"),
                    })

            sag = metrics_by_method["raven_sag"]
            nod = metrics_by_method["raven_wo_design"]
            pred_rows.append({
                "dataset": dataset,
                "seed": int(seed),
                "RMSE_NoD": nod["RMSE_mu"],
                "RMSE_SAG": sag["RMSE_mu"],
                "relative_harm_RMSE": (
                    (sag["RMSE_mu"] - nod["RMSE_mu"]) / nod["RMSE_mu"]
                    if nod["RMSE_mu"] else float("nan")
                ),
                "Worst_NoD": nod["WorstGroupRMSE"],
                "Worst_SAG": sag["WorstGroupRMSE"],
                "relative_harm_Worst": (
                    (sag["WorstGroupRMSE"] - nod["WorstGroupRMSE"]) / nod["WorstGroupRMSE"]
                    if nod["WorstGroupRMSE"] else float("nan")
                ),
            })
            struct_rows.append({
                "dataset": dataset,
                "seed": int(seed),
                "Delta_group_NoD": nod["Delta_group"],
                "Delta_group_SAG": sag["Delta_group"],
                "gain_group": nod["Delta_group"] - sag["Delta_group"],
                "Delta_cs_NoD": nod["Delta_cs"],
                "Delta_cs_SAG": sag["Delta_cs"],
                "gain_cs": (
                    None if nod["Delta_cs"] is None or sag["Delta_cs"] is None
                    else float(nod["Delta_cs"]) - float(sag["Delta_cs"])
                ),
                "NAG_if_available": "NAG_NOT_AVAILABLE_IN_G1",
            })

    pd.DataFrame(method_rows).to_csv(out / "G1_METHOD_SUMMARY.csv", index=False)
    pd.DataFrame(window_rows).to_csv(out / "G1_GATE_WINDOW_LOG.csv", index=False)
    pd.DataFrame(coverage_rows).to_csv(out / "G1_CERTIFICATE_COVERAGE.csv", index=False)
    pd.DataFrame(pred_rows).to_csv(out / "G1_PREDICTION_SAFETY.csv", index=False)
    pd.DataFrame(struct_rows).to_csv(out / "G1_STRUCTURAL_GAIN.csv", index=False)

    report = _g1_verdict(method_rows, pred_rows, struct_rows, coverage_rows, g0)
    (out / "SAG_G0_G1_REPORT.md").write_text(report["markdown"], encoding="utf-8")
    dump_json(report["json"], out / "G1_VERDICT.json")
    return {"verdict": report["json"]["executive_verdict"], "output_dir": str(out)}


def _g1_verdict(
    method_rows: list[dict[str, Any]],
    pred_rows: list[dict[str, Any]],
    struct_rows: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
    g0: dict[str, Any],
) -> dict[str, Any]:
    sag = pd.DataFrame([r for r in method_rows if r["method"] == "raven_sag"])
    always = pd.DataFrame([r for r in method_rows if r["method"] == "raven"])
    pred = pd.DataFrame(pred_rows)
    struct = pd.DataFrame(struct_rows)
    cov = pd.DataFrame(coverage_rows) if coverage_rows else pd.DataFrame()

    gate1 = g0.get("verdict") == "PASS"
    mean_harm_rmse = float(pred["relative_harm_RMSE"].mean()) if len(pred) else float("nan")
    mean_harm_worst = float(pred["relative_harm_Worst"].mean()) if len(pred) else float("nan")
    gate4 = bool(mean_harm_rmse <= EPS_PRED and mean_harm_worst <= EPS_PRED)

    sag_on = float(sag["Gate_ON_rate"].mean()) if len(sag) else 0.0
    sag_fe = float(sag["false_enable_rate"].mean()) if len(sag) else float("nan")
    always_fe = float(always["false_enable_rate"].mean()) if len(always) else float("nan")
    gate3 = bool(np.isfinite(sag_fe) and np.isfinite(always_fe) and sag_fe < always_fe)

    joint = float(cov["coverage_joint"].mean()) if len(cov) and "coverage_joint" in cov else float("nan")
    gate2 = bool(np.isfinite(joint) and joint >= 0.90)

    gain_g = float(struct["gain_group"].mean()) if len(struct) else 0.0
    gate5 = bool(sag_on > 0.05 and gain_g > 0)

    flags = {
        "Gate-1 Predictability": gate1,
        "Gate-2 Certificate": gate2,
        "Gate-3 Safety": gate3,
        "Gate-4 Prediction": gate4,
        "Gate-5 Utility": gate5,
    }
    if not gate1:
        verdict = "STOP"
    elif not gate3 or (np.isfinite(mean_harm_rmse) and mean_harm_rmse > 0.05):
        verdict = "STOP"
    elif not gate2 or not gate4 or not gate5:
        verdict = "REPAIR"
    else:
        verdict = "GO"

    lines = [
        "# SAG G0/G1 Report",
        "",
        "# 1. Executive Verdict",
        verdict,
        "",
        "# 2. G0 Implementation Audit",
        f"G0 verdict: {g0.get('verdict')} (mode={g0.get('config', {}).get('mode')})",
        "",
        "# 3. Gate Behavior",
        f"SAG mean ON rate: {sag_on:.4f}",
        f"SAG mean false-enable: {sag_fe:.4f}",
        f"Always-D mean false-enable: {always_fe:.4f}",
        "",
        "# 4. Certificate Calibration",
        cov.to_string(index=False) if len(cov) else "no coverage rows",
        "",
        "# 5. Prediction Safety",
        f"mean relative RMSE harm: {mean_harm_rmse:.6f} (budget {EPS_PRED})",
        f"mean relative WorstGroup harm: {mean_harm_worst:.6f}",
        "",
        "# 6. Structural Utility",
        f"mean gain_group vs No-D: {gain_g:.6f}",
        "NAG_NOT_AVAILABLE_IN_G1",
        "",
        "# 7. Failure Analysis",
        f"ON rate <5% risk: {sag_on < 0.05}",
        "",
        "# 8. Go/Repair/Stop Decision",
    ]
    for name, ok in flags.items():
        lines.append(f"- {name}: {'PASS' if ok else 'FAIL'}")
    lines.extend(["", f"Decision: {verdict}", "", "# 9. Files Produced", "See outputs/sag_g1/", ""])
    return {"markdown": "\n".join(lines), "json": {"executive_verdict": verdict, "flags": flags}}


def main() -> None:
    parser = argparse.ArgumentParser(description="SAG G1 5-seed (requires G0 full PASS)")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    result = run_g1_main(root=args.root, output_dir=args.output_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
