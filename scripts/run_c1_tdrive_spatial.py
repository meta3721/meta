#!/usr/bin/env python3
"""C1-KILL: T-Drive ranking under a frozen 4-quadrant public target.

Read post_review/C1_kill_tdrive_spatial/C1_KILL_INSTRUCTION.md.
Does not edit the manuscript until AUDIT c1_kill=true.
Does not overwrite tdrive_protocol_seal_r1/.
Does not mix into Table II. Gate is unused.
"""

from __future__ import annotations

import argparse
import gc
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from math import erf
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from raven_mcs.data.base import DatasetMetadata  # noqa: E402
from raven_mcs.data.processed_dataset import ProcessedDataset  # noqa: E402
from raven_mcs.e3.real_runner.generator_r3 import build_joint_pi_opp  # noqa: E402
from raven_mcs.e3.real_runner.runner import _mu_weights_for_test, _predict  # noqa: E402
from raven_mcs.e3.target_pair.pair_state_v4 import (  # noqa: E402
    METHODS_REQUIRE_ALPHA,
    METHODS_REQUIRE_ATOMIC_W,
    bind_alpha_by_client,
    bind_w_by_unit,
)
from raven_mcs.metrics.accuracy import mae_mu, rmse_mu  # noqa: E402
from raven_mcs.metrics.distribution import delta_c_s, delta_group  # noqa: E402
from raven_mcs.simulation.event_trace import freeze_event_trace, load_event_trace  # noqa: E402
from raven_mcs.tdrive_protocol_seal_r1.constants import LOCAL_STEPS  # noqa: E402
from raven_mcs.tdrive_protocol_seal_r1.eventtrace_generator import (  # noqa: E402
    generate_tdrive_complete_aligned_eventtrace,
)
from raven_mcs.propensity.usable import deadline_slack_pre  # noqa: E402
from raven_mcs.training.window_runner import build_full_runner  # noqa: E402
from raven_mcs.utils.serialization import dump_json  # noqa: E402

