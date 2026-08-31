# Sprint 2 walk-forward target plan

`WalkForwardTargetPlanV1` freezes the authoritative prequential target universe before any model is
fitted. It is derived from the approved dataset/source pair and governed lifecycle/kickoff claims,
using a fixed retrospective knowledge cutoff.

## Eligibility

For each chronological kickoff batch, target eligibility uses only matches from earlier batches:

```text
competition history >= 100 completed matches
home-team history >= 10 completed matches
away-team history >= 10 completed matches
```

Every match in the current batch is tested against the same pre-batch state. Only after all target
decisions are frozen does the planner add that batch to team and competition history. One team
appearing twice in a batch is rejected as contradictory chronology.

The plan contains only `ForecastMatchContextV1` target fields plus prior-history counts. It contains
no scores, results, corner outcomes, shots, possession, or other post-match target facts.

## Outcome boundary

`PointInTimeMatchDatasetProvider.reveal_outcomes` is a separate call for explicit frozen target
UUIDs. It requires exact lifecycle, kickoff, dataset, corner-label, and knowledge-cutoff lineage and
returns `EvaluationMatchOutcomeV1` rows. The evaluator persists every forecast in a batch before
calling outcome reveal, then updates sequential state only for later batches.

Because Open Data does not establish original provider-availability timestamps, the approved
`retrospective-fixed-snapshot-v1` EPL corpus assigns completed regulation-time outcomes a
conservative availability time of kickoff plus two hours. Other knowledge modes retain the exact
governed claim availability time. Same-kickoff matches remain isolated in one batch, and closely
staggered earlier kickoffs do not enter history before that boundary.

## Immutable identity

`target_set_sha256` hashes the ordered label-free target contexts only. Dataset, source, knowledge,
feature, quality-policy, and minimum-history rules remain explicit in the containing target-plan
specification. The immutable JSON plan is validated by
`schemas/contracts/walk-forward-target-plan-v1.schema.json` and stored at:

```text
target-set=<target-sha256>/plan=<full-plan-sha256>/WalkForwardTargetPlanV1.json
```

The outer checksum identifies the forecast target universe. The nested full-plan checksum also
binds dataset specification and eligibility-history counts, so two plans with the same targets but
different evidence cannot collide. An identical publication verifies existing bytes rather than
replacing them.

## Current corpus evidence

For StatsBomb EPL 2015/16:

```text
Corpus matches:       380
Warm-up exclusions:   100
Eligible targets:     280
Eligible batches:     146
First target kickoff: 2015-10-31T13:45:00Z
Last target kickoff:  2016-05-17T20:00:00Z
Target-set SHA-256:   c5b9ff5860d9d00d55ab58fe3dc044d41d95af49501d27275fdc2e0831bff362
Outcome coverage:     280/280
```

Minimum observed target histories are exactly 10 home-team matches, 10 away-team matches, and 100
competition matches. This satisfies the 250-target Sprint 2 coverage prerequisite. It is not model
execution or predictive-quality evidence; the phase gate remains blocked at walk-forward execution.
