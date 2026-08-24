# G6 decision

Date: 2026-08-24  
Verdict: **`G6_RECORDED_NEGATIVE`**

## What was executed

1. Froze \(g^\star\) from train-side public objects into `GSTAR.json` **before** any method scoring.
2. Scored VAL seeds 30001–30010 by reading G2 `RMSE_block{g*}` (reload only).
3. Stopped. TEST 30011–30020 was **not** opened. S2/S3 were **not** computed. `fedau_mu_window` / `obsuse_mu_window` were **not** trained. Path B unchanged.

## Frozen \(g^\star\)

| Dataset | \(g^\star\) | \(\mu_{g^\star}\) | \(\pi^{opp,4}_{g^\star}\) | gap \(\mu-\pi^{opp}\) | Next-largest gap |
|---|---|---|---|---|---|
| SensorScope | **2** (12:00–18:00 UTC) | 0.2258 | 0.1114 | **+0.1145** | block3 +0.0822 |
| U-Air | **3** (18:00–24:00 UTC) | 0.2830 | 0.1114 | **+0.1717** | block2 +0.1151 |

Tie-break was not used. Generator \(\pi^{opp,4}\) under-weights tail blocks \(\{2,3\}\) by construction (\(\theta=1.25\)). Public \(\mu\) is the sealed P2 artifact marginalized by `parse_time_block`, not G3 EventTrace `mu_test`.

## C6.1 VAL (primary)

Win rule: mean paired \(d_m\le -0.5\%\) vs `fedau_window` **and** `obsuse_window`. Negative = gated better. All methods finite on 10/10 VAL seeds.

| Dataset | vs FedAU | vs ObsUse | Win? | No-harm (\(\le+0.5\%\))? |
|---|---|---|---|---|
| SensorScope | **+0.05%** (CI −0.12, +0.23) | **+0.15%** (CI −0.03, +0.33) | no | yes |
| U-Air | **−0.44%** (CI −1.24, +0.36) | **−0.27%** (CI −1.09, +0.55) | no | yes |

Family success requires a win on at least one dataset and no-harm on the other. **Neither dataset won.** Holm \(p\) vs FedAU/ObsUse are all \(>0.4\). Decision uses the mean-relative rule, not \(p\).

U-Air vs FedAU (−0.44%) is close to MPID but does not meet \(\le-0.5\%\), and ObsUse is farther (−0.27%). Do not round this into a win.

## Why TEST was not opened

Protocol §6: VAL C6.1 fail → `G6_RECORDED_NEGATIVE`; skip TEST; do not change \(g^\star\); do not promote S2/S3; do not retune Path B; do not scan other `RMSE_block*`.

G2 already consumed a TEST look on WorstGroupRMSE. Opening G6 TEST after a VAL fail would be a second look with no pre-registered rescue path.

## Copy diagnostics (VAL, sealed methods only)

These are **not** C6.2 (informed-copy was not trained).

| Dataset | gated vs TwoStage | vs `raven_wo_design` | vs FedAvg | vs full `raven` |
|---|---|---|---|---|
| SensorScope | +0.03% | −0.003% | ~0% | 0% (gated **is** `raven`) |
| U-Air | **−9.17%** | 0% (gated **is** `raven_wo_design`) | **−7.68%** | **−7.56%** |

On SensorScope, \(\mathrm{RMSE}_{g^\star}\) is interchangeable across methods, including FedAvg. On U-Air, gated beats TwoStage / FedAvg / full Design by a wide margin — the same pattern as G2 RMSE\(_\mu\) / WorstGroup — but that does not beat adapted FedAU/ObsUse by MPID.

## Coincidence with G2 WorstGroup (SensorScope)

On every SensorScope VAL seed inspected for gated `raven`, \(\mathrm{RMSE}_{g^\star}=\mathrm{WorstGroupRMSE}\). So SensorScope \(g^\star=2\) **is** the G2 worst block. The G6 SS paired percentages vs FedAU/ObsUse are therefore identical to G2 VAL WorstGroup NI. This endpoint is not a new SensorScope question.

On U-Air, \(g^\star=3\) is **not** the worst block (gated VAL \(\mathrm{RMSE}_{g^\star}\approx1.058\) vs WorstGroup \(\approx1.15\)–1.27). The unique-endpoint construction did bite, and still missed the win rule vs FedAU/ObsUse.

## What this does not change

- G2 NI on 4-block WorstGroupRMSE remains the only external-endpoint statement.
- Path B default unchanged.
- Do not claim “cannot copy.” C6.2 was not run because C6.1 did not pass.
- Do not promote S2/S3. Do not shop 8-group or threshold utility as a new primary.
- Do not turn Design on for U-Air. Full Design is worse on this VAL \(\mathrm{RMSE}_{g^\star}\) (−7.56% gated better).

## Claim ceiling

See `CLAIM_ADDON.md`. Allowed paper sentence: a pre-registered under-served-block prediction endpoint was evaluated on VAL and did not beat adapted FedAU/ObsUse by the 0.5% rule; TEST was not opened.
