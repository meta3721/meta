# P10-R1 Time, Metrics, and Audit Report

## 1. Executive Summary

P10-R1 passes R1-G1 through R1-G8 after correcting several blockers that were
not detected by the earlier test suite: test predictions had used the initial
model instead of final `theta`, EventTrace client assignment used randomized
Python `hash()`, the test-entry freeze gate was not invoked, and the old checker
implemented only four of eight gates. E1 remains **BLOCKED** pending teacher
review; no E1 experiment was run.

## 2. Git State

Branch: `p10-r1-time-metrics-audit`. Baseline commit:
`b4f1661944e100b86295da6583d6449106e7c8af`. The worktree is dirty because the
P10 implementation and evidence are not committed.

## 3. Chronological Window Audit

`outputs/audits/p10_r1_window_audit.json` records sorted-unique-time-slot
contiguous assignment, all 20 ranges, no modulo use, zero overlap,
out-of-order, future leakage, duplicate assignment, unassigned units, and tau
violations. EventTrace enforces
`0 <= tau = window_id - downloaded_version <= num_windows`.

## 4. Arrival Weight Implementation

Atomic intensity is computed as the sum over clients of frozen
`pi_hat_opp * nu_hat * p_hat_obs * q_hat_use`. The output preserves each
contribution plus raw intensity and normalized weight. Test prediction errors
are not inputs. Target-arrival L1 gap is `0.13949978`.

## 5. RMSE_mu / RMSE_rho / Gap Identity

The gate checker independently recomputes both RMSE values from
`predictions_test.parquet` and requires
`abs(Gap_mis - (RMSE_mu - RMSE_rho)) <= 1e-12`.

## 6. q Feature Leakage Audit

Runtime q inputs are `bias`, `model_age`, `device_class`, `network_budget`, and
`deadline_slack`. The strict audit output has the required source and reviewer
fields and contains no unreviewed forbidden feature. Status:
`REVIEWED_WHITELIST_ONLY` (simulator-truth arrival expressions only).

## 7. FedAvg vs TwoStage Diagnostic

`outputs/audits/p10_r1_fedavg_twostage_diagnostic.parquet` compares local
weights, alpha/beta, loss, update hashes, global hashes, and final prediction
differences per comparable window/client. Non-uniform differences are present;
status: `DISTINCT_PATHS_CONFIRMED`.

## 8. Frozen Target Groups

The main mapping is frozen at G=4 time-only groups. All groups have positive
support; optimized `solve_epsilon_reach` output and its validation hash are
frozen. The 220 station×time groups are
diagnostic only and do not enter main debt.

## 9. Artifact Completeness

R1-G7 verifies all required run files, three real checkpoint files, config,
EventTrace and group hashes, non-empty window metrics, and RAVEN solver
diagnostics.

## 10. Config Freeze and ISSUE-010

The test-entry gate now validates the frozen config hash, validation summary,
data hash, target-group hash, and EventTrace hash before any test prediction.
Mismatch tests are executable. ISSUE-010 is closed.

## 11. P10-R1 Smoke Results

Runs:
- `outputs/runs/P10_SMOKE_20260801_102055`
- `outputs/runs/P10_SMOKE_20260801_102515`

| Method | RMSE_mu | RMSE_rho | Gap_mis |
|---|---:|---:|---:|
| FedAvg | 7.181765 | 7.064596 | 0.117169 |
| TwoStage-Hajek | 7.157197 | 7.039968 | 0.117229 |
| RAVEN-MCS | 7.111120 | 6.993705 | 0.117415 |

The two same-seed runs have identical EventTrace/config identities,
predictions within `1e-10`, and metrics within `1e-12`.

## 12. Test Results

Full pytest: 146 passed. E0: 9 passed. G0: all four datasets pass. `pip check`
reports no broken requirements. The experiment runner imports and exposes its
CLI successfully.

## 13. Remaining Issues

CLARABEL emits an inaccurate-solution warning for at least one RAVEN window.
The solver diagnostics and numerical outputs remain finite and all R1 gates
pass, but the warning must remain visible for teacher review. Traffic preferred
60-station coverage also remains informationally open.

## 14. E1 Authorization Decision

`P10-R1 = PASS`. `E1 = BLOCKED_PENDING_TEACHER_REVIEW`. This report does not
authorize E1.
