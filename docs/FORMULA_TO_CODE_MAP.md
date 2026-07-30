# Formula → Code Map (RAVEN-MCS V2.3)

**Source of truth for experiments:** `RAVEN-MCS_V2.3_Cursor_实验执行指令.txt`  
**Workspace root:** `D:\Cursor\raven.mcs`  
**Status:** Phase 1 — package/layout/utils exist; formula modules still **PLANNED** (no numeric F1–F9 yet).
**Update rule:** When a symbol lands, replace `PLANNED` with `path::symbol` and keep the formula ID stable.

---

## 1. Atomic units, strata, targets

| ID | Symbol / definition | Planned code | Notes / bans |
|----|---------------------|--------------|--------------|
| F1.1 | Atomic unit `i = (n, t)` | `src/raven_mcs/data/base.py::AtomicUnit` | Absolute time slot; no per-atom-only opportunity counts |
| F1.2 | Opportunity stratum `s(i)` | `opportunities/strata.py::OpportunityStrataMapper` | Coarse region × ToD × weekday/weekend; freeze on val |
| F1.3 | Target group `h(i)` | `data/target.py::GroupMapper` | Eval spatial × target time block |
| F1.4 | `Ŷ_i = f_θ(i; C_i^dep)` | `models/common_ndmf.py::CommonNDMF` | **Ban:** client_id embedding |
| F1.5 | `ϖ_i^tar = μ_{h(i)} · ν_{i\|h(i)}^tar` | `data/target.py::TargetBuilder.atom_mass` | Nonnegative + normalize |
| F1.6 | `π_{k,s}^tar = Λ_s^tar · λ_{k\|s}^tar` | `data/target.py::client_stratum_mass` | Controlled λ or T-Drive warm-up estimate |
| F1.7 | `π_{k,i}^tar = π_{k,s(i)}^tar · ν_{i\|s(i)}^tar` | `data/target.py::client_atom_mass` | |

---

## 2. Windows and selection

| ID | Symbol / definition | Planned code | Notes / bans |
|----|---------------------|--------------|--------------|
| F2.1 | Window `W_r = [T_r, T_{r+1})` | `training/window_runner.py` | θ fixed inside window |
| F2.2 | Risk set `R_{k,r}` before outcomes | `simulation/observation_generator.py` | Pre-outcome |
| F2.3 | `O`, `p_obs = P(O=1 \| X_obs, hist)` | `propensity/observation.py` | **Ban:** Y, current error, future in `X_obs` |
| F2.4 | `E_r = {k : buffer ≠ ∅}` | `simulation/event_trace.py` | Register before usable outcome |
| F2.5 | `U_{k,r}` usable indicator | `simulation/usable_generator.py` | Keep U=0; never drop |
| F2.6 | `q` usable propensity | `propensity/usable.py` | **Ban:** realized delays, arrival time, post-arrival staleness, update vector/norm/loss gain |
| F2.7 | Usable set `A_r ⊆ E_r` | `training/window_runner.py` | |

---

## 3. Design ratio and stage-1 correction

| ID | Symbol / definition | Planned code | Notes |
|----|---------------------|--------------|-------|
| F3.1 | General `ζ^o_{k,r,i}` | `correction/design_ratio.py` | Full two-factor form |
| F3.2 | Main: `ζ̂_{k,r,s} = π^tar_{k,s} / max(π̂^opp_{k,s,r}, π_min)` | `correction/design_ratio.py::zeta_hat_stratum` | Within-stratum exchangeability default |
| F3.3 | EMA `C^opp`, `π̂^opp` | `opportunities/estimator.py` | **Lagged** only; forgetting `ρ_opp` |
| F3.4 | `a = min{a_max, ζ̂ / max(p̂_obs, p_min)}` | `correction/hajek.py::raw_weights` | |
| F3.5 | `m_{k,r,g} = Σ_i O a 1{h(i)=g}` | `correction/hajek.py::group_mass` | |
| F3.6 | `m_{k,r} = Σ_g m_{k,r,g}` | `correction/hajek.py::total_mass` | Target-equivalent mass — **≠** ESS |
| F3.7 | Hájek `ā = O a / m` | `correction/hajek.py::normalized_weights` | |
| F3.8 | `c_{k,r,g} = m_{k,r,g} / m_{k,r}` | `correction/hajek.py::composition` | |
| F3.9 | `n_eff = m² / Σ(O a)² = 1/Σ ā²` | `correction/effective_sample_size.py` | Test identity; never swap with `m` |

---

## 4. Local objective and normalized update

| ID | Symbol / definition | Planned code |
|----|---------------------|--------------|
| F4.1 | `F̂^H = Σ_i ā · ½ (f_θ − Z)²` | `training/client.py::local_objective` |
| F4.2 | `u = (θ_s − θ^{(E_loc)}) / (γ_r E_loc)` | `training/client.py::normalized_update` |

---

## 5. Lagged variance and stage-2

| ID | Symbol / definition | Planned code | Notes |
|----|---------------------|--------------|-------|
| F5.1 | `v = S̄²_{r⁻} / max(n_eff,1) + v_floor` | `metrics/variance.py` + aggregator state | Current-window var → **next** window only |
| F5.2 | `d = min{d_max, 1/max(q̂, q_min)}` | `correction/second_stage.py::d_weight` | |
| F5.3 | `b = m · d` | `correction/second_stage.py::two_stage_mass` | |
| F5.4 | `β̂ = b / Σ_{j∈A_r} b_j` | `correction/second_stage.py::beta_hat` | β≥0, Σβ=1 |

