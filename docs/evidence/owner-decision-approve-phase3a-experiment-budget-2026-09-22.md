# Owner decision: approve Phase 3A experiment budget — 2026-09-22

```text
Decision ID: APPROVE_PHASE3A_EVALUATION_V2_EXPERIMENT_BUDGET_V1
Status:      APPROVED
Recorded at: 2026-09-22T02:44:54Z
Owner:       repository owner / sir-radar
Map:         phase3a-xg-for-evaluation-v2-freeze
Ticket:      Owner decision: freeze experiment budget
```

The repository owner approved Decision 4 in
`docs/governance/phase3a-xg-for-evaluation-v2-freeze-proposal.md` without
amendments. The approval freezes the experiment search, execution, resource,
retry, and budget-exhaustion limits. It does not authorize a run.

## Approved budget

```text
Candidate families:          1, xG-for only
Reference models:            1 compatible goals-only reference
Feature variants:            1
History windows:             1, fixed last-10; no additional decay
Hyperparameter search:       prohibited
Optimizer starts:            1 fixed start
Optimizer iteration limit:   existing reference limit, capped at 1,000

Development full replays:    at most 2, cumulative
Development CPU:             16 CPU-hours total
Development wall time:       8 hours total
Development peak memory:     16 GiB
Development temporary data:  20 GiB

Authoritative logical runs:  1
Evaluation CPU:              64 CPU-hours total
Evaluation wall time:        24 hours total
Evaluation peak memory:      16 GiB
Evaluation temporary data:   40 GiB
Bootstrap replicates:        2,000, included in evaluation budget
```

The existing reference objective, numerical contract, score-tail behavior,
low-score correction, approved feature mathematics, bootstrap settings, and
acceptance thresholds remain unchanged. No alternative candidate, reference,
feature, window, initial value, or optimizer start is authorized.

An exact technical retry remains within the one logical run only when no
outcome or metric has been exposed, all inputs and hashes are unchanged, and
the accountable owner records the reason. It does not reset resource limits.
After metric exposure, retry requires a new owner decision and experiment ID.

Budget exhaustion is fail-closed. It cannot yield a passing predictive result,
relax checks, add compute or candidates, or authorize a rerun. A non-outcome
dry benchmark may support an explicit prospective owner budget amendment before
the authoritative run; observed results cannot justify an amendment.

The proposal file SHA-256 at approval was:

```text
0e622e17d3e5f1b5b242e22c6d093cb52983490ad8a3cfe17d8d69bc0914e80a
```

## Unresolved result-taxonomy conflict

Decision 4 permits `INCONCLUSIVE` for budget exhaustion. Approved Decision 3
lists five result dispositions and reserves `DEFER_INSUFFICIENT_DATA` for corpus
or target insufficiency before outcome access. Compute exhaustion is not
automatically insufficient data. An explicit owner decision must settle whether
`INCONCLUSIVE` is a new disposition, a separate run status without predictive
disposition, or another exact fail-closed mapping. No existing decision is
silently changed. The pre-registration cannot freeze until this is resolved.

## Explicit non-decisions

This decision does not authorize model implementation or fitting, access to
protected Sprint 2 EPL populations, Evaluation V2 target/outcome access or
execution, Rust work, promotion, or production changes. Exact authoritative
corpus membership, accountable ownership, full pre-registration freeze, and
separate run authorization remain required.
