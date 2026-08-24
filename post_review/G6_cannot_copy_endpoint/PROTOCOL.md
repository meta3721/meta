# G6 protocol — pre-declared external endpoint that adapted FedAU/ObsUse cannot copy

Date: 2026-08-24  
Status: **DESIGN ONLY. Not authorized to run TEST. No numbers in this file.**  
Default method: Path B `raven_gated` (SensorScope = `raven`, U-Air = `raven_wo_design`). Frozen. Do not retune Design, mixture weight, or P2 on this endpoint.

This gate answers one reviewer question: G2 already showed **non-inferiority** on 4-block WorstGroupRMSE. That is not a win, and \(\Delta_{group}\)/\(\Delta_{c\text{-}s}\) are P2-objective compliance. To move 6→7, gated RAVEN must **win** a new endpoint that (i) is frozen before any new TEST look, (ii) is not inside the P2 objective, and (iii) still loses when FedAU/ObsUse are given the same public \(\mu\).

## 0. What this gate is not

| Forbidden as G6 primary | Why |
|---|---|
| 4-block WorstGroupRMSE | Already G2 primary; VAL+TEST looked; NI not a win |
| \(\Delta_{group}\), \(\Delta_{c\text{-}s}\) | P2 directly optimizes composition; “objective compliance” |
| B1 144/220 fine-group worst-group | Different estimand; already-negative audit; do not recycle |
| Any block chosen by scanning G2 `RMSE_block0..3` | TEST leakage / endpoint shopping |
| Turning Design on for U-Air because \(g^\star\) likes it | Path B freeze |
| Official-FedAU-wins-both then silent drop | That **lowers** the paper; must be recorded |

G2 `per_seed.csv` already stores `RMSE_block0..3`. Those columns exist. **Do not open them to pick \(g^\star\).** \(g^\star\) is identified from train-side public objects only (Section 2). After \(g^\star\) is written to `GSTAR.json`, scoring may use the matching `RMSE_block{g*}` column.

G2 already consumed one TEST look (30011–30020) on WorstGroup. G6 is a **new pre-registered family**, not a replacement. If G6 fails, G2 NI remains; do not shop a third endpoint.

## 1. Claim under test

**C6.1 (unique-endpoint win).** On the pre-registered under-served-block prediction error \(\mathrm{RMSE}_{g^\star}\), Path B gated RAVEN is better than adapted `fedau_window` **and** adapted `obsuse_window` by the pre-registered win rule (Section 5), on VAL and TEST.

**C6.2 (cannot copy).** The win in C6.1 does not close when the same public \(\mu\) is given to FedAU/ObsUse at training time (`fedau_mu_window`, `obsuse_mu_window`), and does not close when existing same-trace copies are scored: TwoStage-Hajek (Design+O+U, no P2), `raven_wo_design` (O+U+P2, no Design), FedAvg (none).

C6.1 without C6.2 is “they were not trying.” C6.2 without C6.1 is a mechanism study with no deployment win. Both are required to claim uniqueness.

## 2. Primary endpoint (frozen now)

Same 4 UTC six-hour blocks \(g\in\{0,1,2,3\}\) as G2 (`RepeatableTimeOfDayMapper` on `absolute_time`). Same \(\mu\)-weights \(w_i\) as G2 / RMSE\(_\mu\).

Identify one **under-served block** from **train-side public objects only**:

\[
g^\star
=
\arg\max_{g\in\{0,1,2,3\}}
\bigl(\mu_g - \pi^{opp,4}_g\bigr).
\]

- \(\mu_g\): the public 4-block deployment target already used by P2 (dataset-level, seed-independent).
- \(\pi^{opp,4}_g\): frozen generator opportunity, marginalized onto the same 4 blocks (dataset-level, seed-independent). This is the Design-side \(\pi^{opp}\), not test \(\mu\), not G3 `mu_test`, not realized TEST arrival.
- Ties: lowest \(g\) index. Write the pair \((\mu,\pi^{opp,4},g^\star)\) to `GSTAR.json` **before** scoring any method.

\[
\mathrm{RMSE}_{g^\star}
=
\sqrt{
\frac{\sum_{i:h_4(i)=g^\star} w_i(\hat Y_i-Y_i)^2}
{\sum_{i:h_4(i)=g^\star} w_i}
}.
\]

**Why this is external.** P2 minimizes a composition residual \(\|M_r\alpha-\mu\|\) (and debt), not \(\mathrm{RMSE}_{g^\star}\). Prediction error on one block is not in the solver objective.

**Why FedAU has no reason to copy it.** `fedau_window` uses usable-update IPW only. It never sees \(\mu-\pi^{opp}\). Worst-group can coincide with “intrinsically hard afternoon dynamics” that every backbone shares; \(g^\star\) is the **allocation** gap, not the hardness gap. G2 already showed those two are not the same question.

