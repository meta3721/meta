# SAG G0 Implementation Audit

Verdict: **PASS**

- git: `b4af7a9dacf7c47243c67ad71b1ed4f0f51cf6b4`
- mode: `smoke`
- datasets: ['sensorscope']
- seeds: [30001]
- max_windows: 6

## Checks

- timing correct? **PASS**
- p_obs frozen before O? **PASS**
- q_use frozen before U? **PASS**
- B_r/A_r correct? **PASS**
- shared EventTrace? **PASS**
- no dataset-name Gate? **PASS**
- no forbidden Gate feature? **PASS**
- counterfactual audit valid? **PASS**
- No-Design zeta==1 with IPW/P2 on? **PASS**

## Assertion summary

```json
{
  "timing_correct": {
    "pass": true,
    "n": 18,
    "failures": []
  },
  "p_obs_frozen_before_O": {
    "pass": true,
    "failures": []
  },
  "q_use_frozen_before_U": {
    "pass": true,
    "failures": []
  },
  "b_a_sets": {
    "pass": true,
    "failures": [],
    "n_failures": 0
  },
  "shared_eventtrace": {
    "pass": true,
    "failures": []
  },
  "no_dataset_name_gate": {
    "pass": true,
    "failures": []
  },
  "no_forbidden_gate_feature": {
    "pass": true,
    "forbidden_hits": []
  },
  "counterfactual_audit_valid": {
    "pass": true,
    "failures": []
  },
  "nodesign_semantics": {
    "pass": true,
    "failures": []
  }
}
```
