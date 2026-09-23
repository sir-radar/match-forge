# PitchAPI replacement live-audit pilot — 2026-09-23

Status: `COMPLETED — OWNER REVIEW REQUIRED`

The authorized replacement pilot completed without triggering a stop
condition. It validated two complete season manifests and twenty
deterministically selected match-shot resources. This is sample evidence only;
it does not establish full-season shot completeness.

## Transport preflight

The previous transport failure was reproduced inside the restricted sandbox:
DNS could not resolve `api.pitchapi.dev`. Outside that network boundary, DNS
returned IPv4 and IPv6 records, unauthenticated HTTPS reached the provider,
TLS certificate verification succeeded, HTTP/2 was negotiated, and the root
path returned the expected non-API `404`. No proxy environment or active system
proxy setting was observed. The likely failure category was local sandbox DNS
isolation, not a PitchAPI HTTP response.

Credential presence was confirmed without printing its value. No authenticated
request was used for transport preflight.

## Pilot result

| Check | Bundesliga 2023/24 | Ligue 1 2022/23 | Combined |
| --- | ---: | ---: | ---: |
| Manifest matches observed | 306 | 380 | 686 |
| Sampled matches | 10 | 10 | 20 |
| Successful shot resources | 10 | 10 | 20 |
| Empty shot resources | 0 | 0 | 0 |
| Shots | 277 | 270 | 547 |
| Penalties | 4 | 5 | 9 |
| Regulation-period shots | 277 | 270 | 547 |
| Invalid xG values | 0 | 0 | 0 |
| Missing fields/resources | 0 | 0 | 0 |
| Malformed resources | 0 | 0 | 0 |
| Duplicate shot identifiers | 0 | 0 | 0 |
| Unknown periods/situations | 0 | 0 | 0 |

All observed shots had finite numeric pre-shot xG within `[0,1]`, explicit
periods, recognized situations, valid provider identifiers, and fixture-team
membership. Penalties were identified only by exact `situation=Penalty`.

No valid empty shot resource appeared in this sample, so live empty-resource
behavior remains unobserved even though synthetic tests cover it.

## Request controls

- Attempts this run: 22.
- Retries this run: 0.
- Cumulative attempts: 24 of 702.
- Absolute attempts remaining: 678.
- Rate-limit responses: 0.
- Minimum request-start interval: 1.000 seconds.
- Concurrency: 1.
- Timeout: 30 seconds.
- Raw responses retained: no.

## Status and remaining audit budget

Technical status is `PARTIAL`, solely because PitchAPI's upstream xG model and
cross-season series identity remain unproved. Evaluation V2 status is `FAIL`
because permission, immutable retention, correction history, revision identity,
stable-ID policy, and xG-series lineage remain unproved.

Twenty sampled shot paths and both manifest paths succeeded. A continuation
that combines this immutable aggregate evidence with the remaining sample-free
audit needs:

- 2 manifest calls to reconstruct and verify the current season identities;
- 666 unsampled match-shot calls;
- 668 base attempts total;
- at most 10 retries within the remaining 678-attempt absolute ceiling.

The continuation must require both manifest hashes to equal this pilot's hashes
and must reproduce the same deterministic twenty-match selection hashes before
skipping those sampled shot paths. A manifest or selection hash mismatch must
stop rather than combine revisions.

This bounded route can complete per-match validation and aggregate counts, but
it cannot turn sample evidence into proof of provider model identity,
cross-season xG consistency, retention rights, correction policy, or stable
identifier policy. Those remain independent Evaluation V2 blockers.

No ingestion, corpus admission, provider activation, model implementation,
Evaluation V2 execution, production forecast change, protected-data access,
baseline removal, published-forecast mutation, or Rust requirement change
occurred.

Machine-readable evidence:
`docs/evidence/pitchapi-live-audit-replacement-pilot-2026-09-23.json`.
