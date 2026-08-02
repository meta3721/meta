"""Frozen client-stratum target mass for the first-stage design ratio."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from raven_mcs.data.target import GroupMapper, TargetBuilder
from raven_mcs.utils.hashing import sha256_file


def build_pi_target(
    atomic: pd.DataFrame,
    client_measurements: pd.DataFrame,
    *,
    split: str = "test",
) -> pd.DataFrame:
    """Build pi^tar_{k,s} before training from public target support."""
    target = TargetBuilder(
        group_mapper=GroupMapper("target_group_main"),
    ).build(atomic, split=split)
    selected = atomic.loc[
        atomic["unit_id"].astype(str).isin(target.atom_mass.index),
        ["unit_id", "opportunity_stratum"],
    ].copy()
    selected["unit_id"] = selected["unit_id"].astype(str)
    selected["opportunity_stratum"] = selected[
        "opportunity_stratum"
    ].astype(str)
    selected["target_mass"] = selected["unit_id"].map(target.atom_mass)

    clients = client_measurements[["client_id", "unit_id"]].copy()
    clients["client_id"] = clients["client_id"].astype(str)
    clients["unit_id"] = clients["unit_id"].astype(str)
    lambda_s = selected.groupby("opportunity_stratum")["target_mass"].sum()
    target_support = selected[["unit_id", "opportunity_stratum"]].merge(
        clients, on="unit_id", how="left", validate="one_to_many",
    )[["client_id", "opportunity_stratum"]].drop_duplicates()
    if target_support["client_id"].isna().any():
        raise ValueError("positive target unit lacks client opportunity support")
    support_count = target_support.groupby("opportunity_stratum")["client_id"].count()
    target_support["Lambda_s_tar"] = target_support[
        "opportunity_stratum"
    ].map(lambda_s)
    target_support["lambda_k_given_s_tar"] = 1.0 / target_support[
        "opportunity_stratum"
    ].map(support_count).astype(float)
    target_support["pi_k_s_tar"] = (
        target_support["Lambda_s_tar"]
        * target_support["lambda_k_given_s_tar"]
    )
    all_units = atomic[["unit_id", "opportunity_stratum"]].copy()
    all_units["unit_id"] = all_units["unit_id"].astype(str)
    all_units["opportunity_stratum"] = all_units["opportunity_stratum"].astype(str)
    all_pairs = all_units.merge(
        clients, on="unit_id", how="inner", validate="one_to_many",
    )[["client_id", "opportunity_stratum"]].drop_duplicates()
    support = all_pairs.merge(
        target_support,
        on=["client_id", "opportunity_stratum"],
        how="left",
        validate="one_to_one",
    )
    support[["Lambda_s_tar", "lambda_k_given_s_tar", "pi_k_s_tar"]] = (
        support[["Lambda_s_tar", "lambda_k_given_s_tar", "pi_k_s_tar"]]
        .fillna(0.0)
    )
    support["support_flag"] = support["pi_k_s_tar"] > 0.0
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
