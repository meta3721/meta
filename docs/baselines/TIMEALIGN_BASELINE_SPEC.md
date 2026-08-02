# TimeAlign-Agg baseline status

Status: `BASELINE_UNRESOLVED`

## Sources checked

- `configs/method/timealign_agg.yaml`;
- `docs/FORMULA_TO_CODE_MAP.md`;
- all repository reports and implementation plans mentioning TimeAlign;
- `TimeAlignAggregator` history available in this repository;
- a literature search for the exact name `"TimeAlign-Agg"`.

No primary paper, algorithm, equation, repository, or frozen protocol defines
an original mechanism under this name. The local descriptions only say
“staleness-aligned weights.” The baseline implementation consequently used

```text
alpha_k proportional to n_k exp(-0.1 tau_k)
```

which is exactly the existing FedAsync-Window implementation.

## Adaptation to Common-NDMF

No defensible adaptation can be specified until the original baseline source
or a teacher-approved replacement is supplied. Introducing update-direction
alignment, timestamp interpolation, or a different decay law here would invent
a baseline and would not be reproducible from the frozen V2.3 protocol.

## Difference from FedAsync

There is no difference in the current code. A controlled stale fixture must
therefore fail the method-difference gate.

## Required decision

The formal E1 remains blocked pending one of:

1. provide the original TimeAlign source/formula and freeze its parameters; or
2. remove TimeAlign from E1 and re-freeze the official method registry.

Neither decision is made by this semantic-seal implementation.
