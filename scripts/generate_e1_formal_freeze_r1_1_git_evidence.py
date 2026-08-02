#!/usr/bin/env python3
"""Generate authorized→candidate Git patch/source evidence for FREEZE-R1.1."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from raven_mcs.utils.hashing import sha256_file

AUTHORIZED = "53e277c53b01695330652b8e1bc8a234909d56e5"
CANDIDATE = "bb597a10e6369a49e18ccb6dc642a200bda1868c"


def _run(root: Path, *args: str, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args), cwd=root, check=True, capture_output=capture, text=True,
        encoding="utf-8", errors="replace",
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    git_dir = root / "evidence" / "git"
    src_dir = root / "evidence" / "source"
    git_dir.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(parents=True, exist_ok=True)

    patch = git_dir / "AUTHORIZED_TO_EXECUTION_CANDIDATE.patch"
    name_status = git_dir / "AUTHORIZED_TO_EXECUTION_NAME_STATUS.txt"
    diff_stat = git_dir / "AUTHORIZED_TO_EXECUTION_DIFF_STAT.txt"
    numstat = git_dir / "AUTHORIZED_TO_EXECUTION_NUMSTAT.txt"
    commits = git_dir / "AUTHORIZED_TO_EXECUTION_COMMITS.txt"
    tree = git_dir / "EXECUTION_CANDIDATE_TREE.txt"

    patch.write_bytes(
        subprocess.run(
            ["git", "diff", "--binary", AUTHORIZED, CANDIDATE],
            cwd=root, check=True, capture_output=True,
        ).stdout
    )
    name_status.write_text(
        _run(root, "git", "diff", "--name-status", AUTHORIZED, CANDIDATE).stdout,
        encoding="utf-8",
    )
    diff_stat.write_text(
        _run(root, "git", "diff", "--stat", AUTHORIZED, CANDIDATE).stdout,
        encoding="utf-8",
    )
    numstat.write_text(
        _run(root, "git", "diff", "--numstat", AUTHORIZED, CANDIDATE).stdout,
        encoding="utf-8",
    )
    commits.write_text(
        _run(
            root, "git", "log", "--oneline", "--decorate", "--graph",
            f"{AUTHORIZED}..{CANDIDATE}",
        ).stdout,
        encoding="utf-8",
    )
    tree.write_text(
        _run(root, "git", "ls-tree", "-r", "--full-tree", CANDIDATE).stdout,
        encoding="utf-8",
    )

    archive = src_dir / "RAVEN_MCS_EXECUTION_CANDIDATE_SOURCE.tar.gz"
    bundle = src_dir / "RAVEN_MCS_EXECUTION_CANDIDATE.bundle"
    _run(
        root, "git", "archive", "--format=tar.gz",
        f"--output={archive}", CANDIDATE, capture=False,
    )
    # Include history needed to reach candidate from authorized base.
    bundle_range = f"{AUTHORIZED}..{CANDIDATE}"
    create = subprocess.run(
        ["git", "bundle", "create", str(bundle), bundle_range],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    if create.returncode != 0:
        bundle_range = "--all"
        create = subprocess.run(
            ["git", "bundle", "create", str(bundle), "--all"],
            cwd=root, capture_output=True, text=True, encoding="utf-8",
            errors="replace",
        )
        if create.returncode != 0:
            raise RuntimeError(
                "git bundle create failed: "
                + (create.stderr or create.stdout or "")
            )
    verify = subprocess.run(
        ["git", "bundle", "verify", str(bundle)],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    verify_path = src_dir / "GIT_BUNDLE_VERIFY.txt"
    verify_path.write_text(
        (verify.stdout or "") + (verify.stderr or ""), encoding="utf-8",
    )
    if verify.returncode != 0:
        raise RuntimeError("git bundle verify failed")

    added = deleted = 0
    for line in numstat.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        if parts[0].isdigit():
            added += int(parts[0])
        if parts[1].isdigit():
            deleted += int(parts[1])
    changed = [
        line.split("\t", 1)[-1].strip()
        for line in name_status.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    commit_list = [
        line.strip()
        for line in commits.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    identity = {
        "authorized_algorithm_commit": AUTHORIZED,
        "execution_candidate_commit": CANDIDATE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "patch_sha256": sha256_file(patch),
        "name_status_sha256": sha256_file(name_status),
        "diff_stat_sha256": sha256_file(diff_stat),
        "numstat_sha256": sha256_file(numstat),
        "commits_sha256": sha256_file(commits),
        "tree_sha256": sha256_file(tree),
        "commit_list": commit_list,
        "changed_file_count": len(changed),
        "changed_files": changed,
        "added_line_count": added,
        "deleted_line_count": deleted,
        "patch_bytes": patch.stat().st_size,
        "patch_nonempty": patch.stat().st_size > 0,
    }
    (git_dir / "AUTHORIZED_TO_EXECUTION_DIFF_IDENTITY.json").write_text(
        json.dumps(identity, indent=2), encoding="utf-8",
    )

    # Count files inside archive without extracting fully.
    import tarfile

    with tarfile.open(archive, "r:gz") as tf:
        archive_file_count = sum(1 for m in tf.getmembers() if m.isfile())
    source_manifest = {
        "archive_sha256": sha256_file(archive),
        "bundle_sha256": sha256_file(bundle),
        "candidate_commit": CANDIDATE,
        "authorized_commit": AUTHORIZED,
        "archive_file_count": archive_file_count,
        "bundle_verify_status": "PASS",
        "bundle_range": bundle_range,
        "bundle_verify_log": str(verify_path.relative_to(root)).replace("\\", "/"),
    }
    (src_dir / "SOURCE_SNAPSHOT_MANIFEST.json").write_text(
        json.dumps(source_manifest, indent=2), encoding="utf-8",
    )
    print(json.dumps({
        "patch_sha256": identity["patch_sha256"],
        "changed_file_count": identity["changed_file_count"],
        "archive_sha256": source_manifest["archive_sha256"],
        "bundle_verify_status": "PASS",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