SPEC_PATH = ROOT / "post_review" / "C1_kill_tdrive_spatial" / "TARGET_SPEC.json"
OUT = ROOT / "results_c1_kill" / "round_v1"
TRACE_ROOT = ROOT / "artifacts" / "e3_c1_tdrive_spatial_eventtraces_v1"
PYTHON = ROOT / ".venv_new" / "Scripts" / "python.exe"
CANARY_SEED = 31001
MICRO_SEED = 31999
FORMAL_SEEDS = list(range(31001, 31011))
REGION_ORDER = ("region0", "region1", "region2", "region3")
H_ORDER = REGION_ORDER
SHARED_METHODS = ("fedavg_window", "twostage_hajek", "fedau_window", "obsuse_window")
REQUIRE_ALPHA = set(METHODS_REQUIRE_ALPHA) | {"raven_wo_design", "raven"}
REQUIRE_W = set(METHODS_REQUIRE_ATOMIC_W) | {"raven_wo_design"}


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "UNKNOWN"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(line: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "EXECUTION_LOG.md"
    if not path.is_file():
        path.write_text("# C1-KILL T-Drive spatial execution log\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"- { _now() } {line}\n")
    print(line, flush=True)


def load_spec() -> dict[str, Any]:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    if spec.get("status") != "LOCKED":
        raise SystemExit("TARGET_SPEC.json is not LOCKED")
    if spec.get("chosen_option") != "TD_SPATIAL_4QUAD":
        raise SystemExit("this runner only implements TD_SPATIAL_4QUAD")
    return spec


def load_freeze() -> dict[str, Any]:
    path = OUT / "C1_SCD_FREEZE.json"
    if not path.is_file():
        raise FileNotFoundError("C1_SCD_FREEZE.json missing; run --stage phi first")
    return json.loads(path.read_text(encoding="utf-8"))


def mandatory_methods(freeze: dict[str, Any]) -> list[str]:
    methods = list(SHARED_METHODS)
    scd = str(freeze["scd_method"])
    methods.append(scd)
    if bool(freeze.get("train_full_design_extra")) and "raven" not in methods:
        methods.append("raven")
    return methods


def _region_map(atomic: pd.DataFrame) -> tuple[dict[str, str], dict[str, Any]]:
    sid = atomic["spatial_id"].astype(str)
    xy = sid.str.extract(r"g(\d+)_(\d+)", expand=True)
    tmp = pd.DataFrame(
        {
            "spatial_id": sid,
            "gx": xy[0].astype(int),
            "gy": xy[1].astype(int),
        }
    )
    cells = tmp.drop_duplicates("spatial_id")
    mx = float(cells["gx"].median())
    my = float(cells["gy"].median())
    mapping: dict[str, str] = {}
    counts = {r: 0 for r in REGION_ORDER}
    for r in cells.itertuples(index=False):
        rid = "region%d" % ((int(r.gx >= mx) << 1) + int(r.gy >= my))
        mapping[str(r.spatial_id)] = rid
        counts[rid] += 1
    meta = {
        "median_gx": mx,
        "median_gy": my,
        "n_cells": int(len(cells)),
        "counts": counts,
        "used_y": False,
        "rule": "region = (gx>=median)<<1 | (gy>=median); medians over all cells",
    }
    return mapping, meta


def remap_atomic(atomic: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    out = atomic.copy()
    out["spatial_id"] = out["spatial_id"].astype(str)
    out["region"] = out["spatial_id"].map(mapping)
    if out["region"].isna().any():
        raise RuntimeError("spatial_id missing region map")
    parts = out["opportunity_stratum"].astype(str).str.split("::", expand=True)
    if parts.shape[1] < 3:
        raise RuntimeError("opportunity_stratum is not cell::block::day")
    out["opportunity_stratum"] = (
        out["region"] + "::" + parts[1].astype(str) + "::" + parts[2].astype(str)
    )
    out["target_group"] = out["region"]
    return out


def _load_raw_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    atomic = pd.read_parquet(ROOT / "data/processed/tdrive_speed/atomic_units.parquet")
    meas = pd.read_parquet(ROOT / "data/processed/tdrive_speed/client_measurements.parquet")
    mapping, meta = _region_map(atomic)
    atomic = remap_atomic(atomic, mapping)
    dump_json(meta, OUT / "C1_REGION_MAP.json")
    return atomic, meas


class TDriveSpatialE3Dataset(ProcessedDataset):
    """T-Drive with 4-quadrant target_group. Does not overwrite processed hashes."""

    def __init__(self, root: Path, atomic: pd.DataFrame, meas: pd.DataFrame) -> None:
        root = Path(root)
        metadata = DatasetMetadata(
            dataset="tdrive_spatial_h",
            target_name="speed",
            target_unit="km_per_h",
            spatial_unit="grid_cell_500m",
            time_unit="30min",
            source_name="Microsoft Research T-Drive trajectory sample",
            source_url="https://www.microsoft.com/en-us/research/publication/t-drive-trajectory-data-sample/",
            raw_license="microsoft-research-license",
            filtering_rules=(
                "Drop speeds <5 or >120 km/h",
                "Same vehicle cannot construct both target and client input",
                "h(i)=4 grid quadrants frozen without Y",
            ),
        )
        metadata.validate()
        staging = root / "artifacts/e3_c1_tdrive_spatial_eventtraces_v1/_dataset_staging"
        staging.mkdir(parents=True, exist_ok=True)
        atomic_out = staging / "atomic_units.parquet"
        client_out = staging / "client_measurements.parquet"
        keep = [
            c
            for c in atomic.columns
            if c in {
                "unit_id",
                "spatial_id",
                "absolute_time",
                "time_index",
                "target_value",
                "split",
                "target_group",
                "opportunity_stratum",
                "public_features",
                "support_flag",
                "is_warmup",
            }
        ]
        atomic[keep].to_parquet(atomic_out, index=False)
        meas.to_parquet(client_out, index=False)
        super().__init__(staging, metadata)
        mean = float(self.target_mean)
        std = float(self.target_std) if float(self.target_std) > 0 else 1.0
        self._client_df = self._client_df.copy()
        self._client_df["potential_measurement"] = (
            self._client_df["potential_measurement"].astype(float) - mean
        ) / std
        self._atomic_df = self._atomic_df.copy()
        self._atomic_df["target_value"] = (
            self._atomic_df["target_value"].astype(float) - mean
        ) / std
        cid = self._client_df["client_id"].astype(str).to_numpy()
        uid = self._client_df["unit_id"].astype(str).to_numpy()
        val = self._client_df["potential_measurement"].astype(float).to_numpy()
        self._measurement_index = {
            (str(c), str(u)): float(v) for c, u, v in zip(cid, uid, val)
        }
        self._standardized = True
        self._scaler_mean = mean
        self._scaler_std = std


def load_mu(atomic: pd.DataFrame) -> np.ndarray:
    test = atomic.loc[atomic["split"].astype(str) == "test"]
    shares = test["region"].value_counts(normalize=True)
    mu = np.asarray([float(shares.get(r, 0.0)) for r in REGION_ORDER], dtype=np.float64)
    if abs(float(mu.sum()) - 1.0) > 1e-12:
        raise RuntimeError(f"mu does not sum to 1: {mu}")
    if np.any(mu <= 0):
        raise RuntimeError(f"empty region in test mu: {mu}")
    return mu


def stage_phi() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = load_spec()
    atomic, _meas = _load_raw_tables()
    train = atomic.loc[atomic["split"].astype(str) == "train"].drop_duplicates("unit_id")
    mu = load_mu(atomic)
    mu_map = {r: float(v) for r, v in zip(REGION_ORDER, mu)}
    pi_i = train["region"].map(mu_map).astype(float)
    n = int(len(train))
    zeros = int((pi_i <= 0.0).sum())
    phi = zeros / n if n else float("nan")
    design_on = bool(zeros == 0)
    scd = "raven" if design_on else "raven_wo_design"
    freeze = {
        "experiment_id": "C1-KILL-TD-SPATIAL",
        "phi_definition": "phi_train_unit",
        "phi_train_unit": float(phi),
        "n_train_zero": zeros,
        "n_train_units": n,
        "rule": "Design_ON iff phi_train_unit == 0",
        "design_on": design_on,
        "scd_method": scd,
        "full_design_diagnostic_method": "raven",
        "train_full_design_extra": (not design_on),
        "gate_unused": True,
        "used_y_or_rmse": False,
        "h_definition": spec["h_definition"],
        "mu": mu_map,
        "frozen_utc": _now(),
        "note": "Frozen from region mu on train units. Not from labels or residuals.",
        "git_commit": _git_commit(),
    }
    dump_json(freeze, OUT / "C1_SCD_FREEZE.json")
    dump_json(
        {
            "copied_from": "C1_SCD_FREEZE.json",
            "design_on": design_on,
            "phi_train_unit": float(phi),
            "scd_method": scd,
            "used_y_or_rmse": False,
        },
        OUT / "GO.json",
    )
    (OUT / "tables").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "dataset": "tdrive_spatial_h",
                "h_definition": spec["h_definition"],
                "n_train_units": n,
                "n_train_zero": zeros,
                "phi_train_unit": float(phi),
                "design_on": design_on,
                "scd_method": scd,
            }
        ]
    ).to_csv(OUT / "tables" / "C1_PHI.csv", index=False)
    shutil.copyfile(SPEC_PATH, OUT / "TARGET_SPEC.json")
    _log(f"PHI frozen design_on={design_on} phi={phi} {zeros}/{n} scd={scd}")
    return freeze


