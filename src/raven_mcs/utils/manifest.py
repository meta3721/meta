"""Run manifests for auditability and resume safety."""

from __future__ import annotations

import shutil
import socket
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from raven_mcs.utils.hashing import (
    config_hash,
    environment_fingerprint,
    environment_hash,
    is_sha256,
    run_hash,
    sha256_bytes,
    sha256_file,
    sha256_json,
)
from raven_mcs.utils.serialization import dump_json, dump_yaml, load_json
from raven_mcs.utils.seed import SeedBundle


REQUIRED_MANIFEST_FIELDS = (
    "run_id",
    "experiment",
    "dataset",
    "method",
    "scenario",
    "seed",
    "run_hash",
    "git_commit",
    "git_dirty",
    "git_state_hash",
    "config_hash",
    "data_hash",
    "event_trace_hash",
    "environment_hash",
    "hostname",
    "device",
    "start_time",
    "end_time",
    "solver",
    "hard_gate_status",
    "failure_reason",
)


VALID_GATE_STATUSES = frozenset({"PENDING", "PASS", "FAIL", "N/A"})


def git_executable() -> str | None:
    """Locate Git from PATH or standard Git-for-Windows install locations."""
    found = shutil.which("git")
    if found is not None:
        return found
    for candidate in (
        Path(r"C:\Program Files\Git\cmd\git.exe"),
        Path(r"C:\Program Files\Git\bin\git.exe"),
        Path(r"C:\Program Files (x86)\Git\cmd\git.exe"),
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _git_info(repo_root: Path | None = None) -> tuple[str, bool | None, str]:
    cwd = str(repo_root) if repo_root is not None else None
    git = git_executable()
    if git is None:
        return "NO_GIT", None, sha256_json({"git": "NO_GIT"})
    try:
        commit = subprocess.check_output(
            [git, "rev-parse", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "NO_GIT", None, sha256_json({"git": "NO_GIT"})
    try:
        status_bytes = subprocess.check_output(
            [git, "status", "--porcelain"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
        )
        dirty = bool(status_bytes.strip())
        diff_bytes = subprocess.check_output(
            [git, "diff", "--binary", "--no-ext-diff", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
        )
        untracked_bytes = subprocess.check_output(
            [git, "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
        )
        root = Path(cwd) if cwd is not None else Path.cwd()
        untracked_content = bytearray()
        for encoded_path in untracked_bytes.split(b"\0"):
            if not encoded_path:
                continue
            relative = encoded_path.decode("utf-8", errors="surrogateescape")
            path = root / relative
            untracked_content.extend(encoded_path)
            untracked_content.extend(b"\0")
            if path.is_file():
                untracked_content.extend(sha256_file(path).encode("ascii"))
            untracked_content.extend(b"\0")
        state_hash = sha256_bytes(
            status_bytes + b"\0" + diff_bytes + b"\0" + bytes(untracked_content)
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        dirty = None
        state_hash = sha256_json({"git": "STATE_UNAVAILABLE", "commit": commit})
    return commit, dirty, state_hash


@dataclass
class RunManifest:
    run_id: str
    experiment: str
    dataset: str
    method: str
    scenario: str
    seed: int
    run_hash: str
    git_commit: str
    git_dirty: bool | None
    git_state_hash: str
    config_hash: str
    data_hash: str
    event_trace_hash: str
    environment_hash: str
    hostname: str
    device: str
    start_time: str
    end_time: str | None = None
    solver: str = "CLARABEL"
    hard_gate_status: str = "PENDING"
    failure_reason: str | None = None
    seeds: dict[str, int] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    phase: str = "1"
    constitution_version: str = "V2.3"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self, *, final: bool = False) -> list[str]:
        """Return manifest schema/value violations."""
        data = self.to_dict()
        errors = [f"missing field: {key}" for key in REQUIRED_MANIFEST_FIELDS if key not in data]
        for field_name in (
            "run_hash",
            "config_hash",
            "data_hash",
            "event_trace_hash",
            "environment_hash",
        ):
            if not is_sha256(data.get(field_name)):
                errors.append(f"{field_name} must be a SHA-256 digest")
        if self.git_commit == "NO_GIT":
            if self.git_dirty is not None:
                errors.append("git_dirty must be null when git_commit=NO_GIT")
        elif not self.git_commit:
            errors.append("git_commit must be non-empty")
        elif not isinstance(self.git_dirty, bool):
            errors.append("git_dirty must be boolean for a Git repository")
        if not is_sha256(self.git_state_hash):
            errors.append("git_state_hash must be a SHA-256 digest")
        if self.hard_gate_status not in VALID_GATE_STATUSES:
            errors.append(f"invalid hard_gate_status: {self.hard_gate_status}")
        if final:
            if self.end_time is None:
                errors.append("end_time is required for a finalized manifest")
            else:
                try:
                    if datetime.fromisoformat(self.end_time) < datetime.fromisoformat(
                        self.start_time
                    ):
                        errors.append("end_time cannot precede start_time")
                except ValueError:
                    errors.append("start_time/end_time must be ISO-8601 timestamps")
            if self.hard_gate_status == "PENDING":
                errors.append("hard_gate_status cannot be PENDING when finalized")
            if self.hard_gate_status == "FAIL" and not self.failure_reason:
                errors.append("failure_reason is required when hard_gate_status=FAIL")
            if self.hard_gate_status in {"PASS", "N/A"} and self.failure_reason:
                errors.append(
                    "failure_reason must be null when hard_gate_status is PASS or N/A"
                )
        return errors

    def validate_complete(self) -> list[str]:
        """Backward-compatible alias for validating a running manifest."""
        return self.validate(final=False)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_manifest(
    *,
    run_id: str,
    config: Mapping[str, Any],
    seed_bundle: SeedBundle,
    data_hash: str = "UNSET",
    event_trace_hash: str = "UNSET",
    device: str | None = None,
    repo_root: Path | None = None,
    require_git: bool = False,
    allow_unset_hashes: bool = False,
) -> RunManifest:
    commit, dirty, git_state_hash = _git_info(repo_root)
    if require_git and (commit == "NO_GIT" or dirty is None):
        raise RuntimeError("Git is required for an auditable run, but no repository is available")
    if not allow_unset_hashes:
        if not is_sha256(data_hash):
            raise ValueError("data_hash must be a SHA-256 digest")
        if not is_sha256(event_trace_hash):
            raise ValueError("event_trace_hash must be a SHA-256 digest")
    elif data_hash == "UNSET":
        data_hash = sha256_json({"phase": 1, "data": "UNSET"})
    if allow_unset_hashes and event_trace_hash == "UNSET":
        event_trace_hash = sha256_json({"phase": 1, "event_trace": "UNSET"})

    solver = "UNKNOWN"
    solver_block = config.get("solver")
    if isinstance(solver_block, Mapping):
        solver = str(solver_block.get("backend", "UNKNOWN"))
    cfg_hash = config_hash(config)
    env_hash = environment_hash()
    identity_hash = run_hash(
        config_hash_value=cfg_hash,
        data_hash=data_hash,
        event_trace_hash=event_trace_hash,
        environment_hash_value=env_hash,
        git_commit=commit,
        git_state_hash=git_state_hash,
        seed=int(config.get("seed")),
    )
    manifest = RunManifest(
        run_id=run_id,
        experiment=str(config.get("experiment")),
        dataset=str(config.get("dataset")),
        method=str(config.get("method")),
        scenario=str(config.get("scenario")),
        seed=int(config.get("seed")),
        run_hash=identity_hash,
        git_commit=commit,
        git_dirty=dirty,
        git_state_hash=git_state_hash,
        config_hash=cfg_hash,
        data_hash=data_hash,
        event_trace_hash=event_trace_hash,
        environment_hash=env_hash,
        hostname=socket.gethostname(),
        device=device or str(config.get("device", "cpu")),
        start_time=utc_now_iso(),
        end_time=None,
        solver=solver,
        hard_gate_status="PENDING",
        failure_reason=None,
        seeds=seed_bundle.as_dict(),
        environment=environment_fingerprint(),
    )
    errors = manifest.validate()
    if errors:
        raise ValueError("Invalid manifest: " + "; ".join(errors))
    return manifest


def write_manifest(manifest: RunManifest, run_dir: Path) -> Path:
    path = Path(run_dir) / "manifest.json"
    dump_json(manifest.to_dict(), path)
    return path


def write_resolved_config(config: Mapping[str, Any], run_dir: Path) -> Path:
    path = Path(run_dir) / "resolved_config.yaml"
    dump_yaml(config, path)
    return path


def load_manifest(run_dir: Path) -> dict[str, Any]:
    return load_json(Path(run_dir) / "manifest.json")


def finalize_manifest(
    run_dir: Path,
    *,
    hard_gate_status: str,
    failure_reason: str | None = None,
) -> RunManifest:
    """Finalize a run manifest atomically with an end time and outcome."""
    if hard_gate_status not in VALID_GATE_STATUSES - {"PENDING"}:
        raise ValueError(f"Invalid final hard_gate_status: {hard_gate_status}")
    if hard_gate_status == "FAIL" and not failure_reason:
        raise ValueError("failure_reason is required for a failed run")
    data = load_manifest(run_dir)
    data["end_time"] = utc_now_iso()
    data["hard_gate_status"] = hard_gate_status
    data["failure_reason"] = failure_reason
    manifest = RunManifest(**data)
    errors = manifest.validate(final=True)
    if errors:
        raise ValueError("Invalid finalized manifest: " + "; ".join(errors))
    write_manifest(manifest, run_dir)
    return manifest


def assert_resume_config_hash(run_dir: Path, config: Mapping[str, Any]) -> None:
    """Refuse resume when config hash differs from the saved manifest."""
    existing = load_manifest(run_dir)
    expected = existing.get("config_hash")
    actual = config_hash(config)
    if expected != actual:
        raise RuntimeError(
            f"Resume refused: config hash mismatch "
            f"(manifest={expected}, current={actual})"
        )


def manifest_content_hash(manifest: RunManifest | Mapping[str, Any]) -> str:
    data = manifest.to_dict() if isinstance(manifest, RunManifest) else dict(manifest)
    return sha256_json(data)
