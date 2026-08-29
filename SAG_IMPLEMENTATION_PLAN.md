# SAG_IMPLEMENTATION_PLAN.md

Status: **plan only — no code change, no experiment, waiting for confirmation.**  
Date: 2026-08-29  
Branch to create later: `raven_sag_g0_g1`  
Authority (if existing code / comments / old scripts conflict):

1. `RAVEN_MCS_Support_Aware_Gate_Spec_v1.2_Final_Closure.txt`
2. `RAVEN_MCS_v2_Sections_III_VI_PostAudit_Final.txt`
3. `RAVEN_MCS_Cursor_SAG_G0_G1_Experiment_Instruction_v1.0.txt`

Handoff copies: `_handoff_sag_v1.1/`.  
This plan does **not** rewrite Overleaf `main.tex`. Sections III–VI in the PostAudit file are the theory master for SAG code.

---

## 0. What will not happen in this round

- No dataset-name Gate (`if dataset == sensorscope: G=1`).
- No Path B `raven_gated` inside the trainer.
- No 20-seed / E1–E5 / T-Drive / FedCure / neural Gate.
- No overwrite of sealed E1–E4, `paper_ready_r2/`, `post_review/` results, or `outputs/` of old gates.
- No-Design is **not** FedAvg and **not** ObsUse: only `zetã = 1`; observation IPW, usable IPW, P2, V, staleness, optional Debt stay on.
- Shared EventTrace for Always-D / No-D / SAG (same seed). Do not regenerate a new trace per mode.

---

## 1. Required window order (must implement)

From PostAudit Algorithm 1 and the G0/G1 instruction:

```
completed history
  → F_{r-} SAG certificates
  → freeze G_r                         [stage 1]
  → realize R                          [stage 2]
  → freeze p̂_obs from H^obs (pre-O)   [stage 3]
  → realize O, form E_r (registered)   [stage 4]
  → ζ̃ = 1 + G_r (ζ̂^D − 1)
  → m_{k,r}, B_r = {k ∈ E_r : m>0}     [local set]
  → weights / c / n_eff on B_r
  → local Hájek training on B_r        [stage 5]
  → freeze q̂_use from H^use (pre-U)   [stage 6]
  → realize U                          [stage 7]
  → A_r = B_r ∩ U_r
  → restrict masses to A_r; d, β̂, M, V, C
  → P2 / global update / optional Debt [stage 8]
  → post-window D vs 0 audit (future Gate only)
```

Logical stage indices are enough if EventTrace is pre-materialized (G0-1). Assert:

`gate < R ≤ p_obs_freeze < O < local < q_use_freeze < U < P2`

---

## 2. Current code vs required order

### 2.1 Old dataset-level Design gate (must not remain on the SAG path)

| Location | What it does | SAG action |
|---|---|---|
| `post_review/G1_path_b_gated_default/run_path_b.py` `GATED = {sensorscope: raven, uair: raven_wo_design}` | Post-hoc paper label `raven_gated` | **Do not call** from SAG runners. Leave sealed Path B files untouched. |
| `post_review/G1_path_b_gated_default/PROTOCOL.md` | Dataset identity → Design ON/OFF | Not a runtime Gate |
| `post_review/G2_external_baselines/run_g2.py` same `GATED` | Reuses Path B | Out of SAG-G0/G1 |
| `src/raven_mcs/aggregation/method_policy.py` `POLICY_MAP["raven"]` / `["raven_wo_design"]` | Runtime `uses_design_ratio` | Keep as Always-D and No-D modes. Add `raven_sag`. |
| `src/raven_mcs/training/window_runner.py` ~339–340 | `if not uses_design_ratio: zeta = 1` | Keep for No-D. SAG uses `zetã = 1 + G_r (ζ̂^D − 1)` with `G_r` from certificates, **not** dataset name. |

Confirm: **no dataset-name Gate will remain** in `window_runner`, new `sag/` modules, or `run_sag_g0.py` / `run_sag_g1.py`.

### 2.2 Where R / O / U are realized

EventTrace is **already frozen** before training (`simulation/event_trace.py`: `freeze_event_trace`, `compute_trace_hash`). Realization in the runner is a **read**, not a draw.

| Layer | Written (generate) | Read (train) |
|---|---|---|
| R risk set | `e3/real_runner/generator_r3.py`, `simulation/event_trace.py` | `data/window_dataset.py` `extract_window_slice` → `risk_set_unit_ids` |
| O | same generators (`p_obs_true_by_unit`) | `WindowRecords.O`, `observed_unit_ids`, `observed_values` (Z) |
| U | `e3/semantic_alignment/stage2_usable.py` `compute_usable_indicator` | `WindowRecords.U` |