def stage_generate(*, seeds: list[int], force: bool) -> dict[str, Any]:
    load_freeze()
    TRACE_ROOT.mkdir(parents=True, exist_ok=True)
    atomic, meas = _load_raw_tables()
    rows: list[dict[str, Any]] = []
    for seed in seeds:
        out = TRACE_ROOT / "tdrive_spatial_h" / f"seed{seed}" / "training_eventtrace"
        ident_path = out / "trace_identity.json"
        if ident_path.is_file() and not force:
            ident = json.loads(ident_path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "status": "REUSED",
                    "seed": int(seed),
                    "trace_hash": ident.get("trace_hash"),
                    "path": str(out.relative_to(ROOT)).replace("\\", "/"),
                }
            )
            _log(f"REUSED trace seed{seed}")
            continue
        if out.exists() and force:
            shutil.rmtree(out, ignore_errors=True)
        _log(f"START trace seed{seed}")
        t0 = time.perf_counter()
        if seed == CANARY_SEED:
            trace_a, _, audit = generate_tdrive_complete_aligned_eventtrace(
                atomic=atomic,
                measurements=meas,
                seed=int(seed),
                dataset="tdrive_spatial_h",
                method="raven",
            )
            trace_b, _, _ = generate_tdrive_complete_aligned_eventtrace(
                atomic=atomic,
                measurements=meas,
                seed=int(seed),
                dataset="tdrive_spatial_h",
                method="fedavg_window",
            )
            if not trace_a.events.equals(trace_b.events):
                raise RuntimeError("EventTrace hash/content depends on method name")
            ident = freeze_event_trace(trace_a, out)
            audit["method_independence_canary"] = True
        else:
            trace, _, audit = generate_tdrive_complete_aligned_eventtrace(
                atomic=atomic,
                measurements=meas,
                seed=int(seed),
                dataset="tdrive_spatial_h",
                method=None,
            )
            ident = freeze_event_trace(trace, out)
        dump_json(audit, out.parent / "generation_meta.json")
        row = {
            "status": "CREATED",
            "seed": int(seed),
            "trace_hash": ident.get("trace_hash"),
            "path": str(out.relative_to(ROOT)).replace("\\", "/"),
            "n_windows": audit.get("n_windows"),
            "n_event_rows": audit.get("n_event_rows"),
            "n_clients": audit.get("n_clients"),
            "elapsed_sec": float(time.perf_counter() - t0),
        }
        rows.append(row)
        _log(
            f"DONE trace seed{seed} windows={row['n_windows']} rows={row['n_event_rows']} "
            f"hash={row['trace_hash']}"
        )
    manifest = {
        "experiment_id": "C1-KILL-TD-SPATIAL",
        "trace_root": "artifacts/e3_c1_tdrive_spatial_eventtraces_v1/",
        "r_layer": "REAL_FROM_TDRIVE",
        "o_layer": "CONTROLLED_EXPERIMENTAL p_obs=0.35",
        "u_layer": "CONTROLLED_EXPERIMENTAL compute_usable_r3 s_max=5",
        "gate_unused": True,
        "rows": rows,
        "git_commit": _git_commit(),
        "generated_utc": _now(),
    }
    dump_json(manifest, OUT / "C1_TRACE_MANIFEST.json")
    return manifest


def _device() -> str:
    # Feature indices stay on CPU in extract_features; do not mix CUDA embeddings.
    return "cpu"


class ZeroMissingPi(dict):
    """Store positive (k,s) mass only. Missing keys read as 0; items() stays sparse.

    WindowRunner zeta lookup requires keys to exist. Certificate code iterates
    items() and must not see millions of padded zeros. Gate is unused on T-Drive.
    """

    def __contains__(self, key: object) -> bool:
        return True

    def __getitem__(self, key: object) -> float:
        return float(dict.get(self, key, 0.0))

    def get(self, key: object, default: float = 0.0) -> float:
        return float(dict.get(self, key, default))


def _skip_unused_gate(self, window_id: int = -1):
    """T-Drive: Gate unused. Do not scan pi_target for coverage certificates."""
    self._last_cert_diagnostics = {}
    self._last_gate_to_design = {}
    mode = str(getattr(self.policy, "gate_mode", "policy") or "policy")
    if mode == "always_on":
        return 1, {}, None, {}
    if mode == "always_off":
        return 0, {}, "OFF_MODE_NO_DESIGN", {}
    if bool(getattr(self.policy, "uses_design_ratio", False)):
        return 1, {}, None, {}
    return 0, {}, "OFF_MODE_NO_DESIGN", {}


def build_vehicle_pi_target(
    atomic: pd.DataFrame, measurements: pd.DataFrame
) -> tuple[dict[tuple[str, str], float], dict[str, Any]]:
    atomic = atomic.copy()
    atomic["unit_id"] = atomic["unit_id"].astype(str)
    atomic["opportunity_stratum"] = atomic["opportunity_stratum"].astype(str)
    test = atomic.loc[atomic["split"].astype(str) == "test"]
    unit_s = dict(zip(test["unit_id"], test["opportunity_stratum"]))
    n_test = int(len(unit_s))
    if n_test <= 0:
        raise RuntimeError("empty test units")
    lambda_s = test.groupby("opportunity_stratum").size() / float(n_test)
    meas = measurements.copy()
    meas["unit_id"] = meas["unit_id"].astype(str)
    meas["client_id"] = meas["client_id"].astype(str)
    meas = meas.loc[meas["unit_id"].isin(unit_s)]
    meas["s"] = meas["unit_id"].map(unit_s)
    counts = meas.groupby(["client_id", "s"]).size().rename("n").reset_index()
    tot = counts.groupby("s")["n"].transform("sum")
    counts["pi"] = counts["s"].map(lambda_s).fillna(0.0) * (counts["n"] / tot)
    pi: dict[tuple[str, str], float] = {
        (str(r.client_id), str(r.s)): float(r.pi)
        for r in counts.itertuples(index=False)
        if float(r.pi) > 0.0
    }
    covered = set(counts["s"].astype(str))
    leftover = {
        str(s): float(v) for s, v in lambda_s.items() if str(s) not in covered and float(v) > 0.0
    }
    leftover_mass = float(sum(leftover.values()))
    total = float(sum(pi.values()))
    if total <= 0:
        raise RuntimeError("empty positive vehicle pi_target")
    pi = {k: v / total for k, v in pi.items()}
    meta = {
        "n_positive_keys": int(len(pi)),
        "leftover_n_strata": int(len(leftover)),
        "leftover_mass_before_renorm": leftover_mass,
        "renormalized": True,
        "no_cartesian_pad": True,
    }
    return pi, meta


