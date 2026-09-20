# StatsBomb La Liga lifecycle-completion contract research — 2026-09-09

## Scope and boundaries

This is the one authorized, read-only contract investigation following the
La Liga diagnostic-dataset requalification failure. It inspected the current
lifecycle implementation, StatsBomb parsing and normalization, validation,
the lifecycle schema, Sprint 2 point-in-time decisions, and retained raw and
canonical data.

It did not publish a claim, alter source or dataset bytes, alter a production
contract, run DCv3 diagnostics, fit a challenger, run an evaluation, reuse the
admission population, or access a frozen target outcome.

The protected EPL target outcomes are not part of this investigation. The only
EPL material used is already-retained, metadata-only lifecycle evidence:
match counts, terminal-event counts, and claim counts.

## Current v1 contract and data path

`python/football/src/football/forecasting/lifecycle.py` defines
`statsbomb-terminal-event-score-v1`. For every normalized event dataset file,
it requires:

- exactly one scored match observation at the dataset acquisition cutoff;
- one source event resource and one normalized event file with exact lineage;
- validator v3 status `passed` or `warnings`;
- maximum event period `2`; and
- exactly **two period-2** provider event types named `Half End`.

The `Half End` count is deliberately filtered by `period = 2`. It is not a
count of all `Half End` events in a match. The final score in the claim is read
from `match_observations.home_score` and `away_score`; the lifecycle publisher
does not derive it from terminal events.

`python/football/src/football/ingestion/statsbomb_contracts.py` parses raw
events without reducing lifecycle events. `python/football/src/football/normalization/statsbomb_events.py`
requires unique provider event IDs and unique event indexes, preserves order by
source index, and retains the complete raw event object as
`provider_payload_json`. Thus the four-event observation is in the immutable
source and canonical output; canonicalization does not manufacture a second
pair.

The existing point-in-time decision requires completed history and conservative
completion ordering. It defines Sprint 2 targets as regulation-90 and directs
exclusion when completion cannot be proven. `docs/lifecycle-claims.md` already
limits v1 to regulation-only matches and says extra time and shootouts require
a reviewed claim version.

## Deterministic La Liga sample

Selection was declared before inspecting the raw payload: the lexicographically
first canonical La Liga match ID in source snapshot
`01a08471-f763-7787-80ca-4293316b7e44`, then all `Half End` events ordered by
source `index`. The selected canonical match is
`01a08230-a2e8-7bbf-80dd-17ddd5ec206c`, provider match `265839`.

Its four raw `Half End` events are:

| Period | Index | Provider event ID | Minute / second | Timestamp | Team | Possession / possession team | Play pattern | Related event |
| ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2021 | `49105ce5-9323-4e4a-a263-89ecaf102d01` | 45 / 8 | `00:45:08.240` | Barcelona | 79 / Sevilla | Regular Play | `749ee9d4-374c-4aa1-a5d7-94cd2274eb99` |
| 1 | 2022 | `749ee9d4-374c-4aa1-a5d7-94cd2274eb99` | 45 / 8 | `00:45:08.240` | Sevilla | 79 / Sevilla | Regular Play | `49105ce5-9323-4e4a-a263-89ecaf102d01` |
| 2 | 3840 | `fe4cb3dc-b28a-4c18-8238-613e67d9e42c` | 92 / 6 | `00:47:06.533` | Barcelona | 184 / Barcelona | Regular Play | `59d27460-686a-4efc-b3bf-bd5cfe148d4d` |
| 2 | 3841 | `59d27460-686a-4efc-b3bf-bd5cfe148d4d` | 92 / 6 | `00:47:06.533` | Sevilla | 184 / Barcelona | Regular Play | `fe4cb3dc-b28a-4c18-8238-613e67d9e42c` |

Every event has type ID/name `34` / `Half End`, `duration: 0.0`, no location,
and no terminal score field. The related-event links are reciprocal within each
same-period, same-timestamp, adjacent-index pair. This is two team-specific
records for halftime and two team-specific records for full time, not four
full-time records or duplicate provider IDs.

The sample match observation is `available`, has canonical score `2-1`, and
has no source timezone or UTC kickoff instant. Its raw events contain one
Sevilla goal and two Barcelona goals before the period-2 terminal pair. That
agrees with the canonical score. This is an illustrative independent La Liga
score comparison only; the lifecycle claim itself relies on validator score
reconciliation, not on a terminal-event score.

## Season-wide retained evidence

For the La Liga 2015/16 source snapshot and normalized events dataset:

| Check | Result |
| --- | --- |
| Matches | 380 |
| All `Half End` events per match | `4: 380` |
| Period-2 `Half End` events per match | `2: 380` |
| Maximum event period | `2: 380` |
| Matches with duplicate provider event IDs | 0 |
| Period-2 terminal provider IDs unique per match | 380 / 380 |
| Period-2 terminal indexes unique per match | 380 / 380 |
| Distinct period-2 terminal timestamps per match | `1: 380` |
| Span between the two period-2 terminal indexes | `1: 380` |
| Matches satisfying every v1 data precondition (terminal pair, regulation maximum, one source resource, one scored observation at cutoff, one event file) | 380 / 380 |
| Published `statsbomb-terminal-event-score-v1` claims for this dataset | 0 |

The 0 claims are not evidence that the raw source fails the v1 terminal
predicate. `Sprint2LifecycleClaimPublisher.publish()` has no La Liga CLI scope:
without an argument it constructs `EvaluationCorpusV1()`, whose approved
provider competition/season are EPL `2` / `27`. The public CLI command is
named `resolve sprint2-lifecycle` and invokes that fixed Sprint 2 corpus. No
La Liga v1 claim publication was attempted or authorized.

