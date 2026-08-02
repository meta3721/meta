# E1-ENTRY-R4 Baseline Audit

Date: 2026-08-02

- Baseline commit: `49a2f88d7861e7bb2cf7299e9f4198849453dd5f`.
- Worktree was clean; full machine summary reported 299 passed, 6 skipped.
- `E_r` is currently derived from positive first-stage mass before reading U,
  but EventTrace and q history do not persist an explicit `attempted` field.
- `_update_lagged_estimators` currently updates q for every window record.
  This retains U=0 rows, but incorrectly labels clients with no observed
  buffer as q failures.
- Raw EventTrace has no explicit risk-set-size, attempt-failure or non-attempt
  fields.
- Formal arrival risk currently uses
  `opportunity.get((client, stratum), p_min)`, assigning positive opportunity
  mass to structurally unsupported pairs.
- R3 smoke metrics are in the R3 evidence package; all clip gates passed, but
  RMSE_rho, Gap_mis, Tail and Head depend on the incorrect arrival support.
- Frozen pi target was created at `d341d9a...`; its hash has not been
  independently recomputed from final commit `49a2f88...`.
- R3 exact-command JSONL contains test and dependency commands, not the full
  freeze/audit/validation/smoke/aggregation workflow.
- Therefore stage-2 attempt semantics and arrival-support metric gates fail;
  E1 remains blocked for R4 remediation.