def build_vehicle_pi_opp(
    atomic: pd.DataFrame, measurements: pd.DataFrame
) -> dict[tuple[str, str], float]:
    atomic = atomic.copy()
    atomic["unit_id"] = atomic["unit_id"].astype(str)
    atomic["opportunity_stratum"] = atomic["opportunity_stratum"].astype(str)
    train_units = set(
        atomic.loc[atomic["split"].astype(str) == "train", "unit_id"].astype(str)
    )
    unit_s = dict(zip(atomic["unit_id"].astype(str), atomic["opportunity_stratum"].astype(str)))
    meas = measurements.copy()
    meas["unit_id"] = meas["unit_id"].astype(str)
    meas["client_id"] = meas["client_id"].astype(str)
    meas = meas.loc[meas["unit_id"].isin(train_units)]
    strata_by_client: dict[str, list[str]] = {}
    for r in meas.itertuples(index=False):
        strata_by_client.setdefault(str(r.client_id), []).append(unit_s[str(r.unit_id)])
    for cid, vals in list(strata_by_client.items()):
        strata_by_client[cid] = sorted(set(vals))
    clients = sorted(strata_by_client)
    return build_joint_pi_opp(clients, strata_by_client)


def _wrmse_block(y_true: np.ndarray, y_pred: np.ndarray, mask: np.ndarray, mu_w: np.ndarray) -> float:
    if not np.any(mask):
        return float("nan")
    ww = mu_w[mask].copy()
    s = float(ww.sum())
    ww = ww / s if s > 0 else np.full(int(mask.sum()), 1.0 / int(mask.sum()))
    err = y_true[mask] - y_pred[mask]
    return float(np.sqrt(np.sum(ww * err * err)))


def _install_fast_logistic(est: Any, *, n_features: int, kind: str) -> None:
    """Same lagged L2-logistic SGD, without rebuilding X from a Python list."""
    from scipy.special import expit as sigmoid

    est._n = 0
    est._X = np.empty((0, int(n_features)), dtype=np.float64)
    est._y = np.empty((0,), dtype=np.float64)

    def _grow(extra: int) -> None:
        need = int(est._n) + int(extra)
        cap = int(est._X.shape[0])
        if need <= cap:
            return
        new_cap = 1024 if cap == 0 else cap * 2
        while new_cap < need:
            new_cap *= 2
        x2 = np.empty((new_cap, int(n_features)), dtype=np.float64)
        y2 = np.empty((new_cap,), dtype=np.float64)
        n = int(est._n)
        if n:
            x2[:n] = est._X[:n]
            y2[:n] = est._y[:n]
        est._X = x2
        est._y = y2

    def _step() -> None:
        n = int(est._n)
        if n < int(est.min_samples):
            return
        x_mat = est._X[:n]
        y_vec = est._y[:n]
        logits = x_mat @ est.weights
        probs = sigmoid(logits) if kind == "p" else (1.0 / (1.0 + np.exp(-logits)))
        grad = x_mat.T @ (probs - y_vec) / n + float(est.l2) * est.weights
        est.weights = est.weights - 0.5 * grad

    def update_records_after_completion(features, outcomes) -> None:
        x_batch = np.asarray(features, dtype=np.float64)
        y_batch = np.asarray(outcomes, dtype=np.float64).reshape(-1)
        if x_batch.ndim != 2 or x_batch.shape[1] != int(n_features):
            raise ValueError("record feature dimension mismatch")
        if x_batch.shape[0] != len(y_batch):
            raise ValueError("record features/outcomes length mismatch")
        est._previous_weights = est.weights.copy()
        _grow(len(y_batch))
        n0 = int(est._n)
        n1 = n0 + len(y_batch)
        est._X[n0:n1] = x_batch
        est._y[n0:n1] = np.clip(y_batch, 0.0, 1.0)
        est._n = n1
        _step()

    def update_lagged(features, usable) -> None:
        x = np.asarray(features, dtype=np.float64).reshape(-1)
        if x.shape[0] != int(n_features):
            raise ValueError("feature dimension mismatch")
        _grow(1)
        n0 = int(est._n)
        est._X[n0] = x
        est._y[n0] = float(usable)
        est._n = n0 + 1
        _step()

    def predict(features) -> float:
        x = np.asarray(features, dtype=np.float64).reshape(-1)
        if x.shape[0] != int(n_features):
            raise ValueError("feature dimension mismatch")
        if int(est._n) < int(est.min_samples):
            raw = float(est.prior_rate)
        else:
            logit = float(est.weights @ x)
            raw = float(sigmoid(logit) if kind == "p" else (1.0 / (1.0 + np.exp(-logit))))
        if kind == "q":
            return float(np.clip(raw, float(est.q_min), float(est.q_max)))
        return float(raw)

    def predict_batch(features_matrix) -> np.ndarray:
        x_mat = np.asarray(features_matrix, dtype=np.float64)
        if x_mat.ndim == 1:
            x_mat = x_mat.reshape(1, -1)
        if int(est._n) < int(est.min_samples):
            return np.full(x_mat.shape[0], float(est.prior_rate), dtype=np.float64)
        logits = x_mat @ est.weights
        probs = sigmoid(logits) if kind == "p" else (1.0 / (1.0 + np.exp(-logits)))
        if kind == "q":
            return np.clip(probs, float(est.q_min), float(est.q_max))
        return np.asarray(probs, dtype=np.float64)

    est.update_records_after_completion = update_records_after_completion
    est.update_lagged = update_lagged
    est.predict = predict
    est.predict_batch = predict_batch


def _delta_cs_from_contrib(
    contrib: dict[str, float],
    s_r: float,
    pi_target: dict[tuple[str, str], float],
) -> dict[str, Any]:
    pi_tar = {f"{k}::{s}": float(v) for (k, s), v in pi_target.items()}
    denom = float(s_r) if s_r > 0 else 1.0
    keys = sorted(set(list(contrib.keys()) + list(pi_tar.keys())))
    pi_hat = np.asarray([contrib.get(k, 0.0) / denom for k in keys], dtype=np.float64)
    pi_t = np.asarray([pi_tar.get(k, 0.0) for k in keys], dtype=np.float64)
    if float(pi_hat.sum()) > 0:
        pi_hat = pi_hat / float(pi_hat.sum())
    return {
        "Delta_c_s": float(delta_c_s(pi_hat, pi_t)),
        "pair_support_size": int(len(keys)),
        "overlap_size": int(len(set(contrib) & set(pi_tar))),
        "support": "vehicle_client x opportunity_stratum",
        "status": "OK",
    }


