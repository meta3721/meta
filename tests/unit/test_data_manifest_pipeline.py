from __future__ import annotations

from pathlib import Path

import pytest

from raven_mcs.data.manifest import freeze_data_manifest, verify_data_manifest
from raven_mcs.data.pipeline import load_processed_bundle, prepare_dataset
from raven_mcs.data.registry import get_dataset_adapter


def _stage_dirs(root: Path) -> tuple[Path, Path, Path]:
    raw = root / "raw"
    interim = root / "interim"
    processed = root / "processed"
    for path in (raw, interim, processed):
        path.mkdir(parents=True)
        (path / "artifact.bin").write_bytes(path.name.encode())
    return raw, interim, processed


def test_data_manifest_detects_mutation(tmp_path) -> None:
    raw, interim, processed = _stage_dirs(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    first = freeze_data_manifest(
        dataset="fixture",
        raw_root=raw,
        interim_root=interim,
        processed_root=processed,
        output_path=manifest_path,
    )
    assert verify_data_manifest(
        manifest_path,
        raw_root=raw,
        interim_root=interim,
        processed_root=processed,
    ) == []

    (processed / "artifact.bin").write_bytes(b"mutated")
    errors = verify_data_manifest(
        manifest_path,
        raw_root=raw,
        interim_root=interim,
        processed_root=processed,
    )
    assert "processed stage hash mismatch" in errors
    assert "overall data_hash mismatch" in errors
    assert len(first["data_hash"]) == 64


def test_prepare_freeze_resume_pipeline(tmp_path) -> None:
    result = prepare_dataset(
        "synthetic", data_root=tmp_path, seed=17, freeze=True
    )
    assert result.audit_passed
    assert result.data_hash is not None
    assert result.paths.manifest.exists()
    bundle = load_processed_bundle(result.paths)
    assert len(bundle.atomic_units) == 120
    assert len(bundle.client_measurements) == 360

    resumed = prepare_dataset(
        "synthetic",
        data_root=tmp_path,
        seed=17,
        freeze=True,
        resume=True,
    )
    assert resumed.resumed
    assert resumed.data_hash == result.data_hash

    with pytest.raises(RuntimeError, match="preparation seed"):
        prepare_dataset(
            "synthetic",
            data_root=tmp_path,
            seed=999,
            freeze=True,
            resume=True,
        )

    with pytest.raises(FileExistsError, match="refusing overwrite"):
        prepare_dataset("synthetic", data_root=tmp_path, seed=17, freeze=True)


def test_prepare_dry_run_writes_nothing(tmp_path) -> None:
    result = prepare_dataset(
        "synthetic",
        data_root=tmp_path,
        seed=3,
        freeze=True,
        dry_run=True,
    )
    assert result.dry_run
    assert list(tmp_path.iterdir()) == []


def test_real_adapters_are_registered_in_phase_2b() -> None:
    for name in ("sensorscope", "uair", "traffic", "tdrive_speed"):
        assert get_dataset_adapter(name).name in {
            "sensorscope",
            "uair",
            "traffic",
            "tdrive_speed",
        }
