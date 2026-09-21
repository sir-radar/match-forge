# Owner decision: approve Phase 3A xG-for feature mathematics — 2026-09-21

```text
Decision ID: APPROVE_PHASE3A_MINIMAL_XG_FOR_V1_FEATURE_MATHEMATICS_V1
Status:      APPROVED
Recorded at: 2026-09-21T09:47:07Z
Owner:       repository owner / sir-radar
Map:         phase3a-xg-for-evaluation-v2-freeze
Ticket:      Owner decision: freeze feature mathematics
```

This append-only record captures the repository owner's direct answer to the
Wayfinder decision ticket. The owner approved Decision 1 in
`docs/governance/phase3a-xg-for-evaluation-v2-freeze-proposal.md` without
amendments.

## Decision

Freeze `MATCHFORGE_NPXG_FOR_LAST10_V1` as the only feature contract for
`PHASE3A_MINIMAL_XG_FOR_V1`:

- sum `shot.statsbomb_xg` for non-penalty Shot events in periods 1 and 2 by
  MatchForge team and match;
- use the previous 10 eligible team matches within the same season;
- require 10 prior matches and mark the target ineligible without fallback when
  that history is unavailable;
- compute the prior-only competition-season reference mean;
- use `log(team_last10_mean / competition_prior_mean)`;
- require both means to be finite and strictly positive;
- freeze each kickoff batch before revealing any same-batch outcome;
- reset at season boundaries and prohibit cross-season carryover.

Integrate the signal into the compatible goals-only reference using exactly one
shared coefficient:

```text
lambda_home_challenger = lambda_home_reference * exp(beta_xg_for * signal_home)
lambda_away_challenger = lambda_away_reference * exp(beta_xg_for * signal_away)

beta_xg_for domain:         [0, 1]
beta_xg_for initialization: 0.25
additional parameters:      exactly 1
```

Use the reference model's existing likelihood, optimizer, iteration limit,
tolerances, time weighting, identifiability constraints, score-tail rule, and
low-score correction. `beta_xg_for = 0` is a valid no-effect result. Invalid
means, non-convergence, invalid probabilities, and artifact reload mismatch
fail closed.

The proposal file SHA-256 at approval was:

```text
2e311979673d2259d947d9ad1ca9693a7a2a8e79597c5c2795de677d02820030
```

## Explicit non-decisions

This decision does not approve Decisions 2–5 and does not authorize:

- implementation or fitting before the complete pre-registration is frozen;
- xGA, shot-count, xG-per-shot, venue-split, opponent, game-state, penalty,
  alternative-window, decay, cross-season, regularization, or calibrator work;
- Evaluation V2 execution or result access;
- Rust implementation;
- candidate promotion or production changes.

Sprint 2 remains `FAIL`. Its EPL admission population and frozen 280 targets
remain inaccessible. Existing baselines, artifacts, forecasts, raw
probabilities, and terminal evidence remain unchanged.

## Dependencies

The feature mathematics must be incorporated into the complete Phase 3A
pre-registration after the remaining freeze decisions resolve. Implementation
remains blocked until that document has final IDs and hashes and the repository
owner explicitly approves and freezes it.
