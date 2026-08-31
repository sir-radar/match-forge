# Team Elo baseline

Sprint 2 starts with a deterministic team-level Elo baseline. It produces a measurable,
versioned signal before more complex score and player models are introduced.

## Contract

Each completed match supplies canonical match, competition, home-team, and away-team UUIDs; an
explicit timezone-aware kickoff; and non-negative integer scores. Matches are processed by kickoff
time and canonical match UUID. Duplicate matches and two matches for one team at the same timestamp
fail closed.

For home rating `R_h`, away rating `R_a`, and home advantage `H`, expected home score is:

```text
E_h = 1 / (1 + 10 ^ ((R_a - R_h - H) / 400))
```

Actual home score is `1` for a win, `0.5` for a draw, and `0` for a loss. The symmetric update is:

```text
margin = 1                                  when goal difference <= 1
margin = 1 + ln(goal difference)            otherwise
delta = K * competition_weight * margin * (actual_home - E_h)
R_h' = R_h + delta
R_a' = R_a - delta
```

Before a later match, an inactive team's previous rating regresses toward the configured initial
rating. With elapsed days `d` and half-life `L`:

```text
R_pre = R_initial + (R_previous - R_initial) * 0.5 ^ (d / L)
```

Time decay may be disabled. Competition weights default to `1`. Opponent strength is represented
by the rating difference inside the expected-score calculation.

## 1X2 probability adapter

Elo expected score is not a home-win probability. Sprint 2 execution projects pre-match home and
away ratings through `EloOneXTwoAdapterV1`, a Davidson-style three-outcome model. It applies the
configured Elo home advantage and uses draw propensity `0.5` under algorithm version
`elo-davidson-1x2-v1`:

```text
w_home = exp(log(10) * (R_h + H) / 400)
w_away = exp(log(10) * R_a / 400)
w_draw = 0.5 * sqrt(w_home * w_away)
P(outcome) = w_outcome / (w_home + w_draw + w_away)
```

This V1 value is frozen before the authoritative evaluation run. It is configuration and artifact
lineage, not a result selected after seeing evaluation scores. Changing it creates a different fit
identity.

## Versioning and storage

`EloConfig` includes every baseline parameter. Its canonical JSON SHA-256 and lowercase model
version identify one immutable model contract. Reusing a version with different configuration
fails.

`football.team_elo_history` stores one post-match row per model version, team, and canonical match,
including the pre-match rating, post-match rating, expected score, actual score, opponent, side, and
timestamp. Publication is transactional and serialized per model version. An identical retry
verifies existing rows; different values for an existing identity fail instead of overwriting
history. Composite foreign keys require the competition and both teams to belong to the canonical
match.

`PostgresEloHistory.rating_at` returns only the latest rating at or before an explicit timezone-aware
cutoff. Dataset construction for evaluation must use this point-in-time boundary and must never read
future ratings.

## Verification boundary

Unit tests fix the formulas, ordering, decay, configuration identity, and invalid-input behavior.
Fresh PostgreSQL integration tests cover migration replay, model registration, immutable publication,
idempotent retries, canonical foreign keys, and point-in-time lookup.

The raw walk-forward executor and immutable artifact/forecast publication are implemented, but the
authoritative operator run and phase-gate evidence remain pending. Probability calibration remains
a separate challenger layer. The Dixon–Coles score baseline is documented in
[Dixon–Coles goal baseline](dixon-coles.md).
