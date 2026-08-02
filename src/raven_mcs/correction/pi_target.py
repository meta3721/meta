"""Frozen client-stratum target mass for the first-stage design ratio."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from raven_mcs.data.target import GroupMapper, TargetBuilder
from raven_mcs.utils.hashing import sha256_file


def build_pi_target(
    atomic: pd.DataFrame,
    station_to_client: dict[str, str],
    *,
    split: str = "test",
) -> pd.DataFrame:
    """Build pi target from frozen station-client opportunity support."""
    target = TargetBuilder(
        group_mapper=GroupMapper("target_group_main"),
    ).build(atomic, split=split)
    selected = atomic.loc[
        atomic["unit_id"].astype(str).isin(target.atom_mass.index),
        ["unit_id", "spatial_id", "opportunity_stratum"],
    ].copy()
    selected["unit_id"] = selected["unit_id"].astype(str)
    selected["opportunity_stratum"] = selected[
        "opportunity_stratum"
    ].astype(str)
    selected["target_mass"] = selected["unit_id"].map(target.atom_mass)

    mapping = {
        str(station): str(client)
        for station, client in station_to_client.items()
    }
    selected["client_id"] = selected["spatial_id"].astype(str).map(mapping)
    if selected["client_id"].isna().any():
        raise ValueError("positive target station lacks frozen client mapping")
    lambda_s = selected.groupby("opportunity_stratum")["target_mass"].sum()
    target_support = selected[
        ["client_id", "opportunity_stratum"]
    ].drop_duplicates()
    if bool(
        target_support.groupby("opportunity_stratum")["client_id"].nunique().gt(1).any()
    ):
        raise ValueError("each stratum must map to exactly one client")
    all_units = atomic[
        ["spatial_id", "opportunity_stratum"]
    ].copy()
    all_units["opportunity_stratum"] = all_units["opportunity_stratum"].astype(str)
    all_units["client_id"] = all_units["spatial_id"].astype(str).map(mapping)
    if all_units["client_id"].isna().any():
        raise ValueError("atomic station lacks frozen client mapping")
    support = all_units[
        ["client_id", "opportunity_stratum"]
    ].drop_duplicates()
    if bool(
        support.groupby("opportunity_stratum")["client_id"].nunique().ne(1).any()
    ):
        raise ValueError("station-client support is not unique by stratum")
    support["Lambda_s_tar"] = support["opportunity_stratum"].map(
        lambda_s,
    ).fillna(0.0)
    support["lambda_k_given_s_tar"] = 1.0
    support["pi_k_s_tar"] = support["Lambda_s_tar"]
    support["support_flag"] = True
    support = support.sort_values(
        ["client_id", "opportunity_stratum"],
    ).reset_index(drop=True)
    if abs(float(support["pi_k_s_tar"].sum()) - 1.0) > 1e-12:
        raise ValueError("pi target does not sum to one")
    if bool((support["pi_k_s_tar"] < 0).any()):
        raise ValueError("pi target must be nonnegative")
    return support


def load_pi_target(path: Path) -> tuple[dict[tuple[str, str], float], str]:
    frame = pd.read_parquet(path)
    required = {"client_id", "opportunity_stratum", "pi_k_s_tar", "support_flag"}
    if not required.issubset(frame.columns):
        raise ValueError(f"pi target missing columns: {sorted(required - set(frame))}")
    if abs(float(frame["pi_k_s_tar"].sum()) - 1.0) > 1e-12:
        raise ValueError("frozen pi target does not sum to one")
    values = {
        (str(row.client_id), str(row.opportunity_stratum)): float(row.pi_k_s_tar)
        for row in frame.itertuples()
    }
    return values, sha256_file(path)
