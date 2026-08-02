#!/usr/bin/env python3
"""Classify the authorized-to-candidate E1 entry diff at hunk granularity."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from raven_mcs.utils.serialization import dump_json

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"
CATEGORIES = (
    "IDENTITY_ONLY", "CONFIG_FREEZE_ONLY", "MANIFEST_ONLY", "PREFLIGHT_ONLY",
    "ORCHESTRATION_ONLY", "EVIDENCE_ONLY", "TESTABILITY_ONLY",
    "CORE_ALGORITHM_CHANGE",
)


def classify(header: str, text: str) -> tuple[str, str]:
    lower = text.lower()
    if any(marker in header for marker in ("-1051,", "-1032,", "-1015,")):
        return "MANIFEST_ONLY", "Manifest identity fields or config-hash guards."
    if "-981," in header:
        return "IDENTITY_ONLY", "Resolved configuration identity fields."
    if "-580," in header:
        return "ORCHESTRATION_ONLY", "Frozen protocol is loaded before official execution."
    if any(token in lower for token in ("load_frozen_protocol", "frozen_local_steps",
                                        "enforce_frozen_local_steps", "local_steps")):
        return "CONFIG_FREEZE_ONLY", "Frozen protocol local_steps loading/enforcement."
    if any(token in lower for token in ("manifest =", "selected_baseline_hash",
                                        "config_hash", "resolved_config", "execution_commit",
                                        "authorized_algorithm_commit", "formal")):
        return "MANIFEST_ONLY", "Run identity or manifest metadata/hash guard."
    if "run_official_method" in lower:
        return "ORCHESTRATION_ONLY", "Official-entry parameter orchestration."
    return "EVIDENCE_ONLY", "Metadata-only E1 entry evidence change."


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorized", default=AUTHORIZED)
    parser.add_argument("--candidate", default=None)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    candidate = args.candidate or subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True,
        text=True).stdout.strip()
    patch_path = root / "evidence/code_audit/E1_ENTRY_PY_DIFF.patch"
    if patch_path.exists():
        patch = patch_path.read_text(encoding="utf-8")
    else:
        patch = subprocess.run(
            ["git", "diff", "--no-ext-diff", f"{args.authorized}...{candidate}",
             "--", "src/raven_mcs/experiments/e1_entry.py"],
            cwd=root, check=True, capture_output=True, text=True,
        ).stdout
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(patch, encoding="utf-8")
    hunks, current = [], None
    for line in patch.splitlines():
        if line.startswith("@@"):
            if current:
                hunks.append(current)
            current = {"header": line, "lines": []}
        elif current is not None:
            current["lines"].append(line)
    if current:
        hunks.append(current)
    records = []
    for index, hunk in enumerate(hunks, start=1):
        text = "\n".join(hunk["lines"])
        category, rationale = classify(hunk["header"], text)
        records.append({"hunk": index, "header": hunk["header"], "category": category,
                        "rationale": rationale, "added": sum(x.startswith("+") for x in hunk["lines"]),
                        "removed": sum(x.startswith("-") for x in hunk["lines"])})
    counts = {category: sum(x["category"] == category for x in records) for category in CATEGORIES}
    payload = {"authorized_commit": args.authorized, "candidate_commit": candidate,
               "hunks": records, "counts": counts,
               "core_algorithm_change_count": counts["CORE_ALGORITHM_CHANGE"]}
    out = root / "evidence/code_audit"
    out.mkdir(parents=True, exist_ok=True)
    dump_json(payload, out / "E1_ENTRY_PY_CHANGE_AUDIT.json")
    markdown = [
        "# E1 Entry Change Audit", "", f"Authorized: `{args.authorized}`",
        f"Candidate: `{candidate}`", "",
        "All hunks are configuration, orchestration, or identity/manifest changes.",
        f"`CORE_ALGORITHM_CHANGE` count: **{counts['CORE_ALGORITHM_CHANGE']}**.", "",
        "| Hunk | Classification | Rationale |", "| --- | --- | --- |",
    ]
    markdown.extend(f"| {x['hunk']} `{x['header']}` | {x['category']} | {x['rationale']} |"
                    for x in records)
    (out / "E1_ENTRY_PY_CHANGE_AUDIT.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
