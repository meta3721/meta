"""Convex P2 solver via CVXPY + CLARABEL (paper F6.4–F6.5)."""

from __future__ import annotations

import time
from dataclasses import dataclass

import cvxpy as cp
import numpy as np

from raven_mcs.aggregation.feasibility import (
    alpha_bar,
    ess_ball_bound,
    validate_p2_lambdas,
)


@dataclass(frozen=True)
class P2Result:
    alpha: np.ndarray
    status: str
    objective_value: float
    solve_time_s: float
    primal_residual: float
    constraint_violation: float
    backend: str
    fallback_used: bool = False
    primary_status: str = ""
    fallback_solver: str | None = None
    fallback_status: str | None = None
    simplex_residual: float = 0.0
    nonnegative_violation: float = 0.0
    upper_bound_violation: float = 0.0
    ess_l2_violation: float = 0.0
    feasibility_repair_used: bool = False
    pre_repair_violation: float = 0.0


def solve_p2(
    coverage_matrix: np.ndarray,
    mu: np.ndarray,
    beta_reference: np.ndarray,
    debt: np.ndarray,
    variance_diag: np.ndarray,
    staleness: np.ndarray,
    *,
    lambda_group: float,
    lambda_beta: float,
    lambda_variance: float,
    lambda_staleness: float,
    alpha_max: float,
    e_min: float,
    max_server_learning_rate: float,
    tolerance: float = 1e-6,
    backend: str = "CLARABEL",
) -> P2Result:
    """
    Minimize
      -QᵀMα + (λ_g/2)‖Mα−μ‖² + (λ_β/2)‖α−β̂‖²
      + (λ_v/2)αᵀVα + λ_s τ̄ᵀα
    s.t. 1ᵀα=1, 0≤α≤ᾱ, ‖α‖₂²≤1/Ē.

    Ban (F6.7): client displacement vector u is not an input to weighting.
    """
    validate_p2_lambdas(
        lambda_beta=lambda_beta,
        lambda_group=lambda_group,
        max_server_learning_rate=max_server_learning_rate,
    )
    m = np.asarray(coverage_matrix, dtype=np.float64)
    target = np.asarray(mu, dtype=np.float64)
    beta = np.asarray(beta_reference, dtype=np.float64)
    q = np.asarray(debt, dtype=np.float64)
    v_diag = np.asarray(variance_diag, dtype=np.float64)
    tau = np.asarray(staleness, dtype=np.float64)
    if m.ndim != 2:
        raise ValueError("coverage_matrix must be groups × clients")
    n_groups, n_active = m.shape
    if target.shape != (n_groups,) or q.shape != (n_groups,):
        raise ValueError("mu/debt must match group dimension")
    if beta.shape != (n_active,) or v_diag.shape != (n_active,) or tau.shape != (
        n_active,
    ):
        raise ValueError("beta/variance/staleness must match active clients")
    if np.any(v_diag < 0):
        raise ValueError("variance_diag must be nonnegative")

    a_bar = alpha_bar(alpha_max=alpha_max, n_active=n_active)
    e_bar = ess_ball_bound(e_min=e_min, n_active=n_active)

    alpha = cp.Variable(n_active)
    mix = m @ alpha
    objective = (
        -q @ (m @ alpha)
        + 0.5 * float(lambda_group) * cp.sum_squares(mix - target)
        + 0.5 * float(lambda_beta) * cp.sum_squares(alpha - beta)
        + 0.5 * float(lambda_variance) * cp.sum(cp.multiply(v_diag, cp.square(alpha)))
        + float(lambda_staleness) * (tau @ alpha)
    )
    constraints = [
        cp.sum(alpha) == 1.0,
        alpha >= 0.0,
        alpha <= a_bar,
        cp.sum_squares(alpha) <= 1.0 / e_bar,
    ]
    problem = cp.Problem(cp.Minimize(objective), constraints)

    solver_name = backend.upper()
    fallback_used = False
    fallback_status: str | None = None
    fallback_solver: str | None = None
    started = time.perf_counter()
    try:
        if solver_name == "CLARABEL":
            problem.solve(solver=cp.CLARABEL, verbose=False)
        else:
            problem.solve(solver=solver_name, verbose=False)
    except Exception:  # noqa: BLE001
        pass
    primary_status = str(problem.status)

    def _violations(value: np.ndarray | None) -> tuple[float, float, float, float]:
        if value is None:
            return (float("inf"),) * 4
        candidate = np.asarray(value, dtype=np.float64).reshape(-1)
        return (
            abs(float(candidate.sum()) - 1.0),
            max(0.0, -float(candidate.min())),
            max(0.0, float(candidate.max()) - float(a_bar)),
            max(0.0, float(np.square(candidate).sum()) - 1.0 / float(e_bar)),
        )

    primary_violations = _violations(alpha.value)
    primary_bad = (
        primary_status != "optimal"
        or not np.all(np.isfinite(primary_violations))
        or max(primary_violations) > 1e-7
    )
    if primary_bad:
        fallback_used = True
        fallback_solver = "SCS"
        problem.solve(
            solver=cp.SCS,
            verbose=False,
            eps=min(float(tolerance), 1e-7),
            max_iters=100_000,
        )
        fallback_status = str(problem.status)
    elapsed = time.perf_counter() - started

    if alpha.value is None:
        raise RuntimeError(f"P2 solver failed with status={problem.status}")

    alpha_hat = np.asarray(alpha.value, dtype=np.float64).reshape(-1)
    simplex, nonnegative, upper, ball = _violations(alpha_hat)
    constraint_violation = max(simplex, nonnegative, upper, ball)
    accepted_status = str(problem.status)
    pre_repair_violation = constraint_violation
    repair_used = accepted_status != "optimal" or constraint_violation > 1e-7
    if repair_used:
        # Deterministic feasibility repair of the fallback candidate. Mixing
        # toward the uniform interior preserves simplex and box constraints
        # while reducing the L2 norm; this is recorded, never silent.
        alpha_hat = np.clip(alpha_hat, 0.0, a_bar)
        if float(alpha_hat.sum()) <= 0:
            raise RuntimeError("P2 fallback produced no positive mass")
        alpha_hat /= float(alpha_hat.sum())
        uniform = np.full(n_active, 1.0 / n_active, dtype=np.float64)
        l2_limit = 1.0 / float(e_bar)
        if float(np.square(alpha_hat).sum()) > l2_limit:
            low, high = 0.0, 1.0
            for _ in range(80):
                middle = (low + high) / 2.0
                candidate = (1.0 - middle) * alpha_hat + middle * uniform
                if float(np.square(candidate).sum()) <= l2_limit:
                    high = middle
                else:
                    low = middle
            alpha_hat = (1.0 - high) * alpha_hat + high * uniform
            alpha_hat /= float(alpha_hat.sum())
        simplex, nonnegative, upper, ball = _violations(alpha_hat)
        constraint_violation = max(simplex, nonnegative, upper, ball)
        accepted_status = "feasible_repaired"
    if constraint_violation > 1e-7:
        raise RuntimeError(
            "P2 residual hard gate failed: "
            f"status={accepted_status}, simplex={simplex:.3e}, "
            f"nonnegative={nonnegative:.3e}, upper={upper:.3e}, "
            f"ess_l2={ball:.3e}"
        )

    return P2Result(
        alpha=alpha_hat,
        status=accepted_status,
        objective_value=float(problem.value) if problem.value is not None else float("nan"),
        solve_time_s=float(elapsed),
        primal_residual=float(constraint_violation),
        constraint_violation=float(constraint_violation),
        backend=solver_name if not fallback_used else "SCS",
        fallback_used=fallback_used,
        primary_status=primary_status,
        fallback_solver=fallback_solver,
        fallback_status=fallback_status,
        simplex_residual=simplex,
        nonnegative_violation=nonnegative,
        upper_bound_violation=upper,
        ess_l2_violation=ball,
        feasibility_repair_used=repair_used,
        pre_repair_violation=pre_repair_violation,
    )