def accumulate_delta_cs_vehicle(
    *,
    window_metrics: list[Any],
    diagnostics: list[dict[str, Any]],
    atomic: pd.DataFrame,
    pi_target: dict[tuple[str, str], float],
    method: str,
) -> dict[str, Any]:
    unit_s = {
        str(r.unit_id): str(r.opportunity_stratum) for r in atomic.itertuples(index=False)
    }
    pi_tar = {f"{k}::{s}": float(v) for (k, s), v in pi_target.items()}
    contrib: dict[str, float] = {}
    s_r = 0.0
    for wm in window_metrics:
        if not bool(getattr(wm, "active", False)):
            continue
        s_r += 1.0
        if method in REQUIRE_ALPHA and not list(getattr(wm, "alpha", []) or []):
            raise RuntimeError(f"empty alpha for active window method={method}")
        alpha_map = bind_alpha_by_client(wm)
        win_diag = [d for d in diagnostics if int(d.get("window_id", -1)) == int(wm.window_id)]
        for d in win_diag:
            cid = str(d["client_id"])
            if cid not in alpha_map:
                continue
            a = float(alpha_map[cid])
            w_map = bind_w_by_unit(d, method=method if method in REQUIRE_W else method)
            for uid, w in w_map.items():
                sid = f"{cid}::{unit_s[str(uid)]}"
                contrib[sid] = contrib.get(sid, 0.0) + float(a * w)
    denom = float(s_r) if s_r > 0 else 1.0
    keys = sorted(set(list(contrib.keys()) + list(pi_tar.keys())))
    pi_hat = np.asarray([contrib.get(k, 0.0) / denom for k in keys], dtype=np.float64)
    pi_t = np.asarray([pi_tar.get(k, 0.0) for k in keys], dtype=np.float64)
    if float(pi_hat.sum()) > 0:
        pi_hat = pi_hat / float(pi_hat.sum())
    return {
        "Delta_c_s": float(delta_c_s(pi_hat, pi_t)),
        "pair_support_size": int(len(keys)),
        "overlap_size": int(len(set(contrib) & set(pi_tar))),
        "support": "vehicle_client x opportunity_stratum",
        "status": "OK",
    }


