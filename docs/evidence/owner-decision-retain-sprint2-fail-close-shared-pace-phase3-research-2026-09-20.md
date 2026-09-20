# Owner decision: retain Sprint 2 FAIL, close shared pace, authorize Phase 3 research — 2026-09-20

```text
Decision ID: RETAIN_SPRINT2_FAIL_CLOSE_SHARED_PACE_AND_AUTHORIZE_PHASE3_RESEARCH_V1
Recorded at: 2026-09-20T04:58:42Z
Map: governance-status-reconciliation-2026-09-11
```

This is an append-only repository-owner governance decision. It modifies no
prior evidence file, gate, threshold, corpus, or evaluation result.

## Decision

1. Sprint 2 V1 remains `FAIL` permanently. Its frozen corpus, policy,
   thresholds, metrics, bootstrap semantics, and retained evidence are
   preserved unchanged.
2. `DCV3_SHARED_MATCH_PACE_MIXTURE_V1` is closed as
   `TERMINAL_ROUTE_FAIL` / `CLOSED` under its existing contract. Its
   corrected deterministic feasibility `PASS` and frozen training-only
   admission `FAIL` both remain preserved in their retained evidence.
3. Prohibited: retries of the shared-pace admission route, later-fold
   continuation (`70/10`, `80/10`, `90/10`), post-result tuning, admitting
   `kappa=0` as success, changing admission semantics, and any use of the
   frozen 280 Sprint 2 targets.
4. Phase 3A is authorized for RESEARCH ONLY: one bounded, minimal,
   leakage-safe xG goal-model hypothesis using approved and qualified
   Tier-A event/shot data.
5. The research authorization does NOT authorize xT, VAEP, player models,
   lineup models, ensembles, simulation work, authoritative Evaluation V2
   scoring, or model promotion.
6. Design and pre-registration of a new Evaluation V2 multi-season,
   multi-competition policy and corpus are authorized. Evaluation V2 is a
   new versioned experiment and must never reuse or extend the frozen
   Sprint 2 280-target corpus.
7. An authoritative Evaluation V2 run requires a separate owner decision
   after its corpus, policy, thresholds, coverage requirements,
   references, and evidence contract are frozen.
8. Model promotion requires a separate governance event after
   authoritative evidence exists. No automatic promotion is authorized.
9. Phase 1C core-coverage qualification, provider/resource coverage
   mapping, and project-status reconciliation continue in parallel.
10. Data, evaluation, and predictive signal are prioritized before
    substantial simulator/Rust expansion.

## Preserved state

```text
Sprint 2:                 FAIL / RETAIN_FAIL_AND_STOP
Challenger authorized:   false
Model promoted:           false
Sprint 2 corpus:          frozen 280 targets, unchanged
Gate policy:              Sprint2BaselineGatePolicyV1, unchanged
```

## Boundaries

This decision records authorization state only. It starts no Phase 3A
implementation, no Evaluation V2 scoring, and no promotion. Historical
evidence files are unchanged; this record is the only new artifact of the
decision itself.
