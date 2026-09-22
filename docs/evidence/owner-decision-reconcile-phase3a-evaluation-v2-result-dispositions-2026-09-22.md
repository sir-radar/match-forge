# Owner decision: reconcile Phase 3A Evaluation V2 result dispositions — 2026-09-22

```text
Decision ID: RECONCILE_PHASE3A_EVALUATION_V2_RESULT_DISPOSITIONS_V1
Status:      APPROVED
Recorded at: 2026-09-22T03:15:50Z
Owner:       repository owner / sir-radar
Map:         phase3a-xg-for-evaluation-v2-freeze
Ticket:      Owner decision: reconcile result dispositions
```

The owner answered “Yes” to the explicit question whether `INCONCLUSIVE`
should be a separate run status for resource exhaustion, with no Decision 3
result disposition or passing result, while Decision 3's five dispositions
and thresholds remain unchanged. This resolves the conflict left open by the
approved acceptance-threshold and experiment-budget decisions. It does not
amend either decision's numeric values or create a sixth disposition.

## Approved mapping

- A run that exhausts its frozen resource budget without completing all
  required checks is `INCONCLUSIVE` at the run level. It receives **no**
  Decision 3 result disposition. Record the exhaustion reason, consumed
  resources, available integrity evidence, and whether any outcome or metric
  was exposed. Partial metrics cannot establish promotion or retention.
- Corpus or reportable-target insufficiency established **before** outcome
  inspection remains `DEFER_INSUFFICIENT_DATA`. Compute exhaustion alone is
  not insufficient data and cannot be relabelled as such.
- A known Decision 3 integrity failure remains `TERMINAL_ROUTE_FAIL` even if
  resources were also exhausted. `INCONCLUSIVE` cannot hide leakage,
  protected-target access, artifact mutation, hash mismatch, nondeterministic
  replay, invalid probabilities, unauthorized input, or a post-outcome policy
  change.
- Decision 4's exact technical retry remains within the same logical run only
  if no outcome or metric was exposed, inputs and hashes are unchanged, and
  the accountable owner records the reason. It does not reset cumulative
  limits. A retry after metric exposure requires a new owner decision and
  experiment ID. No automatic extra compute, omitted checks, relaxed
  threshold, candidate, or rerun is authorized.

Decision 3 continues to define exactly `PROMOTE_CANDIDATE`,
`RETAIN_CHAMPION`, `REJECT`, `DEFER_INSUFFICIENT_DATA`, and
`TERMINAL_ROUTE_FAIL`. Its primary metric, guardrails, calibration limits,
bootstrap settings, segment rules, and all numeric thresholds are unchanged.

The proposal file SHA-256 before recording this decision was:

```text
08b34a887d1851755fbcbfc343d426d7d487c0e1ab6287d4dd3ea023fcda0cc9
```

This decision resolves the result-disposition conflict only. Independent
men's source qualification and exact Evaluation V2 corpus membership remain
open. The complete pre-registration has not been approved or frozen. Model
implementation, protected EPL access, Evaluation V2 outcome access or
execution, Rust work, promotion, and production changes remain unauthorized.
Sprint 2 stays `FAIL`; published forecasts and goals-only baselines remain
unchanged.
