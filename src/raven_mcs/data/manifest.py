"""SHA-256 manifests for raw, interim, and processed dataset stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from raven_mcs.utils.hashing import sha256_file, sha256_json
from raven_mcs.utils.serialization import dump_json, load_json

DATA_MANIFEST_VERSION = "1.0"


class DataManifestError(ValueError):
    pass


@dataclass(frozen=True)
class DataFileHash:
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class DataStageHash:
    stage: str
    files: tuple[DataFileHash, ...]
    virtual_inputs: dict[str, Any]
    stage_hash: str


def _stage_payload(
    stage: str,
    files: tuple[DataFileHash, ...],
    virtual_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "stage": stage,
        "files": [asdict(item) for item in files],
        "virtual_inputs": dict(virtual_inputs),
    }


def build_stage_hash(
    root: Path,
    *,
    stage: str,
    virtual_inputs: Mapping[str, Any] | None = None,
) -> DataStageHash:
    root = Path(root)
    virtual = dict(virtual_inputs or {})
    paths = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    files = tuple(
        DataFileHash(
            relative_path=path.relative_to(root).as_posix(),
            size_bytes=path.stat().st_size,
            sha256=sha256_file(path),
        )
        for path in paths
    )
    if not files and not virtual:
        raise DataManifestError(f"{stage} stage has no files or virtual inputs: {root}")
    payload = _stage_payload(stage, files, virtual)
    return DataStageHash(
        stage=stage,
        files=files,
        virtual_inputs=virtual,
        stage_hash=sha256_json(payload),
    )


def freeze_data_manifest(
    *,
    dataset: str,
    raw_root: Path,
    interim_root: Path,
    processed_root: Path,
    output_path: Path,
    raw_virtual_inputs: Mapping[str, Any] | None = None,
    preparation_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze all three stage hashes into one atomically written manifest."""
    stages = {
        "raw": build_stage_hash(
            raw_root, stage="raw", virtual_inputs=raw_virtual_inputs
        ),
        "interim": build_stage_hash(interim_root, stage="interim"),
        "processed": build_stage_hash(processed_root, stage="processed"),
    }
    identity = {
        "manifest_version": DATA_MANIFEST_VERSION,
        "dataset": dataset,
        "preparation_identity": dict(preparation_identity or {}),
        "stages": {name: asdict(value) for name, value in stages.items()},
    }
    manifest = {
        **identity,
        "data_hash": sha256_json(identity),
        "created_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
    }
    dump_json(manifest, output_path)
    return manifest


def verify_data_manifest(
    manifest_path: Path,
    *,
    raw_root: Path,
    interim_root: Path,
    processed_root: Path,
) -> list[str]:
    """Return all mismatches between a frozen manifest and current files."""
    manifest = load_json(manifest_path)
    errors: list[str] = []
    roots = {
        "raw": Path(raw_root),
        "interim": Path(interim_root),
        "processed": Path(processed_root),
    }
    rebuilt: dict[str, DataStageHash] = {}
    for stage, root in roots.items():
        recorded = manifest["stages"][stage]
        try:
            rebuilt[stage] = build_stage_hash(
                root,
                stage=stage,
                virtual_inputs=recorded.get("virtual_inputs", {}),
            )
        except DataManifestError as exc:
            errors.append(str(exc))
            continue
        if rebuilt[stage].stage_hash != recorded.get("stage_hash"):
            errors.append(f"{stage} stage hash mismatch")

    if len(rebuilt) == 3:
        identity = {
            "manifest_version": manifest.get("manifest_version"),
            "dataset": manifest["dataset"],
            "preparation_identity": manifest.get("preparation_identity", {}),
            "stages": {
                name: asdict(rebuilt[name]) for name in ("raw", "interim", "processed")
            },
        }
        if sha256_json(identity) != manifest.get("data_hash"):
            errors.append("overall data_hash mismatch")
    return errors
