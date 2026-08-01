"""Real local Hájek-weighted SGD client training (P10-A).

ClientTrainer performs local SGD steps using the Hájek-weighted MSE loss.
The model is a Common-NDMF instance. Client ID is NOT used as a model feature.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch import nn

from raven_mcs.models.common_ndmf import CommonNDMF
from raven_mcs.models.features import extract_features
from raven_mcs.training.local_objective import local_hajek_loss, normalize_a_bar


class ClientTrainer:
    """Performs local Hájek-weighted SGD on client observations.

    Args:
        model: Common-NDMF model instance.
        learning_rate: Local learning rate gamma_r.
    """

    def __init__(self, model: CommonNDMF, learning_rate: float = 0.01) -> None:
        self.model = model
        self.learning_rate = float(learning_rate)

    def train_step(
        self,
        model_state: dict[str, torch.Tensor],
        observed_records: list[dict[str, Any]],
        a_bar_weights: np.ndarray,
        local_steps: int,
    ) -> tuple[np.ndarray, float]:
        """Perform local SGD steps and return normalized update and loss.

        Args:
            model_state: Server model state_dict to load before training.
            observed_records: List of dicts with keys:
                - spatial_id (str)
                - absolute_time (float)
                - time_index (int)
                - observed_value (float)
                - spatial_to_idx (dict mapping str→int)
            a_bar_weights: Hájek-normalized weights a_bar, shape (N_record,).
            local_steps: Number of local SGD steps E_loc.

        Returns:
            Tuple of (flattened_local_update, average_train_loss).
        """
        if not observed_records:
            return np.array([], dtype=np.float64), 0.0

        # Load server model weights (deep copy to avoid mutating server state)
        self.model.load_state_dict(
            {k: v.clone() for k, v in model_state.items()}
        )
        self.model.train()

        n_records = len(observed_records)
        a_bar_tensor = torch.tensor(a_bar_weights, dtype=torch.float32)

        # Extract features
        spatial_ids = [r["spatial_id"] for r in observed_records]
        abs_times = [r["absolute_time"] for r in observed_records]
        time_idx = [r["time_index"] for r in observed_records]
        targets = torch.tensor(
            [r["observed_value"] for r in observed_records],
            dtype=torch.float32,
        )

        # Use spatial_to_idx from first record (same across client)
        spatial_to_idx = observed_records[0].get("spatial_to_idx", {})
        total_slots = observed_records[0].get("total_time_slots", None)

        sp_idx, hour_t, wday_t, trend_t = extract_features(
            spatial_ids, abs_times, time_idx, spatial_to_idx, total_slots,
        )

        param_ids_before = {name: p.data.clone() for name, p in self.model.named_parameters()}

        total_loss = 0.0
        for _ in range(local_steps):
            self.model.zero_grad()
            predictions = self.model(sp_idx, hour_t, wday_t, trend_t)
            loss = local_hajek_loss(predictions, targets, a_bar_tensor)
            loss.backward()
            with torch.no_grad():
                for p in self.model.parameters():
                    if p.grad is not None:
                        p -= self.learning_rate * p.grad
            total_loss += float(loss.item())

        avg_loss = total_loss / max(local_steps, 1)

        # Compute normalized update: (theta_s - theta_local) / (gamma * E_loc)
        flat_params_before = _flatten_params(param_ids_before)
        flat_params_after = _flatten_params(dict(self.model.named_parameters()))

        update = flat_params_before - flat_params_after
        denom = self.learning_rate * local_steps
        if denom > 0:
            update = update / denom

        return update, avg_loss


def _flatten_params(param_dict: dict[str, torch.Tensor]) -> np.ndarray:
    """Flatten named parameters into a single 1-D NumPy array in stable key order."""
    pieces: list[np.ndarray] = []
    for key in sorted(param_dict.keys()):
        pieces.append(param_dict[key].detach().cpu().numpy().ravel())
    if not pieces:
        return np.array([], dtype=np.float64)
    return np.concatenate(pieces).astype(np.float64)


def unflatten_params(
    flat: np.ndarray,
    reference_state: dict[str, torch.Tensor],
) -> dict[str, torch.Tensor]:
    """Restore flattened parameter vector to a state_dict matching reference shapes."""
    result: dict[str, torch.Tensor] = {}
    offset = 0
    for key in sorted(reference_state.keys()):
        ref = reference_state[key]
        size = int(ref.numel())
        piece = flat[offset:offset + size].reshape(ref.shape)
        result[key] = torch.tensor(piece, dtype=ref.dtype)
        offset += size
    return result
