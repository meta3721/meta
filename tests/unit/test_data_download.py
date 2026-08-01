"""Download CLI / resolver smoke tests (no large network payloads)."""

from __future__ import annotations

from pathlib import Path

from raven_mcs.data.download import (
    download_dataset,
    load_dataset_download_config,
)


def test_dataset_yamls_declare_official_sources() -> None:
    for name in ("sensorscope", "uair", "traffic", "tdrive_speed"):
        cfg = load_dataset_download_config(name)
        download = cfg["download"]
        assert download["source_url"]
        assert download.get("artifacts") is not None or download.get("resolve_from_page")


def test_download_dry_run_sensorscope(tmp_path: Path) -> None:
    result = download_dataset(
        "sensorscope",
        data_root=tmp_path / "data",
        dry_run=True,
    )
    assert result.ok
    assert result.dry_run
    assert any(item["filename"] == "Sensorscope.zip" for item in result.files)


def test_download_dry_run_resolve_pages(tmp_path: Path) -> None:
    for name in ("uair", "tdrive_speed"):
        result = download_dataset(name, data_root=tmp_path / "data", dry_run=True)
        assert result.ok
        assert result.files
        assert result.files[0]["status"] == "would_resolve"
