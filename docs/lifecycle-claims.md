# Match lifecycle claims

## Boundary

StatsBomb `match_status=available` means event data is available; MatchForge does not reinterpret it
as football lifecycle `completed`. Provider match observations therefore retain their exact status
and remain `lifecycle = 'unknown'` when no provider football-lifecycle fact exists.

`Sprint2LifecycleClaimPublisher` creates a separate immutable completion claim only when the
approved Sprint 2 corpus has stronger, mutually consistent evidence:

- one scored match observation available at the event dataset acquisition cutoff;
- one exact normalized dataset file and source event resource for the match;
- validator v3 status `passed` or `warnings`, so no quarantine or fatal score finding exists;
- maximum event period `2`; and
- exactly two period-2 `Half End` events, matching the paired terminal-event convention observed in
  the pinned corpus.

The rule is versioned as `statsbomb-terminal-event-score-v1`. It is deliberately limited to
regulation-only matches; extra-time and shootout matches require another reviewed claim version.

## Lineage and immutability

Each `match_lifecycle_claims` row binds:

- canonical match and exact match observation;
- event dataset version and source snapshot;
- event source resource and normalized dataset file;
- validation run;
- terminal period/count evidence;
- deterministic evidence JSON and SHA-256 identity; and
- `known_from`, equal to validation completion time.

The provider observation is never mutated. Identical publication verifies the existing claim. A
source correction, dataset change, validator change, or claim-rule change creates new immutable
evidence rather than rewriting a prior claim.

## Operator command

```bash
football resolve sprint2-lifecycle
```

The command publishes the complete approved corpus atomically. Partial corpus coverage, missing
terminal evidence, quarantined validation, ambiguous match metadata, or mismatched lineage fails the
whole transaction.

The Sprint 2 gate counts only `completed` claims with the approved claim version. It does not count
raw `available` provider statuses.

Lifecycle evidence does not invent timezone semantics. UTC chronology is a separate governed
boundary documented in [Match kickoff claims](kickoff-claims.md).
