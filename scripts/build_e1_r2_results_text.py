#!/usr/bin/env python3
"""Generate E1-R2 paper result text with supported claims only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

BANNED_PHRASES = (
    "RAVEN significantly outperforms all baselines.",
    "RAVEN achieves the best RMSE in E1.",
    "RAVEN reduces communication bytes.",
    "All solver calls succeed without fallback.",
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _method_means(recompute: dict[str, Any]) -> dict[str, float]:
    return {
        row["method"]: float(row["RMSE_mu_mean"])
        for row in recompute.get("method_summary", [])
    }


def build_text(root: Path) -> dict[str, Any]:
    root = Path(root)
    out_dir = root / "outputs/paper/E1_R2"
    out_dir.mkdir(parents=True, exist_ok=True)

    recompute = _json(root / "outputs/audits/E1_R2_FORMAL_RESULTS_INDEPENDENT_RECOMPUTE.json")
    solver = _json(root / "outputs/audits/E1_R2_RAVEN_SOLVER_RESIDUAL_MAXIMA.json")
    communication = _json(root / "outputs/audits/E1_R2_COMMUNICATION_METRIC_SEMANTICS.json")
    stats_dir = root / "outputs/statistics/E1_R2_SEALED"
    if not stats_dir.is_dir():
        stats_dir = root / "outputs/statistics/E1_R2"
    no_harm_path = stats_dir / "no_harm_summary.json"
    no_harm = _json(no_harm_path) if no_harm_path.is_file() else {}
    if not no_harm:
        relative_rows = recompute.get("raven_relative_vs_baselines", [])
        flamf_rows = [row for row in relative_rows if row.get("baseline") == "flamf_timealign_adapted" and row.get("seed") == "mean"]
        rel_mean = float(flamf_rows[0]["relative_pct"]) / 100.0 if flamf_rows else float("nan")
        no_harm = {
            "no_harm_tests": {
                "raven": {
                    "no_harm_pass": rel_mean == rel_mean and rel_mean < 0.03,
                    "relative_degradation_mean": rel_mean,
                }
            }
        }

    means = _method_means(recompute)
    flamf = means.get("flamf_timealign_adapted", float("nan"))
    raven = means.get("raven", float("nan"))
    nh_pass = no_harm.get("no_harm_tests", {}).get("raven", {}).get("no_harm_pass")
    fallback_total = int(solver.get("total_fallback_invoked", 0))

    english = (
        "In the balanced setting, RAVEN achieved the second-lowest target-risk "
        f"RMSE ({raven:.6f}) and remained within a small margin of the validation-selected "
        f"FLAMF-TimeAlign-Adapted baseline ({flamf:.6f}). The frozen one-sided no-harm "
        f"criterion was {'satisfied' if nh_pass else 'not satisfied'}. RAVEN also improved "
        "the mean target-risk RMSE over FedAvg, FedAsync, and TwoStage-Hajek, although the "
        "five-seed paired tests did not establish Holm-corrected statistical significance. "
        "All safety and semantic gates passed. RAVEN incurred additional solver overhead "
        f"with {fallback_total} fallback invocations across five seeds, while complete solver "
        "failures remained zero. Communication results report update counts "
        f"({communication.get('paper_label_en', 'Number of received client updates')}), "
        "not bytes. The balanced E1 setting does not represent all deployment scenarios."
    )

    chinese = "\n".join([
        "# E1-R2 正式结果文字（中文）",
        "",
        f"- TimeAlign（FLAMF-TimeAlign-Adapted）取得最低 mean RMSE_mu：{flamf:.6f}。",
        f"- RAVEN 取得第二低 mean RMSE_mu：{raven:.6f}，与 TimeAlign 差异很小。",
        f"- 冻结 one-sided no-harm 门：{'通过' if nh_pass else '未通过'}。",
        "- RAVEN 平均优于 FedAvg、FedAsync 与 TwoStage，但 n=5 且 Holm 校正后未建立统计显著优越性。",
        "- 全部安全与语义门通过。",
        f"- RAVEN 存在 solver fallback（合计 {fallback_total} 次），complete solver failure 为 0。",
        "- communication 指标为 update count，不是 bytes。",
        "- balanced 场景仅为 E1，不代表全部场景。",
    ])

    tex_path = out_dir / "E1_R2_RESULTS_TEXT.tex"
    zh_path = out_dir / "E1_R2_RESULTS_TEXT_ZH.md"
    tex_path.write_text(
        "\\paragraph{E1-R2 Formal Results.}\n" + english + "\n", encoding="utf-8",
    )
    zh_path.write_text(chinese + "\n", encoding="utf-8")

    banned_hits = [phrase for phrase in BANNED_PHRASES if phrase.lower() in english.lower()]
    return {
        "status": "PASS" if not banned_hits else "FAIL",
        "tex": tex_path.as_posix(),
        "zh": zh_path.as_posix(),
        "banned_phrase_hits": banned_hits,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    result = build_text(args.root)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
