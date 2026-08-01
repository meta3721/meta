"""Phase 2A preparation pipeline with freeze/resume semantics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from raven_mcs.data.audit import audit_processed_bundle, write_audit_report
from raven_mcs.data.base import DatasetMetadata, ProcessedBundle
from raven_mcs.data.manifest import freeze_data_manifest, verify_data_manifest
from raven_mcs.data.registry import get_dataset_adapter
from raven_mcs.data.scaling import TrainOnlyStandardizer
from raven_mcs.data.schema import write_processed_parquet
from raven_mcs.utils.serialization import dump_json, load_json


@dataclass(frozen=True)
class DatasetPaths:
    dataset: str
    raw: Path
    interim: Path
    processed: Path
    manifest: Path


@dataclass(frozen=True)
class PreparationResult:
    paths: DatasetPaths
    data_hash: str | None
    resumed: bool
    dry_run: bool
    audit_passed: bool | None


def dataset_paths(data_root: Path, dataset: str) -> DatasetPaths:
    root = Path(data_root)
    return DatasetPaths(
        dataset=dataset,
        raw=root / "raw" / dataset,
        interim=root / "interim" / dataset,
        processed=root / "processed" / dataset,
        manifest=root / "manifests" / f"{dataset}_manifest.json",
    )


def _has_files(path: Path) -> bool:
    return path.exists() and any(item.is_file() for item in path.rglob("*"))


def prepare_dataset(
    dataset: str,
    *,
    data_root: Path,
    seed: int,
    freeze: bool,
    resume: bool = False,
    dry_run: bool = False,
) -> PreparationResult:
    """Prepare one registered dataset without overwriting existing artifacts."""
    adapter = get_dataset_adapter(dataset)
    paths = dataset_paths(data_root, adapter.name)
    if paths.manifest.exists():
        if not resume:
            raise FileExistsError(
                f"Frozen dataset already exists; refusing overwrite: {paths.manifest}"
            )
        manifest = load_json(paths.manifest)
        recorded_identity = manifest.get("preparation_identity", {})
        if recorded_identity.get("seed") != int(seed):
            raise RuntimeError(
                "Resume refused: preparation seed does not match frozen manifest"
            )
        errors = verify_data_manifest(
            paths.manifest,
            raw_root=paths.raw,
            interim_root=paths.interim,
            processed_root=paths.processed,
        )
        if errors:
            raise RuntimeError("Resume refused: " + "; ".join(errors))
        return PreparationResult(
            paths=paths,
            data_hash=str(manifest["data_hash"]),
            resumed=True,
            dry_run=False,
            audit_passed=True,
        )
    if _has_files(paths.interim) or _has_files(paths.processed):
        raise FileExistsError(
            "Unfrozen interim/processed artifacts exist; refusing ambiguous overwrite"
        )
    if dry_run:
        return PreparationResult(
            paths=paths,
            data_hash=None,
            resumed=False,
            dry_run=True,
            audit_passed=None,
        )

    for path in (paths.raw, paths.interim, paths.processed, paths.manifest.parent):
        path.mkdir(parents=True, exist_ok=True)

    bundle = adapter.prepare(paths.raw, seed=int(seed))
    audit = audit_processed_bundle(bundle)
    write_audit_report(audit, paths.interim / "audit_report.json")
    if not audit.passed:
        raise RuntimeError(
            f"Data audit failed for {dataset}: {'; '.join(audit.errors)}"
        )

    scaler = TrainOnlyStandardizer.fit(bundle.atomic_units, ["target_value"])
    dump_json(scaler.to_dict(), paths.interim / "scaling.json")
    dump_json(asdict(bundle.metadata), paths.interim / "metadata.json")
    bundle.anomaly_records.to_parquet(
        paths.interim / "physical_anomalies.parquet", index=False
    )
    pd.DataFrame(
        {"source_trace_id": sorted(bundle.target_source_trace_ids)}
    ).to_parquet(paths.interim / "target_source_trace_ids.parquet", index=False)
    if bundle.fleet_assignments is not None and not bundle.fleet_assignments.empty:
        bundle.fleet_assignments.to_parquet(
            paths.interim / "fleet_assignments.parquet", index=False
        )
    write_processed_parquet(
        bundle.atomic_units, bundle.client_measurements, paths.processed
    )

    data_hash: str | None = None
    if freeze:
        virtual = (
            {"generator": "synthetic-v1", "seed": int(seed)}
            if adapter.name == "synthetic"
            else None
        )
        manifest = freeze_data_manifest(
            dataset=adapter.name,
            raw_root=paths.raw,
            interim_root=paths.interim,
            processed_root=paths.processed,
            output_path=paths.manifest,
            raw_virtual_inputs=virtual,
            preparation_identity={
                "adapter": type(adapter).__name__,
                "adapter_version": bundle.metadata.adapter_version,
                "seed": int(seed),
            },
        )
        data_hash = str(manifest["data_hash"])
    return PreparationResult(
        paths=paths,
        data_hash=data_hash,
        resumed=False,
        dry_run=False,
        audit_passed=True,
    )


def load_processed_bundle(paths: DatasetPaths) -> ProcessedBundle:
    """Load persisted Phase 2 artifacts for an independent audit command."""
    metadata = DatasetMetadata(**load_json(paths.interim / "metadata.json"))
    anomaly_records = pd.read_parquet(paths.interim / "physical_anomalies.parquet")
    target_sources = set(
        pd.read_parquet(paths.interim / "target_source_trace_ids.parquet")[
            "source_trace_id"
        ].astype(str)
    )
    return ProcessedBundle(
        atomic_units=pd.read_parquet(paths.processed / "atomic_units.parquet"),
        client_measurements=pd.read_parquet(
            paths.processed / "client_measurements.parquet"
        ),
        metadata=metadata,
        target_source_trace_ids=target_sources,
        anomaly_records=anomaly_records,
    )
