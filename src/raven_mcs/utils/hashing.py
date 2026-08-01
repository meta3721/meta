"""Hashing helpers for configs, data, traces, and environment."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
from typing import Any, Mapping

NON_IDENTITY_CONFIG_KEYS = frozenset(
    {"resume", "dry_run", "max_workers", "fail_fast", "output_dir"}
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_path_tree(root: Path, patterns: tuple[str, ...] = ("**/*",)) -> str:
    """Hash sorted relative file paths + contents under root."""
    root = Path(root)
    if not root.exists():
        return sha256_text(f"MISSING:{root.as_posix()}")
    files: list[Path] = []
    for pattern in patterns:
        files.extend(p for p in root.glob(pattern) if p.is_file())
    files = sorted({p.resolve() for p in files}, key=lambda p: p.as_posix())
    h = hashlib.sha256()
    for path in files:
        rel = path.relative_to(root.resolve()).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(sha256_file(path).encode("ascii"))
        h.update(b"\0")
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def sha256_json(obj: Any) -> str:
    return sha256_text(canonical_json(obj))


def environment_fingerprint() -> dict[str, Any]:
    packages = sorted(
        (
            {
                "name": dist.metadata.get("Name", "unknown").lower(),
                "version": dist.version,
            }
            for dist in importlib.metadata.distributions()
        ),
        key=lambda item: (item["name"], item["version"]),
    )
    return {
        "python_version": sys.version,
        "python_version_info": list(sys.version_info[:3]),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "executable": sys.executable,
        "packages": packages,
    }


def environment_hash() -> str:
    return sha256_json(environment_fingerprint())


def config_hash(config: Mapping[str, Any]) -> str:
    """Hash scientific run identity while excluding execution-control flags."""
    return sha256_json(
        {
            key: value
            for key, value in config.items()
            if key not in NON_IDENTITY_CONFIG_KEYS
        }
    )


def run_hash(
    *,
    config_hash_value: str,
    data_hash: str,
    event_trace_hash: str,
    environment_hash_value: str,
    git_commit: str,
    git_state_hash: str,
    seeds: Mapping[str, int],
) -> str:
    """Hash the immutable identity of a run, excluding timestamps/results."""
    return sha256_json(
        {
            "config_hash": config_hash_value,
            "data_hash": data_hash,
            "event_trace_hash": event_trace_hash,
            "environment_hash": environment_hash_value,
            "git_commit": git_commit,
            "git_state_hash": git_state_hash,
            "seeds": {key: int(value) for key, value in sorted(seeds.items())},
        }
    )


def is_sha256(value: object) -> bool:
    """Return whether *value* is a lowercase or uppercase SHA-256 hex digest."""
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True