The published La Liga validation run
`1780ec10-300c-5de0-90f5-df6acabea4eb` has warnings only: 9 out-of-bounds
locations, 126 impossible timestamps, 66 nonmonotonic position stints, and
447 unknown event types. It has no `SB_SCORE_INCONSISTENCY` finding. The
quality policy makes score inconsistency quarantining, while these four
categories are warnings with explicit limited-use actions.

## Governed comparison without protected outcomes

| Corpus | Dataset | Matches | All `Half End` per match | Period-2 `Half End` per match | Max period | v1 completed claims |
| --- | --- | ---: | --- | --- | --- | ---: |
| La Liga 2015/16 | `670662d6-6ed7-5fa1-ba3c-1cfd561e524f` | 380 | `4: 380` | `2: 380` | `2: 380` | 0 (not in fixed Sprint 2 command scope) |
| EPL 2015/16, retained Sprint 2 lineage | `d62b97d6-f39b-5f14-9773-61f57f7b677b` | 380 | `4: 380` | `2: 380` | `2: 380` | 380 |

No EPL target context, outcome, forecast, evaluation artifact, or distribution
was queried. The comparison establishes that the observed La Liga structure is
the same terminal-event structure already accepted under v1.

## Score and lifecycle semantics

The strongest currently retained evidence is the conjunction of the
period-2 terminal pair and the validator's independent score reconciliation.
The score validator derives goals from `Shot` events with outcome `Goal` and
from `Own Goal For`; it intentionally ignores the paired `Own Goal Against`
event and period 5. It compares those event-derived totals with the canonical
match-observation scores and quarantines a mismatch.

`match_status=available` is not a football-completion signal. The repository
explicitly treats it as event-data availability, so metadata cannot replace
terminal evidence. `Half End` events themselves contain no final-score field,
so terminal-timestamp/terminal-score equality cannot be an authoritative
criterion from this source without inventing a score representation.

## Candidate-rule and fail-closed analysis

### A. Deduplicated semantic period-2 `Half End` pair

A potential future rule could require exactly one logical terminal pair:
two unique provider IDs and indexes, same period-2 timestamp, adjacent indexes,
and reciprocal `related_events`, alongside existing validated score
reconciliation and `max_period = 2`. This matches the retained sample and
season-wide count/order facts. It is stronger than v1, which currently checks
only count and maximum period. Because it adds accepted/rejected evidence
semantics, it is a versioned-contract change, not a silent v1 edit.

### B. Terminal timestamp plus score equality

Rejected: terminal records have no score attribute. The source supports a
separate score-reconciliation check, not terminal-score equality.

### C. Completed match metadata plus terminal confirmation

Rejected as a replacement: the only observed status is `available`, which the
repository correctly defines as data availability rather than football
completion. It may remain lineage evidence but is not an authority for
completion.

### D. Accept exactly two or four terminal records

Rejected: the apparent four is the total across periods 1 and 2. V1 correctly
filters period 2 and already observes two. A `2 OR 4` period-2 rule would be
an unproven broadening that could accept malformed or duplicated terminal
records.

| Condition | Current v1 behavior | Semantic-pair candidate behavior |
| --- | --- | --- |
| 0 or 1 period-2 `Half End` | Reject | Reject |
| 2 | Accept if all other v1 lineage, score, validator, and max-period checks pass | Accept only if one coherent pair is also proven |
| 3, 4, or 5+ period-2 `Half End` | Reject | Reject |
| Four total, split as two in period 1 and two in period 2 | Accept | Accept |
| Duplicate provider ID or index | Rejected during parsing/normalization and quarantined by validation | Reject |
| Different terminal timestamps | V1 does not test this explicitly | Reject |
| Conflicting final score | Validator quarantines `SB_SCORE_INCONSISTENCY`; v1 requires a usable validator run | Reject |
| Terminal event outside period 2 | Ignored for terminal count; any period above 2 rejects through `max_period` | Reject |
| Period 3/4/5, extra time, or penalties | Reject through `max_period != 2` | Reject; another reviewed version is required |
| Abandoned or postponed metadata | Not explicitly classified by v1; missing scores or terminal evidence reject, but `available` is not a completion status | Fail closed unless a future version has an authoritative status policy |
| Missing match metadata | Missing scored observation, exact lineage, or validation evidence rejects | Reject |

The table identifies two v1 limitations for adversarial source shapes: it does
not require same terminal timestamps or reciprocal related-event links, and it
does not supply an authoritative abandoned/postponed status vocabulary. Those
limitations were not exercised by the La Liga source and cannot be corrected
silently under v1.

## Research conclusion

The previous La Liga requalification block conflated all `Half End` records
with the v1 period-2 predicate. The observed source is neither ambiguous nor a
canonicalization defect. It matches the already-accepted EPL terminal shape:
two paired halftime records and two paired full-time records, with the latter
two satisfying v1.

The existing v1 evidence remains scientifically usable for the observed,
regulation-only La Liga source. It is only partially fail-closed for unobserved
adversarial terminal shapes, which is a separate governance question. A future
semantic-pair hardening must be versioned as v2, not retrofitted into immutable
v1 claims.

## Non-actions

- Frozen 280 outcomes: not accessed.
- Existing admission population: not reused.
- Shared-pace admission: not rerun.
- DCv3 diagnostics: not run.
- Candidate challengers: not fit.
- Authoritative evaluation: not run or authorized.
- Production changes: none.
