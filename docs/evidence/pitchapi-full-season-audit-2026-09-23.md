# PitchAPI full-season technical audit — 2026-09-23

Status: `COMPLETED — TECHNICAL PARTIAL — EVALUATION V2 FAIL`

The owner-authorized audit combined hash-locked pilot aggregates with all 666
previously untested match-shot resources. Both refetched manifests matched the
pilot's manifest and deterministic selection hashes before sampled paths were
skipped. No raw provider response was retained.

## Coverage

| Check | Bundesliga 2023/24 | Ligue 1 2022/23 | Combined |
| --- | ---: | ---: | ---: |
| Manifest matches | 306 | 380 | 686 |
| Successful shot resources | 306 | 380 | 686 |
| Empty shot resources | 0 | 0 | 0 |
| Shots | 8,523 | 9,350 | 17,873 |
| Penalties | 101 | 143 | 244 |
| Regulation-period shots | 8,523 | 9,350 | 17,873 |
| Missing resources/fields | 0 | 0 | 0 |
| Malformed resources | 0 | 0 | 0 |
| Invalid xG values | 0 | 0 | 0 |
| Duplicate shot identifiers | 0 | 0 | 0 |
| Unknown periods/situations | 0 | 0 | 0 |
| Request failures | 0 | 0 | 0 |

The audit observed complete shot-resource availability for both season
manifests. Every observed shot had finite numeric pre-shot xG in `[0,1]`, a
recognized explicit period and situation, a valid provider identifier, and
team membership consistent with its fixture. Penalties were counted only from
exact `situation=Penalty` values.

No valid empty resource occurred, so the provider's live representation of a
genuinely shotless match remains unobserved. Synthetic tests cover the empty
versus missing distinction.

## Request accounting

- Authorized continuation: 668 base attempts plus at most 10 retries.
- Attempts used this run: 668.
- Retries: 0.
- Rate-limit responses: 0.
- Cumulative attempts: 692 of 702.
- Unused budget: 10 attempts.
- Minimum request-start interval: 1.000 seconds.
- Concurrency: 1.
- Acquisition duration: 11 minutes 12 seconds.
- Raw responses retained: no.

The failed direct-module launch occurred before credential loading and before
network access; it consumed zero API attempts.

## Disposition

Resolved technical coverage questions:

- exact 306- and 380-match manifest coverage;
- one successful shot resource per manifest match;
- finite bounded shot-level xG;
- explicit penalty, situation, and regulation-period fields;
- within-snapshot match, team, and shot identifier validity;
- no observed duplicate, malformed, missing, or unknown records;
- safe one-request/second operation without retries or rate limits.

Still unresolved and blocking Evaluation V2:

- permission for the required persistent immutable raw retention and reuse;
- upstream xG supplier, model identity, and version;
- proof that both seasons use one unchanged xG series;
- correction history, immutable revision identity, and prior-version access;
- identifier stability across provider rebuilds or revisions;
- point-in-time availability and reproducible historical snapshots;
- exact corpus target eligibility, independent-group membership, firewall
  hashes, and explicit corpus admission.

Technical status is therefore `PARTIAL`, with
`CROSS_SEASON_XG_SERIES_UNPROVED`. Evaluation V2 status remains `FAIL`, with
`EVALUATION_PERMISSION_OR_LINEAGE_UNPROVED`. Statistical similarity was not
used to infer model identity or consistency.

No ingestion, provider activation, corpus admission, model implementation,
Evaluation V2 execution, frozen-decision change, provider communication,
protected-data access, production forecast change, baseline removal, published
forecast mutation, or Rust requirement change occurred.

Machine-readable evidence:
`docs/evidence/pitchapi-full-season-audit-2026-09-23.json`.
