# E2 Source-to-Protocol Mapping

This mapping distinguishes source-backed content from protocol choices requiring teacher authorization.

## Design DOCX RQ1 / §13.3
- Source wording: Target-risk misalignment evidence; compare RMSE_rho and RMSE_mu across six bias scenarios.
- Frozen interpretation: E2 tests risk misalignment, not RAVEN superiority.
- Ambiguity: None
- Proposed resolution: Freeze objective and metrics now.
- Teacher authorization required: False

## Design DOCX §8.5 / §13.3
- Source wording: Balanced, opportunity-only, observation-only, usable-only, complete-aligned, complete-counteracting.
- Frozen interpretation: Six mutually named scenarios with auditable enabled stages.
- Ambiguity: Existing YAML lacks stage-direction implementation fields.
- Proposed resolution: Use provisional structural registry; authorize numeric generator encoding before formal runs.
- Teacher authorization required: True

## Design DOCX §13.3
- Source wording: FedAvg-Window, FedAsync-Window, TimeAlign-Agg.
- Frozen interpretation: Strict primary has exactly these three methods.
- Ambiguity: Binding Cursor source additionally names diagnostic methods/RAVEN.
- Proposed resolution: Keep Local-Hajek/TwoStage-Hajek separate extended diagnostic; exclude RAVEN.
- Teacher authorization required: True

## configs/experiment/E2_misalignment.yaml
- Source wording: SensorScope; 20 seeds; num_windows: 300.
- Frozen interpretation: D1 and 20/300 are recommended, not authorized formal settings.
- Ambiguity: Layer-B source lists three controlled datasets.
- Proposed resolution: Present D1/D2/D3 and recommend D1 primary + D2/D3 extensions.
- Teacher authorization required: True

## Design DOCX §15 / Appendix A
- Source wording: 20 paired seeds; two-sided Wilcoxon; Holm; 95% confidence interval.
- Frozen interpretation: Pre-register paired unit and tests prior to formal results.
- Ambiguity: Effect-size convention has multiple source expressions.
- Proposed resolution: Use paired median and relative difference; report rank-biserial descriptively.
- Teacher authorization required: False

## E2 entry instruction §J
- Source wording: SensorScope, seed 29001, 10 windows, six scenarios, strict methods, formal=false.
- Frozen interpretation: Exactly 18 structural canaries; no performance claim.
- Ambiguity: None
- Proposed resolution: Schema-only EventTrace artifacts.
- Teacher authorization required: False

## E2 entry instruction §I
- Source wording: Formal execution requires teacher protocol authorization.
- Frozen interpretation: This entry stops READY_FOR_TEACHER_PROTOCOL_AUTHORIZATION.
- Ambiguity: No numeric E2 misalignment threshold supplied.
- Proposed resolution: Do not define outcome threshold or formal stopping result.
- Teacher authorization required: True
