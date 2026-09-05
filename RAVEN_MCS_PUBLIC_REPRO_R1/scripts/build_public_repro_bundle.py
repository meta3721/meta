"""Build the public reproducibility bundle for the TMC manuscript.

Copies frozen seeds, configs, EventTraces, tabulated results, and the
coverage-audit records. Does not copy GPU checkpoints or the sealed
training-run dumps. Does not start SAG or retrain E3/E4.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "RAVEN_MCS_PUBLIC_REPRO_R1"

SEEDS_E1 = list(range(28001, 28006))
SEEDS_E234 = list(range(30001, 30021))
SEEDS_TDRIVE = list(range(30001, 30011))

MAX_NONTRACE_BYTES = 20 * 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path, *, skip_suffixes: tuple[str, ...] = (".pt",)) -> int:
    n = 0
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() in skip_suffixes:
            continue
        rel = f.relative_to(src)
        copy_file(f, dst / rel)
        n += 1
    return n


def copy_if_small(src: Path, dst: Path) -> bool:
    if not src.is_file():
        return False
    if src.stat().st_size > MAX_NONTRACE_BYTES:
        return False
    copy_file(src, dst)
    return True


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def protocol_payload() -> dict:
    return {
        "bundle_id": "RAVEN_MCS_PUBLIC_REPRO_R1",
        "paper_method": "support-conditional Design (SCD)",
        "design_rule": {
            "SensorScope": "ON (compatible target support)",
            "U-Air": "OFF (25.5% zero-target mass; withheld)",
            "coverage_Gate": "diagnostic audit only; not the E3/E4 Design switch",
        },
        "seeds": {
            "E1_balanced_no_harm": SEEDS_E1,
            "E2_E3_E4": SEEDS_E234,
            "TDrive_opportunity_replay": SEEDS_TDRIVE,
        },
        "lambdas": {
            "lambda_group": 1.0,
            "lambda_beta": 1.0,
            "lambda_v": 0.1,
            "lambda_s": 0.1,
            "alpha_max": 0.5,
            "ESS_constraints": 3.0,
        },
        "certificate_audit": {
            "role": "window-level lower bound on aggregate opportunity coverage C_t",
            "tau_cov": 0.05,
            "alpha": 0.05,
            "n_min": 19,
            "availability_grid": [1.00, 0.80, 0.60, 0.40, 0.20],
            "reset": "after a completed CERTIFIED window if C_LCB > C_t",
            "predictor": "ridge, alpha=1.0, legal pre-window features only",
        },
        "environment": {
            "python": "3.11",
            "table_verify": ["numpy", "pandas"],
            "retraining_optional": ["torch>=2.1", "cvxpy>=1.4", "clarabel>=0.7"],
        },
        "not_included": [
            "GPU checkpoints (.pt)",
            "full E3/E4 training-run dumps",
            "T-Drive unit-level opportunity audit CSV",
        ],
    }


def readme_text() -> str:
    return """# RAVEN-MCS public reproducibility bundle

This directory is the frozen public artifact for the TMC manuscript.
It lets a reader check the tabulated numbers, the paired seeds, the
target maps, the selection-protocol configs, and the EventTraces used
by the evaluation. It does not require GPU-scale retraining.

## What is in the bundle

- `PROTOCOL.json`: support-conditional Design rule, seeds, P2 lambdas, and the diagnostic coverage-audit constants.
- `configs/`: frozen target maps, opportunity strata, E2 run config, E3 source hashes, E4 one-factor spec.
- `eventtraces/`: E1 formal traces; E2 NSW-Traffic traces (20 seeds x 6 scenarios); E3 SensorScope / U-Air / Traffic traces (20 seeds).
- `tables/` and `figures/`: CSVs that generate the manuscript tables and figures.
- `certificate/`: coverage-stress audit records (diagnostic Gate, not the paper Design switch).
- `processed/`: processed atomic units for SensorScope, U-Air, and NSW-Traffic.
- `tdrive/`: opportunity-replay target and seed policy. T-Drive is not a method ranking.
- `verify.py`: SHA-256 check against `MANIFEST.csv`.