**Why ObsUse has no reason to copy it.** `obsuse_window` corrects \(O\) and \(U\) given opportunity. It does not reallocate aggregation toward \(\mu\). On U-Air the paper default is `raven_wo_design` = ObsUse + P2 + debt; uniqueness vs ObsUse on U-Air is **only** P2+debt. SensorScope uniqueness also includes Design.

**Reload-only.** No new training for C6.1. Reload sealed `checkpoints/final.pt` exactly as G2. After `GSTAR.json` exists, score `RMSE_block{g*}` from a **new** script that reads G2 artifacts; do not hand-pick columns.

## 3. Secondary endpoints (pre-declared, not rescue levers)

Computed only if C6.1 VAL is scored. **Cannot replace** \(\mathrm{RMSE}_{g^\star}\) after a fail.

| ID | Endpoint | Role |
|---|---|---|
| S1 | 4-block \(\mathrm{RMSE}_g\) for all \(g\), plus G2 WorstGroup | Context; already exists |
| S2 | Train-threshold utility \(U_\tau=\sum_i w_i \mathbf{1}\{|Y_i|\ge\tau\}(\hat Y_i-Y_i)^2\) under the same \(\mu\)-weights; \(\tau=\) train-split 90th percentile of \(\|Y\|\) (absolute, split=`train` only) | TMC-facing task utility; report, do not promote |
| S3 | 8-group (4 blocks × weekday/weekend) \(\mu\)-weighted worst-group | Finer public partition; **not** P2’s \(h(i)\); not B1 144/220 |

S2/S3 stay supplement unless C6.1 wins and they agree in direction. If they disagree, they are limitations, not a new primary.

## 4. Baseline / copy matrix

All adapted, same backbone / EventTrace / seeds / local epochs / update budget. Any method that uses a target may use **only** the same public \(\mu\) as RAVEN.

### 4.1 Already sealed (reload; first copy diagnostics)

| Method | What it copies | Missing vs gated |
|---|---|---|
| `raven_gated` | paper default | — |
| `raven` (full Design) | U-Air diagnostic only | Path B off on U-Air |
| `raven_wo_design` | ObsUse + P2 + debt | Design |
| `fedau_window` | participation / usable IPW | R, O, Design, P2, \(\mu\) |
| `obsuse_window` | O+U Hajek | Design, P2 |
| `twostage_hajek` | Design+O+U target-risk IW | P2, debt |
| `fedavg_window` | unweighted control | everything |

Interpretation if C6.1 is a win:

- gated \(\approx\) TwoStage on SensorScope \(\Rightarrow\) P2 is not the source; uniqueness vs IW fails.
- gated \(\approx\) `raven_wo_design` on SensorScope \(\Rightarrow\) Design is not needed for this endpoint.
- gated \(\approx\) ObsUse on U-Air \(\Rightarrow\) expected risk (default has no Design); uniqueness vs ObsUse then lives only on SensorScope.
- gated \(\approx\) FedAU on both \(\Rightarrow\) C6.1 fails.

### 4.2 Informed-copy (new training; required for C6.2)

Give the baseline the public 4-block \(\mu\) **at aggregation time**, not at evaluation time.

| Method | Construction | Fairness rule |
|---|---|---|
| `fedau_mu_window` | `fedau_window` usable weight \(\times\) the public \(\mu_g\) of the update’s 4-block | same \(\mu\) as P2; no test \(Y\); no Design \(\zeta\); no P2 solver |
| `obsuse_mu_window` | `obsuse_window` Hajek weight \(\times\) the same \(\mu_g\) | same; still no Design, no P2 |

Do **not** implement “FedAU + full P2.” That is `raven_wo_design` with a FedAU-style \(U\) term, i.e. a RAVEN ablation, not a copy of FedAU.

FedCure-class and official (unadapted) FedAU are **not** in G6 P0. Official FedAU is Section 8 (P3, can lower the paper).

### 4.3 Optional later (not G6 default)

- T-Drive method ranking / 1-seed canary: G3 forbade this unless separately authorized. Same \(g^\star\) formula on T-Drive public \(\mu\) vs real-\(R\) \(\pi^{opp,4}\). Path B stays frozen. No RMSE ranking in the paper unless that authorization exists.
- Spatial hold-out stations: new split, leakage risk, not this gate.

## 5. Win rule (frozen before TEST)

Same seed banks as G2:

- VAL: 30001–30010  
- TEST: 30011–30020, **one** look after VAL  
- Scenario: Complete-aligned only  
- MPID = 0.5% (same as G2)

Let \(d_m = 100\cdot(\mathrm{RMSE}_{g^\star}^{\text{gated}} - \mathrm{RMSE}_{g^\star}^{m})/\mathrm{RMSE}_{g^\star}^{m}\). Negative = gated better.

