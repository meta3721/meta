"""Auditable run initialization/finalization and output-directory ownership."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from raven_mcs.utils.hashing import canonical_json
from raven_mcs.utils.manifest import (
    RunManifest,
    assert_resume_config_hash,
    build_manifest,
    finalize_manifest,
    load_manifest,
    write_manifest,
    write_resolved_config,
)
from raven_mcs.utils.paths import ensure_run_layout, make_run_id
from raven_mcs.utils.seed import SeedBundle, assert_preconfigured_python_hash_seed
from raven_mcs.utils.serialization import atomic_write_text, dump_json
from raven_mcs.utils.validation import assert_valid_config


@dataclass(frozen=True)
class RunContext:
    run_id: str
    run_hash: str
    path: Path
    manifest: RunManifest
    resumed: bool
    dry_run: bool


def initialize_run(
    *,
    config: Mapping[str, Any],
    seed_bundle: SeedBundle,
    data_hash: str,
    event_trace_hash: str,
    output_root: Path | None = None,
    resume: bool = False,
    resume_from: Path | None = None,
    dry_run: bool = False,
    require_git: bool = True,
    repo_root: Path | None = None,
) -> RunContext:
    """
    Claim and initialize one immutable run directory.

    Existing outputs are never overwritten. Resume requires both config hash and
    immutable run hash to match and refuses finalized runs.
    """
    resolved = assert_valid_config(config)
    if not dry_run:
        assert_preconfigured_python_hash_seed(int(resolved["seed"]))
    provisional = build_manifest(
        run_id="PENDING",
        config=resolved,
        seed_bundle=seed_bundle,
        data_hash=data_hash,
        event_trace_hash=event_trace_hash,
        repo_root=repo_root,
        require_git=require_git,
    )
    run_id = make_run_id(
        experiment=provisional.experiment,
        dataset=provisional.dataset,
        method=provisional.method,
        scenario=provisional.scenario,
        seed=provisional.seed,
        run_hash=provisional.run_hash,
    )
    provisional.run_id = run_id
    root = Path(output_root or str(resolved["output_dir"]))
    path = root / run_id

    if resume_from is not None and not resume:
        raise ValueError("resume_from requires resume=True")
    if resume:
        resume_path = Path(resume_from) if resume_from is not None else path
        if not resume_path.exists():
            raise FileNotFoundError(
                "Resume refused: target run directory does not exist; "
                "provide resume_from for an existing run"
            )
        assert_resume_config_hash(resume_path, resolved)
        existing = load_manifest(resume_path)
        if existing.get("run_hash") != provisional.run_hash:
            raise RuntimeError(
                "Resume refused: immutable run hash differs "
                f"(manifest={existing.get('run_hash')}, current={provisional.run_hash})"
            )
        if existing.get("end_time") is not None:
            raise RuntimeError("Resume refused: run is already finalized")
        restored = RunManifest(**existing)
        return RunContext(
            run_id=run_id,
            run_hash=restored.run_hash,
            path=resume_path,
            manifest=restored,
            resumed=True,
            dry_run=False,
        )
    if path.exists():
        raise FileExistsError(
            f"Run directory already exists; refusing overwrite: {path}"
        )

    context = RunContext(
        run_id=run_id,
        run_hash=provisional.run_hash,
        path=path,
        manifest=provisional,
        resumed=False,
        dry_run=dry_run,
    )
    if dry_run:
        return context

    # mkdir(exist_ok=False) is the atomic ownership claim across workers.
    path.mkdir(parents=True, exist_ok=False)
    ensure_run_layout(path)
    write_manifest(provisional, path)
    write_resolved_config(resolved, path)
    atomic_write_text(
        path / "environment.txt",
        canonical_json(provisional.environment) + "\n",
    )
    dump_json(
        {"event_trace_hash": event_trace_hash},
        path / "event_trace_ref.json",
    )
    return context


def finalize_run(
    context: RunContext,
    *,
    hard_gate_status: str,
    failure_reason: str | None = None,
) -> RunManifest:
    """Finalize a non-dry run and atomically persist its outcome."""
    if context.dry_run:
        raise RuntimeError("Cannot finalize a dry-run context")
    return finalize_manifest(
        context.path,
        hard_gate_status=hard_gate_status,
        failure_reason=failure_reason,
    )
