# Owner decision: approve Phase 3A Evaluation V2 acceptance thresholds — 2026-09-21

```text
Decision ID: APPROVE_PHASE3A_EVALUATION_V2_ACCEPTANCE_THRESHOLDS_V1
Status:      APPROVED
Recorded at: 2026-09-21T10:27:12Z
Owner:       repository owner / sir-radar
Map:         phase3a-xg-for-evaluation-v2-freeze
Ticket:      Owner decision: freeze acceptance thresholds
```

This append-only record captures the repository owner's direct answer to the
Wayfinder decision ticket. The owner approved Decision 3 in
`docs/governance/phase3a-xg-for-evaluation-v2-freeze-proposal.md` without
amendments.

## Comparison and primary threshold

Evaluate exactly one `PHASE3A_MINIMAL_XG_FOR_V1` candidate against one compatible
goals-only reference on identical frozen targets and raw distributions. Define:

```text
delta = challenger loss - reference loss
```

Lower is better. The only confirmatory primary is joint score-matrix log loss.
Both conditions must pass:

```text
point delta <= -0.010 nats per match
paired 95% CI upper bound < 0
```

## Predictive and calibration guardrails

Freeze these paired 95% CI upper-delta limits:

```text
1X2 log loss:      <= +0.020
1X2 Brier score:   <= +0.010
1X2 RPS:           <= +0.010
total-goal CRPS:   <= +0.020
```

Freeze calibration worsening relative to the same reference:

```text
abs(challenger intercept) - abs(reference intercept) <= 0.050
abs(challenger slope - 1) - abs(reference slope - 1) <= 0.100
```

Missing, invalid, or non-comparable calibration cannot pass. No unauthorized
post-hoc calibrator change may repair a result.

## Uncertainty and segment contract

```text
Method:       paired moving-block bootstrap
Unit:         kickoff batch
Block length: 10 chronological kickoff batches
Replicates:   2,000
Interval:     percentile 95%
Seed:         20260921
Multiplicity: none; one candidate and one confirmatory primary
```

Blocking segment dimensions are competition-season, observed result, reference
favourite-probability band, reference expected-total-goals band, history-depth
band, and data-coverage band. A segment is blocking at `n >= 100`; its joint
score-matrix log-loss 95% CI upper delta must be `<= +0.050`. Smaller and
unavailable broader-roadmap segments are descriptive only. Definitions, band
boundaries, and membership must be frozen before outcome access.

## Result dispositions and precedence

- `PROMOTE_CANDIDATE`: primary point and interval, all predictive and
  calibration guardrails, every blocking segment, integrity checks, and
  resource limits pass.
- `RETAIN_CHAMPION`: integrity passes; no rejection condition occurs; primary
  improvement is not met.
- `REJECT`: any predictive guardrail, calibration limit, or blocking segment
  fails.
- `DEFER_INSUFFICIENT_DATA`: corpus or reportable targets fail frozen minimums
  before outcomes are inspected.
- `TERMINAL_ROUTE_FAIL`: leakage, protected-target access, artifact mutation,
  hash mismatch, nondeterministic replay, invalid probabilities, unauthorized
  input, or post-outcome policy change.

Integrity failures take precedence. Insufficient-corpus checks occur before
outcome exposure. A passing primary cannot override a rejection condition.
No result may change this decision mapping.

The proposal file SHA-256 at approval was:

```text
3d7d636f14295a919973c1075077dbd1c13c22605f818cd3827ee2c079307379
```

## Reconciliation note

The owner's answer described Decision 2 as subject to separate approval. That
status sentence was stale when recorded: Decision 2 was already approved by
`APPROVE_PHASE3A_EVALUATION_V2_CORPUS_POLICY_V1`. The current approved Decision
2 remains authoritative. This does not change any Decision 3 threshold or rule.

## Explicit non-decisions

This decision does not authorize implementation, opening Evaluation V2 targets
or outcomes, Evaluation V2 execution, candidate promotion, Rust implementation,
or production changes. The independent corpus, experiment budget, accountable
owner, complete pre-registration, and separate Evaluation V2 run authorization
remain required.
