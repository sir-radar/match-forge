# Owner decision: finalize PitchAPI retrospective policy — 2026-09-24

```text
Decision ID: APPROVE_PITCHAPI_HISTORY_AND_EVALUATION_ARCHITECTURE_V1
Status:      APPROVED
Recorded at: 2026-09-24T06:30:08Z
Owner:       repository owner / sir-radar
Map:         phase3a-xg-for-evaluation-v2-freeze
```

## Approved

For `PITCHAPI_RETROSPECTIVE_EVALUATION_V1`:

- require at least 10 prior eligible appearances for each target team;
- do not use Sprint 2's 100-prior-competition-match rule as target eligibility;
- use exactly one development group;
- require at least three evaluation groups, two evaluation competitions, two
  evaluation seasons, and 500 exact eligible evaluation targets;
- keep development, evaluation, protected data, providers, and protocols
  isolated;
- treat 120 nominal matches only as an early screen;
- require immutable `PITCHAPI_SNAPSHOT_V1` data and Rust simulation;
- keep result identity and `cross_evaluation_robustness` separation unchanged.

The 100-match rule remains a historical training implementation constraint. It
may return only through a separate owner decision and is not part of this
PitchAPI evaluation policy.

## Not approved by this decision

Exact group roles, compatibility thresholds, acquisition option, request/retry
budget, raw acquisition, storage, corpus admission, preregistration, model
fitting, Rust execution, and evaluation execution remain unauthorized. All ten
unused PitchAPI attempts remain unavailable. StatsBomb Evaluation V2 remains
unchanged and independently awaits a response.
