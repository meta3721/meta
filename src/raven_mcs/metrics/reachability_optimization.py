"""Reachability optimization via CVXPY (P10-D).

Solves:
    min ||sum eta_r (M_r alpha_r - mu)||_2 / sum eta_r

subject to alpha_r simplex constraints, to compute the true epsilon_reach.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import cvxpy as cp
import numpy as np


@dataclass(frozen=True)
class ReachabilityResult:
    epsilon_reach: float
    solver_status: str
    block_length: int
    feasible: bool
    optimal_alphas: list[np.ndarray] | None = None


def solve_epsilon_reach(
    coverage_matrices: list[np.ndarray],
    mu: np.ndarray,
    etas: list[float],
    *,
    alpha_max: float = 0.5,
    e_min: float = 3.0,
    tolerance: float = 1e-6,
) -> ReachabilityResult:
    """Compute the optimal epsilon_reach for a block of windows.

    Args:
        coverage_matrices: List of M_r matrices (groups × clients).
        mu: Target distribution vector.
        etas: Learning rate for each window.
        alpha_max: Maximum per-client weight.
        e_min: Minimum effective sample size.
        tolerance: Solver tolerance.

    Returns:
        ReachabilityResult with optimized epsilon and solver status.
    """
    mu_arr = np.asarray(mu, dtype=np.float64)
    n_groups = len(mu_arr)

    if not coverage_matrices:
        return ReachabilityResult(
            epsilon_reach=0.0,
            solver_status="empty_block",
            block_length=0,
            feasible=True,
        )

    alpha_vars = []
    mix_vars = []
    constraints = []

    for r, M_r in enumerate(coverage_matrices):
        M = np.asarray(M_r, dtype=np.float64)
        n_clients = M.shape[1]
        alpha = cp.Variable(n_clients)
        alpha_vars.append(alpha)
        mix_vars.append(M @ alpha)

        a_bar = min(alpha_max, 1.0) if n_clients > 0 else 0.5
        constraints.append(alpha >= 0)
        constraints.append(alpha <= a_bar)
        constraints.append(cp.sum(alpha) == 1.0)

    # Build cumulative weighted deviation
    total_eta = sum(etas)
    cumulative = cp.Constant(np.zeros(n_groups))
    for r, (mix_r, eta_r) in enumerate(zip(mix_vars, etas)):
        if eta_r > 0:
            cumulative = cumulative + eta_r * (mix_r - mu_arr)

    objective = cp.Minimize(cp.norm2(cumulative) / max(total_eta, 1e-10))

    problem = cp.Problem(objective, constraints)

    started = time.perf_counter()
    try:
        problem.solve(solver=cp.CLARABEL, verbose=False)
        status = str(problem.status)
        feasible = status == "optimal"
    except Exception:
        try:
            problem.solve(solver=cp.SCS, verbose=False, eps=float(tolerance))
            status = str(problem.status)
            feasible = status in ("optimal", "solved")
        except Exception:
            status = "solver_failed"
            feasible = False

    elapsed = time.perf_counter() - started

    if feasible and problem.value is not None:
        eps = float(problem.value)
        optimal = [np.asarray(a.value, dtype=np.float64).flatten() for a in alpha_vars]
    else:
        eps = float("inf")
        optimal = None

    return ReachabilityResult(
        epsilon_reach=eps,
        solver_status=status,
        block_length=len(coverage_matrices),
        feasible=feasible,
        optimal_alphas=optimal,
    )
