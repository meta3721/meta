"""Phase-1 tests: auditable run identity and output lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest

from raven_mcs.utils.config import resolve_run_config
from raven_mcs.utils.run import finalize_run, initialize_run
from raven_mcs.utils.seed import SeedBundle


DATA_HASH = "c" * 64
TRACE_HASH = "d" * 64


def test_initialize_run_writes_required_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONHASHSEED", "26001")
    cfg = resolve_run_config()
    context = initialize_run(
        config=cfg,
        seed_bundle=SeedBundle.from_master(26001),
        data_hash=DATA_HASH,
        event_trace_hash=TRACE_HASH,
        output_root=tmp_path,
        require_git=False,
        repo_root=tmp_path,
    )
    assert context.path.exists()
    assert context.run_hash in context.manifest.run_hash
    assert context.run_hash[:12] in context.run_id
    for name in (
        "manifest.json",
        "resolved_config.yaml",
        "environment.txt",
        "event_trace_ref.json",
        "checkpoints",
        "failure_snapshot",
    ):
        assert (context.path / name).exists()


def test_run_refuses_overwrite_and_supports_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONHASHSEED", "26001")
    cfg = resolve_run_config()
    kwargs = {
        "config": cfg,
        "seed_bundle": SeedBundle.from_master(26001),
        "data_hash": DATA_HASH,
        "event_trace_hash": TRACE_HASH,
        "output_root": tmp_path,
        "require_git": False,
        "repo_root": tmp_path,
    }
    context = initialize_run(**kwargs)
    with pytest.raises(FileExistsError, match="refusing overwrite"):
        initialize_run(**kwargs)
    resumed = initialize_run(**kwargs, resume=True)
    assert resumed.resumed is True
    assert resumed.run_hash == context.run_hash

    finalize_run(context, hard_gate_status="PASS")
    with pytest.raises(RuntimeError, match="already finalized"):
        initialize_run(**kwargs, resume=True)


def test_resume_rejects_changed_config_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONHASHSEED", "26001")
    cfg = resolve_run_config()
    context = initialize_run(
        config=cfg,
        seed_bundle=SeedBundle.from_config(cfg["seed"], cfg["seeds"]),
        data_hash=DATA_HASH,
        event_trace_hash=TRACE_HASH,
        output_root=tmp_path,
        require_git=False,
        repo_root=tmp_path,
    )
    changed = resolve_run_config(
        overrides={"clients": {"local_steps": cfg["clients"]["local_steps"] + 1}}
    )
    with pytest.raises(FileNotFoundError, match="Resume refused"):
        initialize_run(
            config=changed,
            seed_bundle=SeedBundle.from_config(changed["seed"], changed["seeds"]),
            data_hash=DATA_HASH,
            event_trace_hash=TRACE_HASH,
            output_root=tmp_path,
            resume=True,
            require_git=False,
            repo_root=tmp_path,
        )
    with pytest.raises(RuntimeError, match="config hash mismatch"):
        initialize_run(
            config=changed,
            seed_bundle=SeedBundle.from_config(changed["seed"], changed["seeds"]),
            data_hash=DATA_HASH,
            event_trace_hash=TRACE_HASH,
            output_root=tmp_path,
            resume=True,
            resume_from=context.path,
            require_git=False,
            repo_root=tmp_path,
        )


def test_dry_run_does_not_create_output(tmp_path: Path) -> None:
    context = initialize_run(
        config=resolve_run_config(),
        seed_bundle=SeedBundle.from_master(26001),
        data_hash=DATA_HASH,
        event_trace_hash=TRACE_HASH,
        output_root=tmp_path,
        dry_run=True,
        require_git=False,
        repo_root=tmp_path,
    )
    assert context.dry_run is True
    assert not context.path.exists()


def test_run_hash_changes_with_event_trace(tmp_path: Path) -> None:
    common = {
        "config": resolve_run_config(),
        "seed_bundle": SeedBundle.from_master(26001),
        "data_hash": DATA_HASH,
        "output_root": tmp_path,
        "dry_run": True,
        "require_git": False,
        "repo_root": tmp_path,
    }
    first = initialize_run(**common, event_trace_hash="1" * 64)
    second = initialize_run(**common, event_trace_hash="2" * 64)
    assert first.run_hash != second.run_hash