def train_one(
    *,
    ds,
    raw_atomic: pd.DataFrame,
    method: str,
    seed: int,
    pi_target: dict[tuple[str, str], float],
    pi_opp: dict[tuple[str, str], float],
    mu: np.ndarray,
    device: str,
) -> dict[str, Any]:
    run_dir = OUT / "runs" / "tdrive_spatial_h" / method / f"seed{seed}"
    marker = run_dir / "C1_ACCEPTED.json"
    if marker.is_file():
        prev = json.loads(marker.read_text(encoding="utf-8"))
        return {"status": "REUSED", **prev}
    et = TRACE_ROOT / "tdrive_spatial_h" / f"seed{seed}" / "training_eventtrace"
    if not (et / "events.parquet").is_file():
        raise FileNotFoundError(et)
    run_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    trace, identity = load_event_trace(et)
    if int(trace.metadata.num_windows) != 178:
        raise RuntimeError(f"expected 178 train windows, got {trace.metadata.num_windows}")
    runner = build_full_runner(
        trace,
        ds,
        method=method,
        n_groups=4,
        model_seed=int(seed),
        local_steps=int(LOCAL_STEPS),
        target_mu=mu,
        pi_target=pi_target,
        s_max=int(trace.metadata.s_max),
        device=device,
        use_coarse_time_groups=False,
        pi_opp_joint=pi_opp,
    )
    runner.pi_target = ZeroMissingPi(dict(runner.pi_target))
    runner.pi_opp_joint = ZeroMissingPi(dict(runner.pi_opp_joint))
    runner._decide_g_r = _skip_unused_gate.__get__(runner, type(runner))

    def _ckpt_no_deepcopy(version: int, runner=runner):
        if version not in runner.model_versions:
            raise RuntimeError(f"Checkpoint version {version} is unavailable")
        return runner.model_versions[version]

    runner._get_model_checkpoint = _ckpt_no_deepcopy
    if runner.obs_propensity is not None:
        _install_fast_logistic(runner.obs_propensity, n_features=3, kind="p")
    if runner.usable_propensity is not None:
        _install_fast_logistic(runner.usable_propensity, n_features=5, kind="q")
    orig_var = runner._update_variance_state

    def _lagged_light(window_slice, client_data, runner=runner):
        from collections import Counter

        use_p = bool(runner.policy.uses_observation_ipw)
        use_q = bool(runner.policy.uses_usable_ipw)
        opportunity_counts: Counter = Counter()
        for rec in window_slice.records:
            cid = rec.client_id
            runner._fedau_attempt_count[cid] = runner._fedau_attempt_count.get(cid, 0.0) + 1.0
            if int(rec.attempted) == 1 and int(rec.U) == 1:
                runner._fedau_usable_count[cid] = runner._fedau_usable_count.get(cid, 0.0) + 1.0
            opportunity_counts.update(
                (str(cid), str(s)) for s in rec.opportunity_strata
            )
            if cid not in client_data:
                continue
            if use_p and runner.obs_propensity is not None and len(rec.risk_set_unit_ids) > 0:
                features = np.asarray(
                    [
                        [
                            1.0,
                            runner._hour_block(stratum),
                            float(np.log1p(rec.planned_workload_pre)),
                        ]
                        for stratum in rec.opportunity_strata
                    ],
                    dtype=np.float64,
                )
                runner.obs_propensity.update_records_after_completion(features, rec.O)
                runner.p_model_version += 1
            if use_q and runner.usable_propensity is not None:
                q_features = np.array(
                    [
                        1.0,
                        float(rec.model_age),
                        0.0,
                        0.0,
                        deadline_slack_pre(rec.window_close_time, rec.registration_time),
                    ]
                )
                runner.usable_propensity.predict(q_features)
                if bool(rec.attempted == 1):
                    runner.usable_propensity.update_lagged(q_features, float(rec.U))
                    runner.q_model_version += 1
        est = runner.opportunity_estimator
        needs_opp = bool(
            runner.policy.uses_observation_ipw
            or runner.policy.uses_usable_ipw
            or runner.policy.uses_design_ratio
        )
        if est is not None and needs_opp:
            # EMA counts only. Do not append per-pair diagnostics (T-Drive
            # support is ~2e5 pairs; 178 windows would OOM a 16GB host).
            normalized = {
                (str(client), str(stratum)): float(count)
                for (client, stratum), count in opportunity_counts.items()
            }
            rho = float(est.forgetting)
            keys = set(est.counts) | set(normalized)
            for key in keys:
                old = float(est.counts.get(key, 0.0))
                current = float(normalized.get(key, 0.0))
                est.counts[key] = rho * old + current
            est.diagnostics = []
        runner.p_propensity_history.clear()
        runner.q_propensity_history.clear()
        runner.q_attempt_diagnostics.clear()
        return None

    def _var_light(local_updates, a_r_clients, orig_var=orig_var, runner=runner):
        if runner.policy.uses_variance_penalty:
            return orig_var(local_updates, a_r_clients)
        return None

    def _theta_hash_light(self=runner):
        if bool(getattr(self, "_tdrive_lowmem", False)):
            return "tdrive_lowmem"
        return orig_theta_hash()

    orig_theta_hash = runner._theta_hash
    runner._theta_hash = _theta_hash_light.__get__(runner, type(runner))
    runner._update_lagged_estimators = _lagged_light
    runner._update_variance_state = _var_light
    runner._tdrive_lowmem = True
    unit_s = {
        str(r.unit_id): str(r.opportunity_stratum)
        for r in raw_atomic.itertuples(index=False)
    }
    cs_contrib: dict[str, float] = {}
    cs_sr = 0.0
    nwin = int(trace.metadata.num_windows)
    orig_pw = runner._process_window
    vers_by_window: dict[int, set[int]] = {w: set() for w in range(nwin)}
    for w_id, v_id in zip(
        trace.events["window_id"].astype(int).tolist(),
        trace.events["downloaded_version"].astype(int).tolist(),
    ):
        if 0 <= int(w_id) < nwin:
            vers_by_window[int(w_id)].add(int(v_id))
    future_versions: dict[int, set[int]] = {}
    acc: set[int] = set()
    for w in range(nwin - 1, -1, -1):
        future_versions[w] = set(acc)
        acc |= vers_by_window[w]

    def _pw(window_id, events, orig_pw=orig_pw):
        t_w = time.perf_counter()
        out = orig_pw(window_id, events)
        nonlocal cs_sr
        if bool(getattr(out, "active", False)):
            if method in REQUIRE_ALPHA and not list(getattr(out, "alpha", []) or []):
                raise RuntimeError(f"empty alpha for active window method={method}")
            cs_sr += 1.0
            alpha_map = bind_alpha_by_client(out)
            wid_now = int(getattr(out, "window_id"))
            for d in runner.diagnostics:
                if int(d.get("window_id", -1)) != wid_now:
                    continue
                cid = str(d["client_id"])
                if cid not in alpha_map:
                    continue
                a = float(alpha_map[cid])
                w_map = bind_w_by_unit(
                    d, method=method if method in REQUIRE_W else method
                )
                for uid, w in w_map.items():
                    sid = f"{cid}::{unit_s[str(uid)]}"
                    cs_contrib[sid] = cs_contrib.get(sid, 0.0) + float(a * w)
        runner.diagnostics.clear()
        if runner.opportunity_estimator is not None:
            runner.opportunity_estimator.diagnostics = []
        hist = getattr(runner.aggregator, "diagnostics_history", None)
        if isinstance(hist, list):
            hist.clear()
        wid = int(window_id)
        needed = set(future_versions.get(wid, set()))
        needed.add(int(runner.clock.model_version))
        for ver in list(runner.model_versions):
            if int(ver) not in needed:
                del runner.model_versions[ver]
        if (wid + 1) % 20 == 0:
            gc.collect()
        _log(
            f"    window {wid+1}/{nwin} {method} seed{seed} "
            f"sec={time.perf_counter()-t_w:.1f} "
            f"ckpts={len(runner.model_versions)}"
        )
        (OUT / "SMOKE_HEARTBEAT.txt").write_text(
            f"{wid+1}/{nwin} {method} seed{seed}\n", encoding="utf-8"
        )
        return out

    runner._process_window = _pw
    try:
        window_metrics = runner.run()
    except Exception:
        err_path = run_dir / "C1_TRAIN_TRACEBACK.txt"
        import traceback

        err_path.write_text(traceback.format_exc(), encoding="utf-8")
        _log(f"TRAIN failed {method} seed{seed}; traceback {err_path}")
        raise
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    torch.save(runner.theta, run_dir / "checkpoints" / "final.pt")
    pred = _predict(runner, ds, split="test")
    mu_w = _mu_weights_for_test(pred, mu)
    rmse = float(rmse_mu(pred["y_pred"], pred["y_true"], mu_w)) if len(mu_w) else float("nan")
    mae = float(mae_mu(pred["y_pred"], pred["y_true"], mu_w)) if len(mu_w) else float("nan")
    gids = pred["groups"]
    wg_vals = [
        _wrmse_block(pred["y_true"], pred["y_pred"], gids == g, mu_w) for g in range(4)
    ]
    worst = float(np.nanmax(np.asarray(wg_vals, dtype=np.float64)))
    try:
        d_group = float(delta_group(runner.omega_bar(), mu))
    except Exception:
        d_group = float("nan")
    d_cs = _delta_cs_from_contrib(cs_contrib, cs_sr, pi_target)
    n_updates = sum(1 for wm in window_metrics if wm.active)
    accepted = {
        "dataset": "tdrive_spatial_h",
        "method": method,
        "seed": int(seed),
        "RMSE_mu": rmse,
        "MAE_mu": mae,
        "WorstGroupRMSE": worst,
        "WorstGroupRMSE_R0": wg_vals[0],
        "WorstGroupRMSE_R1": wg_vals[1],
        "WorstGroupRMSE_R2": wg_vals[2],
        "WorstGroupRMSE_R3": wg_vals[3],
        "Delta_group": d_group,
        "Delta_c_s": float(d_cs["Delta_c_s"]),
        "n_local_updates": int(n_updates),
        "n_windows": int(trace.metadata.num_windows),
        "eventtrace_hash": identity.get("trace_hash"),
        "path_status": "REAL_PATH_EXECUTED",
        "device": device,
        "runtime_seconds": float(time.perf_counter() - t0),
        "git_commit": _git_commit(),
    }
    dump_json(accepted, marker)
    dump_json(d_cs, run_dir / "delta_cs_vehicle.json")
    return {"status": "CREATED", **accepted}