---

## 6. Target debt and P2

| ID | Symbol / definition | Planned code | Notes / bans |
|----|---------------------|--------------|--------------|
| F6.1 | `M_r = [c_{k,r}]_{k∈A_r}` | `aggregation/debt.py` / P2 inputs | |
| F6.2 | `ω_r = M_r α_r` | `aggregation/debt.py` | |
| F6.3 | `Q_{r+1} = [Q_r + η_r(μ − ω_r)]_+` | `aggregation/debt.py::update_debt` | Empty window: no θ/Q/S_R update |
| F6.4 | P2: `−QᵀMα + (λ_g/2)‖Mα−μ‖² + (λ_β/2)‖α−β̂‖² + (λ_v/2)αᵀVα + λ_s τ̄ᵀα` | `aggregation/p2_cvxpy.py` | Convex; CLARABEL primary |
| F6.5 | `1ᵀα=1`, `0≤α≤ᾱ`, `‖α‖₂²≤1/Ē` | `aggregation/feasibility.py` | `ᾱ=min(1,max(α_max,1/K))`; `Ē=min(E_min,K)` |
| F6.6 | `λ_β>0`, `λ_g ≥ max_server_lr` | config validation | |
| F6.7 | **Ban:** P2 uses current `u` coords/norm/dir for own weight | `tests/.../test_p2_not_using_current_update` | α then aggregate |
| F6.8 | `θ_{r+1} = θ_r − η_r Σ α_k u_k` | `training/server.py` | One update per active window |

---

## 7. Theory diagnostics

| ID | Symbol | Planned code |
|----|--------|--------------|
| F7.1 | Effective pair `Π̂` | `metrics/distribution.py` |
| F7.2 | RAVEN: `w=ā` | same |
| F7.3 | `Δ_group = ‖ω̂−μ‖_1` | same |
| F7.4 | `Δ_pair = ‖Π̂−π^tar‖_1` | same |
| F7.5 | `Δ_{c-s}` | same (esp. T-Drive) |
| F7.6 | `avg_δ_group`, `avg_δ_ref` | same |
| F7.7 | `debt_normalized = ‖Q_R‖_1/S_R` | `metrics/debt.py` |
| F7.8 | Prefix: `‖ω̄_r−μ‖_1 ≤ 2‖Q_r‖_1/S_r` (tol 1e-8) | `metrics/debt.py` + G5 |
| F7.9 | `ε_reach(B)` | `metrics/reachability.py` |

---

## 8. Risks and RMSE

| ID | Symbol | Planned code | Notes |
|----|--------|--------------|-------|
| F8.1 | `RMSE_μ` with `ϖ̃^tar` | `metrics/accuracy.py` | |
| F8.2 | `RMSE_ρ` with **atomic** `ρ̃^arr` | `metrics/accuracy.py` | **Ban:** group-level arrival substitute |
| F8.3 | `r̂^arr_i = Σ_k π̂^opp ν̂^opp p̂ q̂` then normalize | `metrics/accuracy.py::arrival_intensity` | Frozen models |
| F8.4 | `Gap_mis = RMSE_μ − RMSE_ρ` | `metrics/accuracy.py` | |

---

## 9. Client measurement (controlled)

| ID | Symbol | Planned code |
|----|--------|--------------|
| F9.1 | `Z* = Y + b + ε` | `data/*` generators |
| F9.2 | noise `0.05·train_std`; bias ratios `{0,0.1,0.2,0.4}`; main `Δ_cal=0` | scenario configs |

---

## 10. Method → formula usage

| Method | ζ/p (ā,m) | q/d/β | Inst. P2 | Debt Q |
|--------|-----------|-------|----------|--------|
| Central-All / Central-Delivered | — | — | — | — |
| FedAvg-Window | raw counts | — | — | — |
| FedAsync-Window | raw·e^{−κτ} | — | — | — |
| TimeAlign-Agg | — | — | stale align | — |
| Local-Hajek | ✓ | — | — | — |
| TwoStage-Hajek | ✓ | ✓ α=β̂ | — | — |
| Inst-Cal | ✓ | ✓ | full; Q≡0 | — |
| Debt-Cal | raw c | — | group+debt | ✓ |
| RAVEN-MCS | ✓ | ✓ | full | ✓ |
| RAVEN-SimOracle | oracle ζ/p + MC q | ✓ | full | ✓ |

Ablations: w/o Design, Obs, Use, Inst, Debt, Ref, Var, Stale; No Forget; Current-Var (**diagnostic only**).

---

## 11. Hard-gate ↔ formula checklist

| Gate | Focus |
|------|--------|
| G0 | Schema, hashes, split, train-only scale, fleet separation |
| G1 | EventTrace hash identity |
| G2 | F2.1 / F6.8 window freeze + one update |
| G3 | F3.4–F3.9, F5.2–F5.4 weights |
| G4 | F6.4–F6.6 P2 |
| G5 | F7.8 debt prefix bound |
| G6 | Balanced no-harm (empirical) |
| G7 | SimOracle ordering on ζ/p/q error and Δ_pair / Δ_{c-s} |

---

## 12. Leakage keyword denylist (E0.6)

Forbid in `q` / usable feature names:  
`realized`, `arrival`, `future`, `update_norm`, `update_value`, `actual_delay`

---

## 13. Maintenance

After each implementing phase: mark IDs IMPLEMENTED, link unit tests, record teacher-approved deviations only in `ISSUES.md`.