**Win (C6.1) on a dataset:** mean paired \(d_m \le -0.5\%\) vs `fedau_window` **and** vs `obsuse_window`, on VAL **and** on TEST.

**No-harm on the other dataset:** mean paired \(d_m \le +0.5\%\) vs both (gated not worse by more than MPID).

**Family success:** win on at least one of {SensorScope, U-Air} and no-harm on the other.

Report paired Wilcoxon + Holm on the two strong-baseline comparisons per dataset. The decision rule is the mean-relative threshold, not “\(p>0.05\).”

VAL must also confirm every method has a finite \(\mathrm{RMSE}_{g^\star}\) on all 10 seeds.

**C6.2** (informed-copy): after C6.1 family success, the same win rule must still hold vs `fedau_mu_window` and `obsuse_mu_window` on the dataset that carried the win. If the informed-copy closes the gap (mean \(d_m > -0.5\%\) vs either informed baseline), verdict is `G6_COPYABLE` — unique-endpoint win exists but is copyable by \(\mu\)-weighted participation. Do not claim sequential R/O/U uniqueness.

## 6. Stop conditions (do not rescue)

| If | Then | Do not |
|---|---|---|
| VAL C6.1 fails | `G6_RECORDED_NEGATIVE`; still write TEST as a sealed report if already authorized, else skip TEST | change \(g^\star\); promote S2/S3; retune Path B; scan `RMSE_block*` |
| VAL wins, TEST fails | `G6_VAL_ONLY`; do not headline TEST | peek then redefine \(g^\star\) |
| C6.1 succeeds, C6.2 fails | `G6_COPYABLE` | call it “cannot copy” |
| Official FedAU later wins structure **and** \(\mathrm{RMSE}_{g^\star}\) / RMSE\(_\mu\) | paper score risk 6→5/4; record limitation | drop the official run from the draft |
| Informed-copy training diverges / NaN | abort that method; do not loosen the win rule | swap in a friendlier hybrid |

No new IW estimator. No Path A revival. No `POLICY_MAP["raven"]` edit. Sealed E1–E4 and `tdrive_protocol_seal_r1/` untouched. New code only under `post_review/G6_cannot_copy_endpoint/`.

## 7. Execution order

| Step | Action | Cost | Authorization |
|---|---|---|---|
| 0 | This PROTOCOL + empty `DECISION.md` | none | done by writing |
| 1 | Compute \(g^\star\) from train-side \(\mu,\pi^{opp,4}\) → `GSTAR.json` | low | required before any score |
| 2 | VAL score C6.1 + 4.1 copy diagnostics (reload G2 ckpts / `RMSE_block{g*}`) | low | ask before running |
| 3 | If VAL family success: one TEST look | low | ask after VAL |
| 4 | If C6.1 family success: train `fedau_mu_window` / `obsuse_mu_window` (same seeds, VAL then TEST) | high | ask after step 3 |
| 5 | S2/S3 supplement tables | low | only if step 3 succeeded |
| 6 | T-Drive canary / official FedAU | very high | **separate** written authorization |

## 8. Official FedAU (P3, can hurt)

Only if the user explicitly authorizes a new training stage. Official (paper-faithful) FedAU on the same EventTrace is the hostile copy: if it wins both composition **and** \(\mathrm{RMSE}_{g^\star}\) or RMSE\(_\mu\), the nearest-neighbor story collapses. Pre-register that outcome as a limitation, not a retune trigger.

## 9. Deliverables (when run is authorized)

```
post_review/G6_cannot_copy_endpoint/
  PROTOCOL.md          (this file; do not edit after GSTAR.json)
  GSTAR.json           (mu, pi_opp_4, g_star, source hashes)
  VAL_GATE.json
  tables/per_seed.csv
  tables/paired_gstar.csv
  tables/copy_matrix.csv
  DECISION.md
  CLAIM_ADDON.md
```

Do not write paper numbers from this design. Do not compile Overleaf from TBD cells.

## 10. Claim ceiling if the gate later succeeds

1. Allowed: gated RAVEN wins pre-registered \(\mathrm{RMSE}_{g^\star}\) vs adapted FedAU and ObsUse; informed \(\mu\)-hybrids still lose (if C6.2 holds).
2. Allowed: \(g^\star\) is the train-side under-served 4-block, not “worst-group,” not B1 fine groups.
3. Forbidden: “best worst-group”; “FedAU cannot use \(\mu\)” (they can; that is why C6.2 exists); “unbiased prediction”; quoting \(C_1\) as the reason \(\mathrm{RMSE}_{g^\star}\) drops.
4. Forbidden: changing Path B because U-Air \(g^\star\) favored full Design.
5. If only SensorScope wins and U-Air is no-harm vs ObsUse: say so. Do not average datasets into one “unique win.”