def e3_schedule(freeze: dict[str, Any], seeds: list[int]) -> list[dict[str, Any]]:
    rows = []
    for seed in seeds:
        for method in mandatory_methods(freeze):
            rows.append({"dataset": "tdrive_spatial_h", "seed": int(seed), "method": method})
    return rows


def _append_ledger(row: dict[str, Any]) -> None:
    path = OUT / "C1_TRAIN_LEDGER.json"
    payload = {"rows": []}
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
    rows = list(payload.get("rows") or [])
    key = (row.get("dataset"), row.get("method"), row.get("seed"))
    rows = [r for r in rows if (r.get("dataset"), r.get("method"), r.get("seed")) != key]
    rows.append(row)
    dump_json({"rows": rows, "updated_utc": _now()}, path)


def stage_train(*, max_runs: int | None, smoke: bool) -> list[dict[str, Any]]:
    freeze = load_freeze()
    seeds = [CANARY_SEED] if smoke else list(FORMAL_SEEDS)
    schedule = e3_schedule(freeze, seeds)
    if smoke:
        schedule = [r for r in schedule if r["method"] == "fedavg_window" and r["seed"] == CANARY_SEED]
    if max_runs is not None:
        schedule = schedule[: int(max_runs)]
    device = _device()
    _log(f"TRAIN start n={len(schedule)} device={device} smoke={smoke}")
    raw_atomic, raw_meas = _load_raw_tables()
    ds = TDriveSpatialE3Dataset(ROOT, raw_atomic, raw_meas)
    mu = load_mu(raw_atomic)
    g2i = {str(g): i for g, i in ds._target_group_str_to_int.items()}
    if [g2i[h] for h in H_ORDER] != [0, 1, 2, 3] and sorted(g2i) != list(H_ORDER):
        # Align mu to dataset encoding order.
        mu_aligned = np.zeros(4, dtype=np.float64)
        mu_by_h = dict(zip(H_ORDER, mu))
        for h, idx in g2i.items():
            mu_aligned[int(idx)] = float(mu_by_h[h])
        mu = mu_aligned / float(mu_aligned.sum())
    pi_target, pi_meta = build_vehicle_pi_target(raw_atomic, raw_meas)
    pi_opp = build_vehicle_pi_opp(raw_atomic, raw_meas)
    dump_json(
        {
            "n_pi_target_keys": int(len(pi_target)),
            "n_pi_opp_keys": int(len(pi_opp)),
            "pi_target_meta": pi_meta,
            "mu": mu.tolist(),
            "h_encoding": ds._target_group_str_to_int,
            "scaler_mean": getattr(ds, "_scaler_mean", None),
            "scaler_std": getattr(ds, "_scaler_std", None),
            "num_spatial": int(ds.num_spatial),
            "num_groups": int(ds.num_groups),
            "gate_unused": True,
        },
        OUT / "C1_TRAIN_SETUP.json",
    )
    results = []
    for i, job in enumerate(schedule, 1):
        method = str(job["method"])
        seed = int(job["seed"])
        _log(f"[{i}/{len(schedule)}] TRAIN tdrive_spatial_h {method} seed{seed}")
        row = train_one(
            ds=ds,
            raw_atomic=raw_atomic,
            method=method,
            seed=seed,
            pi_target=pi_target,
            pi_opp=pi_opp,
            mu=mu,
            device=device,
        )
        _append_ledger(row)
        results.append(row)
        _log(
            f"  status={row.get('status')} path={row.get('path_status')} "
            f"RMSE_mu={row.get('RMSE_mu')} WorstGroupRMSE={row.get('WorstGroupRMSE')} "
            f"sec={row.get('runtime_seconds')}"
        )
        if smoke and row.get("path_status") != "REAL_PATH_EXECUTED" and row.get("status") != "REUSED":
            raise RuntimeError(f"smoke did not execute real path: {row}")
    return results


