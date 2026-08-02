# E1-ENTRY-R2 Baseline Audit

Date: 2026-08-02

## Repository identity

- Baseline commit: `b997899ee74bc68dcef2080b15894d825619f9e4`.
- Baseline branch was clean before creating `e1-entry-r2-final-seal`.
- Full pytest baseline: 281 passed, 3 skipped, 1 expected TimeAlign failure.
- E1 remained blocked; formal five-seed E1 and E2–E9 were not run.

## Method semantics

FedAsync uses raw sample mass multiplied by exponential model-staleness decay.
The former `TimeAlignAggregator` uses the identical formula and parameters.
Its controlled nonzero-staleness fixture therefore gives zero alpha
difference. R2 supplies the teacher-frozen temporal-coverage formula required
to replace this alias.

## Arrival-risk boundary

Local p prediction already uses `planned_workload_pre`, but the formal
arrival-risk reconstruction in `_arrival_weights` computes
`mean(raw_workload)` from the completed EventTrace. In the generator,
`raw_workload=len(observed)`, so this is post-outcome information and must be
removed. The replacement must use frozen train history and
`planned_workload_pre`.

## Observation propensity granularity

The current p model predicts each risk record separately, but after a window it
adds only one client-window row with label `mean(O)`. It does not persist a
record-level history table. R2 must retain each `(client, window, unit,
stratum, X, O)` record after close.

## Client and EventTrace identity

The regenerated R1 station-cluster mapping currently has exactly eight
nonempty clients, but the generator CLI/default still exposes `clients=10`
and the formal protocol does not consistently freeze `num_clients: 8`.
The five existing traces were generated from the R1 commit, not the final R2
commit. They must be regenerated only after the final R2 code commit is clean.

## Entry status

The R1 smoke guard intentionally refuses to run because TimeAlign is
unresolved. Consequently there is no valid five-method R2 smoke, aggregate or
statistical dry-run at this baseline.
