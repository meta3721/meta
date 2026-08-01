"""Shared Common-NDMF backbone (Phase 5). No client embedding."""

from __future__ import annotations

import math

import torch
from torch import nn


class CommonNDMF(nn.Module):
    """
    Spatial emb 32 + time MLP 32 + interaction features + head 128→64→32→1.

    Ban: client_id embedding.
    """

    def __init__(
        self,
        *,
        num_spatial: int,
        spatial_dim: int = 32,
        time_dim: int = 32,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        if num_spatial <= 0:
            raise ValueError("num_spatial must be positive")
        self.num_spatial = int(num_spatial)
        self.spatial = nn.Embedding(self.num_spatial, spatial_dim)
        self.time_mlp = nn.Sequential(
            nn.Linear(5, 64),
            nn.ReLU(),
            nn.Linear(64, time_dim),
            nn.ReLU(),
        )
        fused = spatial_dim + time_dim + spatial_dim + spatial_dim
        self.head = nn.Sequential(
            nn.Linear(fused, 128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    @staticmethod
    def time_features(hour: torch.Tensor, weekday: torch.Tensor, trend: torch.Tensor) -> torch.Tensor:
        hour = hour.float()
        ang = 2.0 * math.pi * hour / 24.0
        return torch.stack(
            [
                torch.sin(ang),
                torch.cos(ang),
                weekday.float(),
                trend.float(),
                torch.sin(2.0 * ang),
            ],
            dim=-1,
        )

    def forward(
        self,
        spatial_index: torch.Tensor,
        hour: torch.Tensor,
        weekday: torch.Tensor,
        trend: torch.Tensor,
    ) -> torch.Tensor:
        if spatial_index.dtype != torch.long:
            spatial_index = spatial_index.long()
        if bool((spatial_index < 0).any() or (spatial_index >= self.num_spatial).any()):
            raise ValueError("spatial_index out of range")
        e_n = self.spatial(spatial_index)
        e_t = self.time_mlp(self.time_features(hour, weekday, trend))
        interaction = torch.cat([e_n, e_t, e_n * e_t, torch.abs(e_n - e_t)], dim=-1)
        return self.head(interaction).squeeze(-1)

    def uses_client_embedding(self) -> bool:
        return False


def deterministic_common_ndmf(
    num_spatial: int,
    *,
    seed: int = 26001,
) -> CommonNDMF:
    torch.manual_seed(int(seed))
    model = CommonNDMF(num_spatial=num_spatial)
    return model