## Verify the bundle

```bash
python verify.py
```

The verifier hashes every listed file. It does not retrain models.

## Ranking versus replay

SensorScope and U-Air ranking uses a Complete-aligned selection protocol.
Protocol opportunity on those traces is always-on; the original station
records are not claimed to contain mobile clients. T-Drive is an
opportunity replay under real taxi mobility. It is not used to rank methods.

## Retraining (optional)

End-to-end 20-seed retraining is optional. It needs Python 3.11, the
`raven-mcs` package in the companion repository, the public raw datasets
(SensorScope, U-Air, NSW-Traffic, T-Drive; cited in the paper), and the
EventTraces in this bundle. FedAU-Window and ObsUse-Window are windowed
adaptations, not official reproductions of those systems.

Use the seeds in `PROTOCOL.json`. On SensorScope, Design is on. On U-Air,
Design is off. Do not treat the coverage Gate as the E3 method.

## Licenses

Upstream dataset licenses remain those of the public sources. Code in the
companion repository follows that repository's license. This bundle is a
research artifact of tabulated results, traces, and configs.
"""


def license_text() -> str:
    return """RAVEN-MCS public reproducibility bundle.

This artifact redistributes derived tables, configs, and EventTraces for
research verification of the associated manuscript. The original
SensorScope, U-Air, NSW-Traffic, and T-Drive datasets remain under their
upstream licenses. Do not treat this bundle as an official release of
FedAU or ObsUse.
"""


def build() -> int:
    if not (ROOT / "TO_OVERLEAF_paper_tmc_r1_clean" / "main.tex").is_file():
        print("manuscript missing", file=sys.stderr)
        return 2

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    write_json(OUT / "PROTOCOL.json", protocol_payload())
    (OUT / "README.md").write_text(readme_text(), encoding="utf-8")
    (OUT / "LICENSE.txt").write_text(license_text(), encoding="utf-8")
    copy_file(Path(__file__), OUT / "scripts" / "build_public_repro_bundle.py")

    write_json(
        OUT / "configs" / "seeds.json",
        {
            "E1_balanced_no_harm": SEEDS_E1,
            "E2_E3_E4": SEEDS_E234,
            "TDrive_opportunity_replay": SEEDS_TDRIVE,
        },
    )
    write_json(
        OUT / "configs" / "design_rule.json",
        {
            "name": "support-conditional Design",
            "SensorScope": "ON",
            "U-Air": "OFF",
            "coverage_Gate": "diagnostic only",
        },
    )

    copy_tree(
        ROOT / "configs" / "frozen" / "e3_multidataset_protocol_closure",
        OUT / "configs" / "protocol_closure",
    )
    copy_file(
        ROOT / "artifacts" / "e2_traffic_formal_runs_r1" / "FORMAL_RUN_CONFIG.json",
        OUT / "configs" / "e2_formal_run_config.json",
    )
    copy_file(
        ROOT / "configs" / "frozen" / "e2_traffic_profiles_s1" / "traffic_s1_s6_profile_registry.json",
        OUT / "configs" / "e2_profile_registry.json",
    )
    copy_file(
        ROOT / "configs" / "frozen" / "e3_target_pair_metric_final_r1" / "E3_FINAL_INTEGRATION_SOURCE_HASHES.json",
        OUT / "configs" / "e3_source_hashes.json",
    )
    copy_file(
        ROOT / "artifacts" / "e4_wo_inst_reference_penalty_final_correction_r1" / "E4_WO_INST_FINAL_ONE_FACTOR_SPEC.json",
        OUT / "configs" / "e4_one_factor_spec.json",
    )

    copy_tree(ROOT / "data" / "frozen" / "e1_r2" / "formal", OUT / "eventtraces" / "e1_formal")
    copy_tree(ROOT / "artifacts" / "e2_traffic_formal_runs_r1" / "eventtraces", OUT / "eventtraces" / "e2")
    copy_tree(ROOT / "artifacts" / "e3_formal_runs_r1" / "eventtraces", OUT / "eventtraces" / "e3")
    copy_file(
        ROOT / "paper_ready_r2" / "05_provenance" / "E2_EVENTTRACE_INDEX_120.csv",
        OUT / "eventtraces" / "E2_EVENTTRACE_INDEX.csv",
    )
    copy_file(
        ROOT / "artifacts" / "e3_formal_runs_r1" / "E3_FORMAL_EVENTTRACE_MANIFEST.json",
        OUT / "eventtraces" / "E3_EVENTTRACE_MANIFEST.json",
    )
    copy_file(
        ROOT / "artifacts" / "e2_traffic_formal_runs_r1" / "eventtrace_manifest.csv",
        OUT / "eventtraces" / "E2_EVENTTRACE_MANIFEST.csv",
    )

    table_files = [
        "TABLE_E1_BALANCED_SANITY.csv",
        "TABLE_E2_RISK_SEMANTICS.csv",
        "TABLE_E3_MAIN_EFFECTIVENESS.csv",
        "TABLE_E3_FULL_METHODS_SUPPLEMENT.csv",
        "TABLE_E4_CORE_ABLATION.csv",
        "TABLE_E4_COMPONENT_EFFECTS.csv",
        "TABLE_DATASET_SUMMARY.csv",
    ]
    for name in table_files:
        copy_file(ROOT / "paper_ready_r2" / "06_table_sources" / name, OUT / "tables" / name)
    copy_file(
        ROOT / "paper_ready_r2" / "01_core_data" / "master" / "PAPER_EVIDENCE_MASTER_LONG.csv",
        OUT / "tables" / "PAPER_EVIDENCE_MASTER_LONG.csv",
    )
    copy_file(
        ROOT / "paper_ready_r2" / "01_core_data" / "e4" / "E4_ABLATION_RELATIVE_CHANGE.csv",
        OUT / "tables" / "E4_ABLATION_RELATIVE_CHANGE.csv",
    )
    copy_file(
        ROOT / "artifacts" / "e3_formal_runs_r1" / "E3_FORMAL_HOLM_RESULTS.csv",
        OUT / "tables" / "E3_FORMAL_HOLM_RESULTS.csv",
    )
    copy_file(
        ROOT / "artifacts" / "e4_core_mechanism_ablation_r1" / "E4_ABLATION_HOLM_RESULTS.csv",
        OUT / "tables" / "E4_ABLATION_HOLM_RESULTS.csv",
    )
    copy_file(
        ROOT / "paper_ready_r2" / "05_provenance" / "FINAL_CONFIG_REGISTRY_R2.csv",
        OUT / "tables" / "CONFIG_REGISTRY.csv",
    )

    fig_src = ROOT / "TO_OVERLEAF_paper_tmc_r1_clean" / "figure_data"
    for f in sorted(fig_src.glob("*.csv")):
        copy_file(f, OUT / "figures" / f.name)

    copy_file(
        ROOT / "TO_OVERLEAF_paper_tmc_r1_clean" / "figure_data" / "FIG_CERTIFICATE_STRESS.csv",
        OUT / "certificate" / "CERTIFICATE_STRESS.csv",
    )
    copy_file(
        ROOT / "TO_OVERLEAF_paper_tmc_r1_clean" / "figure_data" / "FIG_CERTIFICATE_WINDOWS.csv",
        OUT / "certificate" / "CERTIFICATE_WINDOWS.csv",
    )
    copy_file(
        ROOT / "results_sag_g1" / "round_r1m" / "eval" / "R1M_TRACK_METRICS.csv",
        OUT / "certificate" / "CERTIFICATE_TRACK_METRICS.csv",
    )
    copy_file(
        ROOT / "results_sag_g1" / "round_r1m" / "certificate" / "R1M_CERTIFICATE_BY_WINDOW.csv",
        OUT / "certificate" / "CERTIFICATE_BY_WINDOW.csv",
    )
    cert_protocol = json.loads((ROOT / "results_sag_g1" / "round_r1m" / "freeze" / "R1M_FREEZE.json").read_text(encoding="utf-8"))
    write_json(
        OUT / "certificate" / "CERTIFICATE_PROTOCOL.json",
        {
            "role": "diagnostic coverage Gate",
            "tau_cov": cert_protocol["tau_cov"],
            "alpha": cert_protocol["alpha"],
            "n_min": cert_protocol["n_min"],
            "availability_grid": cert_protocol["A_GRID"],
            "reset": cert_protocol["reset"],
            "predictor": cert_protocol["predictor"],
            "gate_mode": cert_protocol["gate_mode"],
        },
    )

    for ds in ("sensorscope", "uair", "traffic"):
        src_dir = ROOT / "data" / "processed" / ds
        if src_dir.is_dir():
            copy_tree(src_dir, OUT / "processed" / ds)

    tdrive_small = [
        ROOT / "tdrive_protocol_seal_r1" / "03_target" / "TDRIVE_TARGET_H_SEAL.json",
        ROOT / "tdrive_protocol_seal_r1" / "03_target" / "TDRIVE_TARGET_MU.csv",
        ROOT / "tdrive_protocol_seal_r1" / "03_target" / "TDRIVE_TARGET_MU_SEAL.json",
        ROOT / "tdrive_protocol_seal_r1" / "06_eventtrace" / "TDRIVE_SEED_POLICY_SEAL.json",
        ROOT / "tdrive_protocol_seal_r1" / "06_eventtrace" / "TDRIVE_EVENTTRACE_SCHEMA.json",
        ROOT / "tdrive_protocol_seal_r1" / "04_selection" / "TDRIVE_REAL_MOBILITY_OPPORTUNITY_SEAL.json",
        ROOT / "tdrive_protocol_seal_r1" / "04_selection" / "TDRIVE_OPPORTUNITY_DISTRIBUTION_SUMMARY.csv",
        ROOT / "tdrive_protocol_seal_r1" / "04_selection" / "TDRIVE_OBSERVATION_SEAL.json",
        ROOT / "tdrive_protocol_seal_r1" / "04_selection" / "TDRIVE_USABLE_UPDATE_SEAL.json",
    ]
    for src in tdrive_small:
        copy_if_small(src, OUT / "tdrive" / src.name)

    verify_py = '''"""SHA-256 verifier for RAVEN_MCS_PUBLIC_REPRO_R1."""
from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    manifest = ROOT / "MANIFEST.csv"
    if not manifest.is_file():
        print("MANIFEST.csv missing", file=sys.stderr)
        return 2
    n = 0
    bad = 0
    with manifest.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rel = row["path"].replace("\\\\", "/")
            path = ROOT / rel
            n += 1
            if not path.is_file():
                print(f"MISSING {rel}")
                bad += 1
                continue
            got = sha256_file(path)
            if got != row["sha256"]:
                print(f"HASH_MISMATCH {rel}")
                bad += 1
    print(f"checked={n} mismatches={bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''
    (OUT / "verify.py").write_text(verify_py, encoding="utf-8")
    write_json(
        OUT / "BUNDLE_SUMMARY.json",
        {
            "bundle_id": "RAVEN_MCS_PUBLIC_REPRO_R1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
        },
    )

    rows = []
    for f in sorted(p for p in OUT.rglob("*") if p.is_file()):
        rel = f.relative_to(OUT).as_posix()
        if rel == "MANIFEST.csv":
            continue
        rows.append(
            {
                "path": rel,
                "bytes": f.stat().st_size,
                "sha256": sha256_file(f),
            }
        )
    man = OUT / "MANIFEST.csv"
    with man.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "bytes", "sha256"])
        w.writeheader()
        w.writerows(rows)

    payload = sum(int(r["bytes"]) for r in rows)
    print(f"wrote {OUT}")
    print(f"files={len(rows)} bytes={payload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
