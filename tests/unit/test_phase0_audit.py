from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from raven_mcs.experiments.phase0_audit import run_phase0_audit

ROOT = Path(__file__).resolve().parents[2]


def test_phase0_audit_covers_full_executable_scope() -> None:
    report = run_phase0_audit(ROOT, max_workers=2)
    scan_files = set(report["scan_files"])
    assert any(path.startswith("src/") for path in scan_files)
    assert any(path.startswith("scripts/") for path in scan_files)
    assert any(path.startswith("configs/") for path in scan_files)
    assert any(path.startswith("tests/") for path in scan_files)
    assert report["main_experiment_status"] in {"NOT_STARTED", "ARTIFACTS_FOUND"}
    # leakage.py is the denylist guard and is excluded from q-feature scans.
    # Aggregation/P2 cores may exist after E0; they must not use banned signals.
    assert report["scans"]["q_post_outcome"]["status"] in {
        "VACUOUS_NO_IMPLEMENTATION",
        "NO_MATCHES",
        "REVIEWED_WHITELIST_ONLY",
    }
    assert report["scans"]["p2_current_update"]["status"] in {
        "VACUOUS_NO_IMPLEMENTATION",
        "NO_MATCHES",
    }


def test_phase0_audit_records_forbidden_hits(tmp_path) -> None:
    files = {
        "scripts/train.py": "best = select_from_test_metric()\ndef on_arrival():\n    pass\n",
        "src/raven_mcs/propensity/usable.py": "q_features = ['realized', 'arrival']\n",
        "src/raven_mcs/aggregation/p2.py": "weight = current_update_norm\n",
    }
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    report = run_phase0_audit(tmp_path)
    assert report["scans"]["immediate_async"]["status"] == "MATCHES_REQUIRE_REVIEW"
    assert report["scans"]["test_tuning"]["status"] == "MATCHES_REQUIRE_REVIEW"
    assert report["scans"]["q_post_outcome"]["status"] == "MATCHES_REQUIRE_REVIEW"
    assert report["scans"]["p2_current_update"]["status"] == (
        "MATCHES_REQUIRE_REVIEW"
    )


def test_phase0_audit_cli_dry_run() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "audit_phase0.py"),
            "--dry-run",
            "--max-workers",
            "2",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "would_write=docs\\audits\\phase0_audit.json" in result.stdout
