# Source Documents (V2.3)

**Workspace:** `D:\Cursor\raven.mcs`

## Authority order

When sources conflict, resolve in this order unless the teacher explicitly overrides:

1. **`RAVEN-MCS_V2.3_Cursor_实验执行指令.txt`** — binding implementation constitution for Cursor (gates, CLI, tests, phase order, math→code duties).
2. **`RAVEN_MCS_2026_7_26_.pdf`** — paper system model, algorithm, and theory quantities that code must match.
3. **`RAVEN-MCS_V2.3_实验设计方案.docx`** — detailed experiment plan (RQ1–RQ6, data sources, Traffic quality thresholds, timeline).

Machine-readable extracts (for search only; not paper artifacts):

- `docs/_ref_paper_extract.txt`
- `docs/_ref_design_brief_extract.txt`

## Document roles

| Document | Role |
|----------|------|
| Paper PDF | Defines *what* RAVEN-MCS is: two-stage selection, windowed async, design ratio + Hájek + usable IPW, target debt + P2, target-risk theory |
| Design DOCX | Defines *how to prove* claims: Layer A/B/C, G0–G7, E0–E9, RQ1–RQ6, dataset provenance, acceptance checklist |
| Cursor TXT | Defines *how Cursor builds* the repo: phases, hard gates, formula tests, no result-faking, reporting format |

## Research questions (from design brief)

| RQ | Question | Primary evidence |
|----|----------|------------------|
| RQ1 | Does target-risk misalignment exist? | RMSE_ρ vs RMSE_μ across bias scenarios |
| RQ2 | Does full RAVEN improve deployment target risk? | RMSE_μ, Tail RMSE, Δ_pair/Δ_c-s, Δ_group |
| RQ3 | Are components necessary? | Ablations |
| RQ4 | Robust under misspec / ID boundary? | drift, truncation, weak support, Δ_cal, hidden confounding |
| RQ5 | Do theory quantities match measurements? | debt bound, reachability, pair discrepancy, variance proxy |
| RQ6 | Is overhead acceptable? | bytes, compute, P2 time, memory, time-to-RMSE |

## Dataset provenance (design brief → Phase 2B freeze)

| Dataset | Role | Exact download / artifact | Frozen matrix (seed 26001) |
|---------|------|---------------------------|----------------------------|
| SensorScope | Main controlled | Zenodo `https://zenodo.org/records/2654726` → `Sensorscope.zip` md5 `4bbed2bbd48e535bc2877cad339fbbd6` | 55 stations × 312 hours |
| U-Air | Main controlled | MSR Urban Air page → `Data-1.zip` (`Data/airquality.csv`) | 36 stations × 264 hours |
| NSW Traffic Volume | Main controlled | TfNSW station ref CSV + `road_traffic_counts_hourly_permanent.zip` | 43 stations × 720 hours (hard floor met; preferred ≥60 stations not met) |
| T-Drive-Speed | Trace-consistent mobility | MSR T-Drive sample zips `06.zip`…`014.zip` | 500 m / 30 min grid; reference/client fleets 30/70 |

Provenance JSON: `data/raw/<dataset>/provenance.json`. Column/unit rules: `docs/DATA_DICTIONARY.md`.

**Traffic stop rule:** quality report first (`station_quality_report.csv`); prefer ≥60 stations × ≥720 continuous hours; hard floor ≥30 × 336. If hard floor unmet → stop and report; PEMS-BAY only after teacher approval to change paper dataset text.

## Reconciliations requiring explicit treatment

- **Seed taxonomy:** preserve the superset `master`, `data`, `opportunity`,
  `observation`, `event`, `model`, `solver`, `bootstrap`, `mc_oracle`; derive
  unspecified streams deterministically from `master` and hash all resolved
  values.
- **E1 conflict:** the DOCX and binding execution instruction disagree on the
  method set and 2%/3% no-harm threshold. The execution instruction takes
  precedence provisionally, but E1 remains blocked pending teacher confirmation
  (ISSUE-012).
- **Formula ambiguity:** typography-sensitive DOCX/PDF conflicts stop the
  affected experiment for teacher review; source priority is not permission to
  silently change a mathematical definition.

## Layout note

- Design brief sketches package root as `raven/`.
- Cursor instruction mandates `src/raven_mcs/` (and richer module split).
- **Decision:** follow Cursor instruction layout (`src/raven_mcs/`); keep empty top-level `raven/` unused or remove in Phase 1.
