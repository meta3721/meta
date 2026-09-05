# RAVEN-MCS public reproducibility bundle

This directory is the frozen public artifact for the TMC manuscript.
It lets a reader check the tabulated numbers, the paired seeds, the
target maps, the selection-protocol configs, and the EventTraces used
by the evaluation. It does not require GPU-scale retraining.

## What is in the bundle

- `PROTOCOL.json`: support-conditional Design rule, seeds, P2 lambdas, and the diagnostic coverage-audit constants.
- `configs/`: frozen target maps, opportunity strata, E2 run config, E3 source hashes, E4 one-factor spec.
- `eventtraces/`: E1 formal traces; E2 NSW-Traffic traces (20 seeds x 6 scenarios); E3 SensorScope / U-Air / Traffic traces (20 seeds).
- `tables/` and `figures/`: CSVs that generate the manuscript tables and figures.
- `certificate/`: coverage-stress audit records (diagnostic Gate, not the paper Design switch).
- `processed/`: processed atomic units for SensorScope, U-Air, and NSW-Traffic.
- `tdrive/`: opportunity-replay target and seed policy. T-Drive is not a method ranking.
- `verify.py`: SHA-256 check against `MANIFEST.csv`.

## Verify the bundle

```bash
python verify.py
```

The verifier hashes every listed file. It does not retrain models.

## Ranking versus replay

SensorScope and U-Air ranking uses a Complete-aligned selection protocol.
Protocol opportunity on those traces is always-on; the original station
records are not claimed to contain mobile clients. T-Drive is an
opportunity replay under real taxi mobility. It is not used to rank methods.

## Retraining (optional)

End-to-end 20-seed retraining is optional. It needs Python 3.11, the
`raven-mcs` package in the companion repository, the public raw datasets
(SensorScope, U-Air, NSW-Traffic, T-Drive; cited in the paper), and the
EventTraces in this bundle. FedAU-Window and ObsUse-Window are windowed
adaptations, not official reproductions of those systems.

Use the seeds in `PROTOCOL.json`. On SensorScope, Design is on. On U-Air,
Design is off. Do not treat the coverage Gate as the E3 method.

## Licenses

Upstream dataset licenses remain those of the public sources. Code in the
companion repository follows that repository's license. This bundle is a
research artifact of tabulated results, traces, and configs.
