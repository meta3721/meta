# E1 Clip-Gate Definition Audit

## Sources

| Source | Exact wording / behavior | Population and aggregation | Equality / horizon | Frozen? |
|---|---|---|---|---|
| `configs/frozen/e1_weight_safety.yaml` | `first_stage_clip_rate_max: 0.05` | Not stated | Not stated; validation selection declares `windows: 20` | Yes |
| `scripts/run_e1_r4_validation_safety.py:49-56` | `first_stage_clip_rate <= 0.05` | Reads the run scalar | Inherits run implementation; validation runs are 20 windows | No independent definition |
| `scripts/check_e1_run_gates.py:51-55` | `first_stage_clip_rate <= 0.05` | Reads the formal run scalar | Inherits run implementation; formal run is 100 windows | Yes for formal gate |
| `src/raven_mcs/training/window_runner.py:313,572-574` and `e1_entry.py:973` | `mean(abs(a_raw) >= a_max)`, then client and active-window means | Risk records within client; client-window macro; active-window macro | Equality included; active windows only | Implementation |
| E1-FORMAL-EXECUTION-R1 instruction | `first-stage clip rate <=0.05` | Not stated | Not stated | Formal execution instruction |

## Conclusion: C — original definition is materially incomplete

The frozen parameter file and execution instructions freeze the threshold but
do not specify the population (risk versus observed), averaging hierarchy
(micro versus client/window macro), equality treatment (`>` versus `>=`), or
whether the 20-window validation selection horizon is intended to define a
100-window formal gate.  The production implementation consistently applies
one particular macro `>=` definition, but the documents do not independently
make that definition the unique intended gate.

This conclusion is not based on which metric is lower.  In this failed run,
the reconstructed true-exceed risk and observed micro rates both exceed 5%,
so changing from `>=` to `>` cannot resolve the safety finding.  Under the
pre-registered DIAG-R1 decision rule, the appropriate next status is protocol
clarification (branch C), not an erratum/retry.