def _mean_std(vals: list[float], n_expected: int) -> tuple[str, str]:
    arr = np.asarray(vals, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size != n_expected:
        return "TBD", "TBD"
    return f"{float(arr.mean()):.10g}", f"{float(arr.std(ddof=1)):.10g}"


def _holm(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = np.argsort(pvals)
    adj = [1.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        raw = float(pvals[int(idx)]) * (m - rank)
        running = max(running, raw)
        adj[int(idx)] = min(1.0, running)
    return adj


def _paired_p(a: np.ndarray, b: np.ndarray) -> float:
    d = a - b
    se = float(d.std(ddof=1) / np.sqrt(d.size)) if d.size > 1 else 0.0
    if se <= 0:
        return 1.0
    t = float(d.mean() / se)
    return float(2.0 * (1.0 - 0.5 * (1.0 + erf(abs(t) / np.sqrt(2.0)))))


def stage_tables() -> dict[str, Any]:
    ledger = OUT / "C1_TRAIN_LEDGER.json"
    if not ledger.is_file():
        raise FileNotFoundError(ledger)
    rows = list(json.loads(ledger.read_text(encoding="utf-8")).get("rows") or [])
    freeze = load_freeze()
    spec = load_spec()
    methods = mandatory_methods(freeze)
    (OUT / "tables").mkdir(parents=True, exist_ok=True)
    e3_rows = []
    for r in rows:
        e3_rows.append(
            {
                "dataset": r.get("dataset"),
                "method": r.get("method"),
                "seed": r.get("seed"),
                "RMSE_mu": r.get("RMSE_mu"),
                "WorstGroupRMSE": r.get("WorstGroupRMSE"),
                "Delta_group": r.get("Delta_group"),
                "Delta_c_s": r.get("Delta_c_s"),
                "path_status": r.get("path_status"),
                "eventtrace_hash": r.get("eventtrace_hash"),
            }
        )
    pd.DataFrame(e3_rows).to_csv(OUT / "tables" / "C1_E3.csv", index=False)
    n_seeds = len({int(r["seed"]) for r in rows if r.get("seed") is not None})
    summary = []
    for method in methods:
        sub = [r for r in rows if r.get("method") == method]
        rec: dict[str, Any] = {"dataset": "tdrive_spatial_h", "method": method, "n": len(sub)}
        for src, dst in {
            "RMSE_mu": "rmse_mu",
            "WorstGroupRMSE": "worstgroup",
            "Delta_group": "delta_group",
            "Delta_c_s": "delta_cs",
        }.items():
            vals = [float(r[src]) for r in sub if r.get(src) is not None]
            mean_s, std_s = _mean_std(vals, n_seeds if n_seeds else 10)
            rec[f"{dst}_mean"] = mean_s
            rec[f"{dst}_std"] = std_s
        summary.append(rec)
    pd.DataFrame(summary).to_csv(OUT / "tables" / "C1_E3_SUMMARY.csv", index=False)

    scd = str(freeze["scd_method"])
    paired_rows = []
    scd_by = {int(r["seed"]): r for r in rows if r.get("method") == scd}
    for comp in ("fedau_window", "obsuse_window", "fedavg_window"):
        other = {int(r["seed"]): r for r in rows if r.get("method") == comp}
        common = sorted(set(scd_by) & set(other))
        rec = {"scd_method": scd, "comparator": comp, "n_paired": len(common)}
        if len(common) >= 2:
            for metric in ("RMSE_mu", "WorstGroupRMSE", "Delta_group", "Delta_c_s"):
                a = np.asarray([float(scd_by[s][metric]) for s in common], dtype=np.float64)
                b = np.asarray([float(other[s][metric]) for s in common], dtype=np.float64)
                rel = (a - b) / np.where(np.abs(b) > 0, b, np.nan)
                rec[f"{metric}_paired_mean_diff"] = float((a - b).mean())
                rec[f"{metric}_paired_rel_mean"] = float(np.nanmean(rel))
                rec[f"{metric}_p_unadj"] = _paired_p(a, b)
            rec["worstgroup_within_0p5pct_tolerance"] = bool(
                rec.get("WorstGroupRMSE_paired_rel_mean", 1.0) <= 0.005
            )
        paired_rows.append(rec)
    pvals = [float(r["RMSE_mu_p_unadj"]) for r in paired_rows if "RMSE_mu_p_unadj" in r]
    if pvals:
        adj = _holm(pvals)
        for r, p in zip([x for x in paired_rows if "RMSE_mu_p_unadj" in x], adj):
            r["RMSE_mu_p_holm"] = float(p)
    dump_json({"rows": paired_rows, "scd_method": scd}, OUT / "C1_PAIRED.json")
    pd.DataFrame(paired_rows).to_csv(OUT / "tables" / "C1_E3_PAIRED.csv", index=False)
    by_comp = {r["comparator"]: r for r in paired_rows}
    fedau = by_comp.get("fedau_window", {})
    obsuse = by_comp.get("obsuse_window", {})
    wg_kill = bool(
        float(fedau.get("WorstGroupRMSE_paired_rel_mean", 1.0)) <= -0.005
        and float(obsuse.get("WorstGroupRMSE_paired_rel_mean", 1.0)) <= -0.005
    )
    rmse_kill = bool(
        float(fedau.get("RMSE_mu_paired_rel_mean", 1.0)) <= -0.005
        and float(obsuse.get("RMSE_mu_paired_rel_mean", 1.0)) <= -0.005
    )
    hashes = {}
    for r in rows:
        if r.get("seed") is not None:
            hashes.setdefault(int(r["seed"]), set()).add(r.get("eventtrace_hash"))
    hash_ok = all(len(v) == 1 for v in hashes.values()) if hashes else False
    expected = {(m, s) for s in FORMAL_SEEDS for m in methods}
    have = {
        (r.get("method"), int(r["seed"]))
        for r in rows
        if r.get("path_status") == "REAL_PATH_EXECUTED" or r.get("status") == "REUSED"
    }
    complete = expected <= have
    go = json.loads((OUT / "GO.json").read_text(encoding="utf-8"))
    audit = {
        "status": "PASS" if complete and hash_ok else "INCOMPLETE",
        "c1_kill": bool(complete and hash_ok and (wg_kill or rmse_kill)),
        "c1_kill_worstgroup": wg_kill,
        "c1_kill_rmse_mu": rmse_kill,
        "c1_kill_rule": spec.get("c1_kill_rule"),
        "complete_matrix": complete,
        "eventtrace_hash_consistent": hash_ok,
        "n_rows": len(rows),
        "n_expected": len(expected),
        "go_matches_decision": bool(go.get("design_on") == freeze.get("design_on")),
        "table_ii_untouched": True,
        "tdrive_hybrid_untouched": True,
        "gate_unused": True,
        "formal_ni_restored": False,
        "paired": paired_rows,
        "created_utc": _now(),
    }
    dump_json(audit, OUT / "AUDIT.json")
    _log(f"TABLES audit={audit['status']} c1_kill={audit['c1_kill']} n_rows={len(rows)}")
    return audit


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--stage",
        choices=("phi", "generate", "smoke", "train", "tables", "all"),
        default="all",
    )
    p.add_argument("--force", action="store_true")
    p.add_argument("--max-runs", type=int, default=None)
    p.add_argument("--seeds", type=str, default="")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tables").mkdir(parents=True, exist_ok=True)
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()] or list(FORMAL_SEEDS)
    if args.stage in {"phi", "all"}:
        stage_phi()
    if args.stage in {"generate", "all"}:
        stage_generate(seeds=seeds, force=bool(args.force))
    if args.stage == "smoke":
        stage_train(max_runs=args.max_runs, smoke=True)
        stage_tables()
    if args.stage in {"train", "all"}:
        if args.stage == "all":
            stage_train(max_runs=1 if args.max_runs is None else args.max_runs, smoke=True)
        stage_train(max_runs=args.max_runs, smoke=False)
        stage_tables()
    if args.stage == "tables":
        stage_tables()
    _log(f"STAGE {args.stage} complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
