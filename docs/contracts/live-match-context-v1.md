# Live Match Context V1

This contract stores pre-match availability, lineup, coach, and rest information without making
that information predictive. All active champion coefficients for these fields remain zero.

## Point-in-time rules

For target kickoff `K`, match and lineup history must have a kickoff before `K`. Records with a
`known_at` value must also satisfy the forecast knowledge cutoff. Same-kickoff matches are excluded.
Pre-match availability and lineup observations captured at or after kickoff are excluded.

Availability observations are fresh for four hours. A fresh, supported injury feed may produce
`ASSUMED_AVAILABLE_NO_REPORTED_ISSUE` for a player in the latest prior confirmed XI. Missing,
unsupported, restricted, or stale data produces `AVAILABILITY_UNVERIFIED`; it never proves fitness.

## PredictedLineupV1

The predictor repeats the latest eligible confirmed XI, preferring lineups under the current coach.
Its preference window is the latest ten eligible same-coach lineups. A known unavailable starter is
replaced by the highest-ranked eligible alternative at the same normalized position, then the same
position group. Goalkeepers can only replace goalkeepers. Missing slots are processed by fewest
candidates first, then original slot order. A player cannot fill two slots.

Candidate score for lineup index `i`, where zero is most recent:

```text
recency_weight = 0.85 ** i
preference_score = compatible_start_score + 0.25 * bench_score
```

Ties use compatible start count, most recent compatible start, total same-coach starts, then stable
MatchForge player ID. No randomness is used. Confidence is categorical (`HIGH`, `MEDIUM`, `LOW`),
not a probability.

Confirmed observations preserve earlier predictions and link to the prediction they supersede.
Accuracy telemetry compares the saved prediction with the confirmed XI; confirmation never changes
the earlier predicted record.

## Polling and provider behavior

Context polling is disabled by default. Injuries poll within 72 hours of kickoff, no more than once
per four hours. Lineups poll within 90 minutes, no more than once per ten minutes, and stop after both
teams are confirmed. Polling never occurs after kickoff. The job keeps a daily request reserve and a
per-run request cap. Provider failures do not fail normal fixture/result sync.

Explicit competition non-support is saved as `UNSUPPORTED_BY_COMPETITION`. Account access failures
are saved as `PLAN_RESTRICTION`. MatchForge does not scrape or silently substitute another provider.

## Forecast snapshots and revisions

`ForecastInputSnapshot` has separate hashes:

```text
predictive_input_snapshot_sha256
context_snapshot_sha256
```

The current champion ignores the new context fields. A context-only change therefore saves a new
context snapshot but does not create a forecast. A changed predictive input or model artifact creates
a new immutable forecast that links to its predecessor. Identical predictive inputs create no new
forecast. Official responses continue to use the champion forecast path; research and shadow models
cannot become official through this contract.
