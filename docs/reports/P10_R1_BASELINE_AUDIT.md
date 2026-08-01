# P10-R1 Baseline Audit

**Date:** 2026-08-01  
**Scope:** Time semantics, arrival-risk metrics, q leakage audit, group mapping, and artifacts.

## Baseline Findings

- Current P10 Smoke run: `outputs/runs/P10_SMOKE_20260801_054328`.
- EventTrace used real SensorScope unit IDs but did not write time/tau audit evidence.
- `RMSE_mu` and `RMSE_rho` were both unweighted RMSE; `Gap_mis` was incorrectly group-RMSE range.
- The EventTrace was partitioned by contiguous `time_index` slices, not modulo, but omitted the final time slot and did not validate absolute-time chronology.
- q leakage scan had no explicit whitelist and previous audit acceptance was not strict.
- FedAvg and TwoStage-Hajek were identical because the runner ignored MethodPolicy for local loss and never updated q.
- Current main mapping has 220 station×time groups; P10-R1 freezes E1 G=4 time-only groups in `configs/frozen/e1_sensorscope_groups.yaml`.
- Existing smoke artifacts lacked resolved configuration, trace reference, per-window metrics, arrival weights, propensity/solver/system diagnostics, checkpoints, and logs.

## Baseline Metrics (invalid for E1)

| Method | RMSE_mu | RMSE_rho | Reported Gap_mis |
|---|---:|---:|---:|
| FedAvg-Window | 2.2809 | 2.2809 | 2.0641 |
| TwoStage-Hajek | 2.2809 | 2.2809 | 2.0641 |
| RAVEN-MCS | 2.2164 | 2.2164 | 1.9568 |

These values are retained as audit evidence only and are superseded by P10-R1.
