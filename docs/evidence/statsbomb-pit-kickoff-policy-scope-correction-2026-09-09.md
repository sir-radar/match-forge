# StatsBomb PIT kickoff-policy scope correction — 2026-09-09

## Authorized scope

This record requalifies only the point-in-time provider for the governed
StatsBomb La Liga 2015/16 dataset:

```text
Dataset version: 670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot: 01a08471-f763-7787-80ca-4293316b7e44
```

No lifecycle, kickoff, or corner-label publisher was invoked. No source data,
canonical identity, published claim, frozen EPL outcome, admission population,
forecast context, diagnostic, evaluation, or model artifact was changed.

## Corrected selection path

Before this correction,
`PointInTimeMatchDatasetProvider` in
`python/football/src/football/forecasting/dataset.py` bound every kickoff
lookup to the fixed England values:

```text
statsbomb-england-local-kickoff-v1
Europe/London
```

There was no generic provider-side policy selection. The provider now resolves
the exact published dataset/source pair's lifecycle-bound competition fact at
the requested knowledge cutoff, requires exactly one domestic country fact,
and obtains its policy from the existing explicit approved-policy registry in
`football.forecasting.kickoff`.

```text
England -> statsbomb-england-local-kickoff-v1 / Europe/London
Spain   -> statsbomb-spain-local-kickoff-v1 / Europe/Madrid
```

Every PIT kickoff query binds both the selected claim version and timezone.
Unknown, international, ambiguous, or unapproved country facts raise a
point-in-time provider error; there is no England fallback.

## Verification

Focused tests cover the preserved England binding, Spain selection, and
fail-closed unknown, international, and ambiguous scope facts. The canonical
ingestion integration fixture also constructs a Spain dataset and confirms
point-in-time completed history is recognized.

```text
ruff (changed provider/tests): PASS
mypy (changed provider): PASS
focused forecasting and kickoff tests: PASS (19)
fresh-database storage integration suite: PASS
make check: PASS
git diff --check: PASS
```

## Read-only La Liga PIT prerequisite dry-run

At knowledge cutoff `2026-09-10T00:00:00Z`, the provider selected:

```text
Claim version: statsbomb-spain-local-kickoff-v1
Timezone: Europe/Madrid
```

| Check | Count |
| --- | ---: |
| Canonical matches | 380 |
| Lifecycle recognized | 380 |
| Kickoff recognized | 380 |
| Corner labels recognized | 380 |
| Fully PIT-prerequisite eligible | 380 |
| Rejected | 0 |
| Eligible prior completed history at `2017-01-01T00:00:00Z` | 380 |

Rejection categories were empty. The read-only dry-run established the
governed kickoff instant, lifecycle completion ordering, score and corner-label
availability joins, and explicit football and knowledge cutoffs. It did not
construct forecast contexts or run DCv3.

```text
POINT_IN_TIME_SUITABILITY: PASS
```