**Conflict:** `extract_window_slice` returns R, O, U, and Z in one call. G0 forbids using current O/U before their stages. Plan: keep the frozen file, but **stage the read** (or mask unused fields) so G_r cannot see R/O/U, p̂ freeze cannot see O/Z, q̂ freeze cannot see U.

Shared-trace reuse (keep): `e3/canary/execute.py` `ensure_eventtrace`, `e3/formal/eventtrace.py`, `e3/real_runner/runner.py` (`EventTrace_hash`). SAG G0/G1 must load the **same** sealed SensorScope/U-Air traces as E3 for a given seed.

### 2.3 Where p_obs / q_use are estimated / frozen

| Quantity | File | Function | Current timing | Required |
|---|---|---|---|---|
| p̂_obs | `propensity/observation.py` | `ObservationPropensity.predict` | Lagged model; called in `_process_window` **after** full slice (O already in `rec`) | Freeze using **pre-O** features only (`planned_workload_pre`, hour_block, …). Then read O. Do not refit on current O. |
| p̂ apply | `training/window_runner.py` | `_compute_p_hat` then `raw_weights(zeta, p_hat)` | Immediately uses `rec.O` for `m` | Allowed **after** freeze |
| p lag update | `window_runner.py` | `_update_lagged_estimators` | After window close | Keep (future windows only) |
| q̂_use | `propensity/usable.py` | `UsablePropensity.predict`, `deadline_slack_pre` | Computed **after** `A_r` is built from `U==1` (~555+) | **Move before U.** Freeze on registered `B_r` (or `E_r`) using H^use. Then read U. |
| oracle p/q | EventTrace `p_obs_true_by_unit`, `oracle_q` | SimOracle only | Truth is pre-state; still must not peek at current O/U to *choose* G_r | SAG-G0/G1 uses lagged hats, not SimOracle, unless a later instruction says otherwise |

**P0 leak today:** q̂ is estimated on `a_r_clients` (already U=1). That must change.

### 2.4 Local training set (B_r vs old E_r)

| Spec name | Meaning | Current code name |
|---|---|---|
| `E_r` | registered (nonempty observed buffer / `attempted==1`) | `attempted_clients` |
| `B_r` | `{k ∈ E_r : m_{k,r}>0}` — **local training** | `e_r_clients` (docstring: “E_r before reading U”) |
| `A_r` | `B_r ∩ U_r` — aggregation | `a_r_clients` |

Algebra is almost right: local SGD already runs on `e_r_clients` before U is used for aggregation.  
**Rename** `e_r_clients` → `b_r_clients` and set `E_r = attempted`. Do **not** train on `A_r`.  
`WindowDataSlice.all_client_ids` comment (“E_r — all with m>0”) is wrong under v2 and should be fixed when touching that file.

### 2.5 P2

| File | Function | Role |
|---|---|---|
| `aggregation/p2_cvxpy.py` | `solve_p2` | CLARABEL, SCS fallback |
| `aggregation/feasibility.py` | `alpha_bar`, `ess_ball_bound` | C_r ingredients |
| `aggregation/methods.py` | `RavenAggregator.compute_server_weights` | Calls P2 |
| `aggregation/debt.py` | `update_debt` | After α |

Do not skip P2 in smoke runs. Theorem 3 compares D vs 0 on **common A_r** with possibly different β, M, V — counterfactual audit must re-solve (or reconstruct) both modes on the same trace **after** the window, without changing G_r.

### 2.6 EventTrace

| File | Role |
|---|---|
| `simulation/event_trace.py` | Schema, freeze, hash |
| `e3/real_runner/generator_r3.py` | Production R/O/U |
| Sealed dirs under `artifacts/e3_formal_runs_r1/eventtraces/{ds}/seed…` | Reuse; do not regenerate |

G0-3: Always-D / No-D / SAG must share identical R/O/U/deadline/staleness hashes.

---

## 3. Files to modify (minimal)

Do **not** restyle the whole tree to the instruction’s ideal `src/sag/` layout. Add a small package under existing `src/raven_mcs/`.

### 3.1 New modules

| File | Responsibility |
|---|---|
| `src/raven_mcs/sag/__init__.py` | Package |
| `src/raven_mcs/sag/gate.py` | Binary G_r from certificates; fail-closed; **no dataset_id** |
| `src/raven_mcs/sag/certificates.py` | C_cov/ret/ESS/clip LCBs/UCBs; δ_A UCB; Δβ/M/V UCBs; B_srv, B_tot = B_srv + 2δ_A + 2δ_cal |
| `src/raven_mcs/sag/sag_state.py` | Lagged F_{r-} buffer; look-back H; hashes |
| `src/raven_mcs/sag/counterfactual_audit.py` | Post-window D vs 0 on recorded R/O/U; D^A; Δβ/M/V or NA if both-empty |
| `src/raven_mcs/sag/timing.py` | Stage indices + asserts (extend `WindowClock` or wrap it) |
| `src/raven_mcs/experiments/run_sag_g0.py` | G0 smoke/full |
| `src/raven_mcs/experiments/run_sag_g1.py` | G1 5-seed only after G0 PASS |
| `src/raven_mcs/audits/sag_timing_audit.py` | G0-1 |
| `src/raven_mcs/audits/sag_leakage_audit.py` | G0-5 forbidden features |
| `src/raven_mcs/audits/sag_eventtrace_audit.py` | G0-3 |
| `tests/test_sag_timing.py` etc. | Instruction §23 tests 1–10 |

