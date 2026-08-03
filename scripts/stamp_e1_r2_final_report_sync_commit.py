#!/usr/bin/env python3
"""Stamp final_report_synchronization_commit into identity/snapshot and rebuild report."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def stamp(root: Path, commit: str) -> dict:
    root = Path(root).resolve()
    if commit in ("", "HEAD", "PENDING"):
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True,
        ).strip()
    identity_path = root / "outputs/audits/E1_R2_FINAL_PACKAGE_IDENTITY.json"
    snapshot_path = root / "outputs/audits/E1_R2_FINAL_REPORT_INPUT_SNAPSHOT.json"
    identity = _load(identity_path)
    snapshot = _load(snapshot_path)
    identity["final_report_synchronization_commit"] = commit
    snapshot["final_report_synchronization_commit"] = commit
    identity_path.write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    import sys
    sys.path.insert(0, str(root / "scripts"))
    from build_e1_r2_final_synchronized_report import build_report
    from audit_e1_r2_final_report_render import audit_report

    package = "E1_R2_FINAL_REPORT_SYNCHRONIZATION_R1"
    report = root / f"deliverables/TO_SUBMIT_{package}" / f"{package}_REPORT.docx"
    build_report(root, report)
    result = audit_report(report)
    out_json = root / "outputs/audits/E1_R2_FINAL_REPORT_RENDER_AUDIT.json"
    out_md = root / "outputs/audits/E1_R2_FINAL_REPORT_RENDER_AUDIT.md"
    out_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_md.write_text(
        f"# E1-R2 Final Report Render Audit\n\nStatus: **{result['status']}**\n",
        encoding="utf-8",
    )
    return {
        "final_report_synchronization_commit": commit,
        "report": report.as_posix(),
        "render_status": result["status"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--commit", default="HEAD")
    args = parser.parse_args(argv)
    print(json.dumps(stamp(args.root, args.commit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
