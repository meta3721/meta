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

## Dataset provenance (design brief)

| Dataset | Role | Source note |
|---------|------|-------------|
| SensorScope | Main controlled | EPFL/Zenodo |
| U-Air | Main controlled | U-Air / MSR urban air |
| NSW Traffic Volume | Main controlled | Transport for NSW / Data.NSW |
| T-Drive-Speed | Trace-consistent mobility | MSR T-Drive sample |

**Traffic stop rule:** need quality report first; prefer ≥60 stations, ≥720 continuous hours; hard floor ≥30 stations × 336 hours. If unmet → stop and report; PEMS-BAY only after teacher approval to change paper dataset text.

## Layout note

- Design brief sketches package root as `raven/`.
- Cursor instruction mandates `src/raven_mcs/` (and richer module split).
- **Decision:** follow Cursor instruction layout (`src/raven_mcs/`); keep empty top-level `raven/` unused or remove in Phase 1.
