#!/usr/bin/env python3
"""G0 data-integrity gate for frozen paper datasets (Phase 2B)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from raven_mcs.data.audit import assert_record_sources_disjoint, audit_processed_bundle
from raven_mcs.data.base import DatasetMetadata, ProcessedBundle
from raven_mcs.data.fleet import assert_fleet_disjoint
from raven_mcs.data.manifest import verify_data_manifest
from raven_mcs.data.pipeline import dataset_paths
from raven_mcs.data.schema import (
    normalize_atomic_units,
    normalize_client_measurements,
)
from raven_mcs.data.split import assert_split_no_overlap, assert_time_monotonic
from raven_mcs.utils.serialization import dump_json, load_json, load_yaml

PAPER_DATASETS = ("sensorscope", "uair", "traffic", "tdrive_speed")


def _check_dataset(dataset: str, data_root: Path) -> dict:
    paths = dataset_paths(data_root, dataset)
    result: dict = {
        "dataset": dataset,
        "passed": True,
        "errors": [],
        "warnings": [],
        "checks": {},
    }

    def fail(message: str) -> None:
        result["passed"] = False
        result["errors"].append(message)

    if not paths.manifest.exists():
        fail(f"Missing frozen manifest: {paths.manifest}")
        return result
    if not (paths.processed / "atomic_units.parquet").exists():
        fail("Missing processed atomic_units.parquet")
        return result
    if not (paths.processed / "client_measurements.parquet").exists():
        fail("Missing processed client_measurements.parquet")
        return result

    manifest_errors = verify_data_manifest(
        paths.manifest,
        raw_root=paths.raw,
        interim_root=paths.interim,
        processed_root=paths.processed,
    )
    result["checks"]["manifest"] = "PASS" if not manifest_errors else "FAIL"
    for error in manifest_errors:
        fail(error)

    atomic = normalize_atomic_units(
        pd.read_parquet(paths.processed / "atomic_units.parquet")
    )
    clients = normalize_client_measurements(
        pd.read_parquet(paths.processed / "client_measurements.parquet")
    )
    try:
        assert_split_no_overlap(atomic)
        assert_time_monotonic(atomic)
        result["checks"]["split_time"] = "PASS"
    except Exception as exc:  # noqa: BLE001
        result["checks"]["split_time"] = "FAIL"
        fail(str(exc))

    target_ids_path = paths.interim / "target_source_trace_ids.parquet"
    if target_ids_path.exists():
        target_ids = set(
            pd.read_parquet(target_ids_path)["source_trace_id"].astype(str)
        )
    else:
        target_ids = {f"target::{unit}" for unit in atomic["unit_id"].astype(str)}
        result["warnings"].append("target_source_trace_ids.parquet missing; inferred")

    try:
        assert_record_sources_disjoint(target_ids, clients["source_trace_id"].astype(str))
        result["checks"]["source_disjoint"] = "PASS"
    except Exception as exc:  # noqa: BLE001
        result["checks"]["source_disjoint"] = "FAIL"
        fail(str(exc))

    scaling_path = paths.interim / "scaling.json"
    if scaling_path.exists():
        try:
            scaling = load_json(scaling_path)
            stats = {
                item["column"]: item for item in scaling.get("statistics", [])
            }
            if scaling.get("fitted_split") != "train" or "target_value" not in stats:
                raise ValueError("scaling.json missing train/target_value stats")
            train_mask = atomic["split"].astype(str) == "train"
            train_mean = float(atomic.loc[train_mask, "target_value"].mean())
            stored = float(stats["target_value"]["mean"])
            if abs(train_mean - stored) > 1e-5:
                fail(
                    f"Scaling stats not train-only/coherent: "
                    f"train_mean={train_mean} stored={stored}"
                )
                result["checks"]["train_only_scaling"] = "FAIL"
            else:
                result["checks"]["train_only_scaling"] = "PASS"
        except Exception as exc:  # noqa: BLE001
            result["checks"]["train_only_scaling"] = "FAIL"
            fail(f"Scaling check failed: {exc}")
    else:
        result["checks"]["train_only_scaling"] = "FAIL"
        fail("Missing interim/scaling.json")

    metadata_path = paths.interim / "metadata.json"
    metadata: DatasetMetadata | None = None
    if metadata_path.exists():
        meta_dict = load_json(metadata_path)
        try:
            if isinstance(meta_dict.get("filtering_rules"), list):
                meta_dict["filtering_rules"] = tuple(meta_dict["filtering_rules"])
            if isinstance(meta_dict.get("notes"), list):
                meta_dict["notes"] = tuple(meta_dict["notes"])
            metadata = DatasetMetadata(**meta_dict)
            metadata.validate()
            result["checks"]["metadata"] = "PASS"
        except Exception as exc:  # noqa: BLE001
            result["checks"]["metadata"] = "FAIL"
            fail(str(exc))
    else:
        result["checks"]["metadata"] = "FAIL"
        fail("Missing interim/metadata.json")

    if dataset == "tdrive_speed":
        fleet_path = paths.interim / "fleet_assignments.parquet"
        if not fleet_path.exists():
            fail("Missing fleet_assignments.parquet for tdrive_speed")
            result["checks"]["fleet_disjoint"] = "FAIL"
        else:
            try:
                assert_fleet_disjoint(pd.read_parquet(fleet_path))
                result["checks"]["fleet_disjoint"] = "PASS"
            except Exception as exc:  # noqa: BLE001
                result["checks"]["fleet_disjoint"] = "FAIL"
                fail(str(exc))

    if dataset == "traffic":
        cfg = load_yaml(_ROOT / "configs" / "dataset" / "traffic.yaml")
        hard_s = int(cfg["matrix"]["hard_floor_stations"])
        hard_h = int(cfg["matrix"]["hard_floor_hours"])
        n_s = int(atomic["spatial_id"].nunique())
        n_h = int(atomic["absolute_time"].nunique())
        quality = paths.raw / "station_quality_report.csv"
        if not quality.exists():
            fail("Missing station_quality_report.csv")
            result["checks"]["traffic_floor"] = "FAIL"
        elif n_s < hard_s or n_h < hard_h:
            fail(f"Traffic hard floor unmet: got {n_s}×{n_h}, need >={hard_s}×{hard_h}")
            result["checks"]["traffic_floor"] = "FAIL"
        else:
            result["checks"]["traffic_floor"] = "PASS"
        result["checks"]["traffic_shape"] = {"stations": n_s, "hours": n_h}

    # Bundle-level audit for schema/anomaly coherence.
    if metadata is not None:
        anomaly_path = paths.interim / "physical_anomalies.parquet"
        anomalies = (
            pd.read_parquet(anomaly_path)
            if anomaly_path.exists()
            else pd.DataFrame(columns=["source_trace_id", "rule", "action", "value"])
        )
        bundle = ProcessedBundle(
            atomic_units=atomic,
            client_measurements=clients,
            metadata=metadata,
            target_source_trace_ids=target_ids,
            anomaly_records=anomalies,
        )
        audit = audit_processed_bundle(bundle)
        result["checks"]["bundle_audit"] = "PASS" if audit.passed else "FAIL"
        if not audit.passed:
            for error in audit.errors:
                fail(error)

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        help="Dataset name; repeatable. Default: all paper datasets with manifests.",
    )
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/audits"))
    args = parser.parse_args(argv)

    datasets = args.datasets or [
        name
        for name in PAPER_DATASETS
        if (args.data_root / "manifests" / f"{name}_manifest.json").exists()
    ]
    if not datasets:
        print("No frozen paper datasets found to check")
        return 1

    reports = []
    overall = True
    for dataset in datasets:
        report = _check_dataset(dataset, args.data_root)
        reports.append(report)
        overall = overall and report["passed"]
        status = "PASS" if report["passed"] else "FAIL"
        print(f"G0 {dataset}: {status}")
        for error in report["errors"]:
            print(f"  ERROR: {error}")
        for warning in report["warnings"]:
            print(f"  WARN: {warning}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "g0_data_check.json"
    dump_json({"passed": overall, "datasets": reports}, out)
    print(f"report={out}")
    print(f"g0_overall={'PASS' if overall else 'FAIL'}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
