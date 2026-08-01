"""Identity-safe fleet partitioning utilities (used by T-Drive adapter later)."""

from __future__ import annotations

import numpy as np
import pandas as pd


class FleetSplitError(ValueError):
    pass


def stratified_fleet_split(
    trajectory_lengths: pd.Series,
    *,
    reference_fraction: float = 0.30,
    seed: int,
    max_strata: int = 10,
) -> pd.DataFrame:
    """Split vehicle identities by trajectory-length strata with exact disjointness."""
    if not 0 < reference_fraction < 1:
        raise FleetSplitError("reference_fraction must be in (0, 1)")
    if trajectory_lengths.index.has_duplicates:
        raise FleetSplitError("vehicle identities must be unique")
    lengths = pd.to_numeric(trajectory_lengths, errors="raise").astype("float64")
    if len(lengths) < 4:
        raise FleetSplitError("At least four vehicles are required")
    if not np.isfinite(lengths.to_numpy()).all() or (lengths <= 0).any():
        raise FleetSplitError("trajectory lengths must be finite and positive")

    ordered = lengths.sort_values(kind="stable")
    desired_reference = round(len(ordered) * reference_fraction)
    desired_reference = min(max(desired_reference, 1), len(ordered) - 1)
    stratum_count = min(max_strata, desired_reference, len(ordered) - desired_reference)
    strata = [chunk for chunk in np.array_split(ordered.index.to_numpy(), stratum_count)]

    raw_quotas = np.asarray([len(chunk) * reference_fraction for chunk in strata])
    quotas = np.floor(raw_quotas).astype(int)
    remaining = desired_reference - int(quotas.sum())
    remainder_order = np.argsort(-(raw_quotas - quotas), kind="stable")
    for stratum_index in remainder_order[:remaining]:
        quotas[stratum_index] += 1

    rng = np.random.default_rng(int(seed))
    records: list[dict[str, object]] = []
    for stratum_index, (identities, quota) in enumerate(zip(strata, quotas)):
        shuffled = rng.permutation(identities)
        reference = set(shuffled[:quota])
        for vehicle_id in identities:
            records.append(
                {
                    "vehicle_id": str(vehicle_id),
                    "trajectory_length": float(lengths.loc[vehicle_id]),
                    "length_stratum": int(stratum_index),
                    "fleet": "reference" if vehicle_id in reference else "client",
                }
            )
    result = pd.DataFrame(records).sort_values("vehicle_id").reset_index(drop=True)
    assert_fleet_disjoint(result)
    return result


def assert_fleet_disjoint(
    fleet_assignments: pd.DataFrame,
    *,
    identity_column: str = "vehicle_id",
    fleet_column: str = "fleet",
) -> None:
    """Assert one and only one reference/client assignment per identity."""
    required = {identity_column, fleet_column}
    if not required.issubset(fleet_assignments):
        raise FleetSplitError(f"Missing fleet columns: {sorted(required)}")
    invalid = set(fleet_assignments[fleet_column].astype(str).unique()) - {
        "reference",
        "client",
    }
    if invalid:
        raise FleetSplitError(f"Invalid fleet labels: {sorted(invalid)}")
    if fleet_assignments[identity_column].duplicated().any():
        raise FleetSplitError("reference and client fleets overlap by identity")
    if set(fleet_assignments[fleet_column]) != {"reference", "client"}:
        raise FleetSplitError("Both reference and client fleets must be non-empty")