### 3.2 Existing files to touch

| File | Change |
|---|---|
| `aggregation/method_policy.py` | Add `raven_sag` policy = same flags as `raven`, plus a SAG flag **or** a `gate_mode in {always_on, always_off, sag}` |
| `training/window_runner.py` | Insert G_r before R; freeze p̂ before using O; rename B_r; freeze q̂ before reading U; call post-window audit; log stages |
| `data/window_dataset.py` | Staged extract: risk-set-only vs observation vs usable; stop packing U/Z into the first read |
| `training/window_timing.py` | Optional stage counters for G0-1 |
| `e3/real_runner/runner.py` (or a thin SAG wrapper) | Three methods, one EventTrace path, write `outputs/sag_g0/` and `outputs/sag_g1/` |

### 3.3 Do not modify

- Sealed EventTraces / E3–E4 run trees  
- `post_review/G1_path_b_gated_default/` (historical)  
- `TO_OVERLEAF_paper_tmc_r1_clean/` (paper rewrite is a later task)  
- P2 solver math, unless a bug blocks counterfactual reconstruction  

---

## 4. Three modes (same trace)

| Mode | G_r | ζ̃ |
|---|---|---|
| Always-Design (`raven` / Mode D) | 1 | ζ̂^D |
| No-Design RAVEN (`raven_wo_design` / Mode 0) | 0 | 1 |
| SAG-RAVEN (`raven_sag`) | certificates | 1 + G_r (ζ̂^D − 1) |

Shared: split, seed, EventTrace, R/O/U, deadline, staleness, init, local steps, LR, P2 λ, target map, p/q model **classes**.  
SAG certificates use only completed windows + public target + lagged states.

---

## 5. Certificate v1 (auditable, not a net)

First implementation (Spec §15, Instruction §7):

- `C_cov`: one-sided lower bound on P^opp inside π^tar > 0; **not** a smoothed positive point estimate  
- `C_ret` / `C_ESS` / `C_clip`: rolling history lower/upper bounds  
- `δ_A_UCB`: low-dim logistic / isotonic / empirical-bin + one-sided upper  
- `Δβ/M/V_UCB`: rolling quantile  
- `B_M,r`: F_{r-}-measurable, default `sqrt(K)` (not realized |A_r|)  
- `δ_cal`: frozen (start 0.05 for 95% target; report 90% as diagnostic only)  
- Fail-closed: missing / NaN / cold start / out of range → G_r = 0  
- Reason bitmask: `OFF_COLD_START`, `OFF_LOW_COVERAGE`, … (Spec §19)

Forbidden Gate features: `dataset_id`, current R/O/U, Z, label, loss, RMSE, gradient, update, future state.

---

## 6. G0 then G1 (after this plan is approved)

1. Unit tests (instruction §23).  
2. G0-smoke: 1 dataset, 1 seed, shortened windows, **same code path**, P2 and audit on.  
3. G0-full: SS + U-Air, 2–3 seeds. Any P0 FAIL → stop.  
4. G1-5seed only if G0 full PASS. Do **not** auto-expand to 10 seeds.

Outputs: `outputs/sag_g0/`, `outputs/sag_g1/` only.

---

## 7. Naming map (code comments will follow v2)

| Old comment in `window_runner` | v2 symbol |
|---|---|
| “E_r = m>0 before U” | **B_r** |
| “attempted” | **E_r** |
| “A_r = U=1 ∩ E_r” | **A_r = B_r ∩ U_r** |
| Path B / `raven_gated` | **forbidden as Gate** |

---

## 8. Confirmation checklist (please reply)

- [ ] Add `raven_sag` + stage the EventTrace **read** inside `FullWindowRunner` (preferred: minimal).  
- [ ] Reuse sealed E3 SensorScope/U-Air EventTraces (same hashes for D / 0 / SAG).  
- [ ] First certificate models: rolling quantile + empirical-bin / isotonic (no neural Gate).  
- [ ] Do **not** edit Overleaf III–VI in this implementation pass.  
- [ ] After G0/G1, wait for GO / REPAIR / STOP before any further campaign.

No implementation starts until these are confirmed.
