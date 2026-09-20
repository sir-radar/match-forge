# StatsBomb La Liga point-in-time prerequisite scope — 2026-09-09

## Scope

This record follows the lifecycle-publication scope correction for the existing
StatsBomb La Liga 2015/16 publication:

```text
Dataset version: 670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot: 01a08471-f763-7787-80ca-4293316b7e44
Lifecycle claims: 380
```

No source resource, normalized file, source snapshot, dataset version,
canonical match identity, score, provider event ID, or event index was changed.

## Kickoff prerequisite

The existing approved domestic Spain policy is:

```text
Claim version: statsbomb-spain-local-kickoff-v1
Country: Spain
Timezone: Europe/Madrid
tzdata: 2026.3
```

The new immutable route is:

```bash
football resolve kickoff \
  --dataset-version 670662d6-6ed7-5fa1-ba3c-1cfd561e524f \
  --source-snapshot 01a08471-f763-7787-80ca-4293316b7e44
```

It resolved the existing exact competition fact at each lifecycle knowledge
cutoff, required an already-approved domestic policy, and preserved the fixed
Sprint 2/EPL resolver unchanged.

| Check | Count |
| --- | ---: |
| Canonical matches | 380 |
| Kickoff eligible | 380 |
| Rejected | 0 |
| Published kickoff claims | 380 |
| Chronological kickoff batches | 333 |

A repeated identical invocation returned `verified_existing` with the same 380
claims.

## Corner prerequisite

The existing label contract remains:

```text
statsbomb-pass-type-61-corner-v1
Pass id/name: 30 / Pass
Pass-type id/name: 61 / Corner
```

The new immutable route is:

```bash
football resolve corners \
  --dataset-version 670662d6-6ed7-5fa1-ba3c-1cfd561e524f \
  --source-snapshot 01a08471-f763-7787-80ca-4293316b7e44
```

It requires the lifecycle claims bound to the same dataset/source pair and the
registered physical checksum before reading each normalized Parquet file.

| Check | Count |
| --- | ---: |
| Canonical matches | 380 |
| Corner-label eligible | 380 |
| Rejected | 0 |
| Published labels | 380 |
| Exact qualifying corner-pass events | 3,841 |

A repeated identical invocation returned `verified_existing` with the same 380
labels. Corner labels remain lifecycle-bound post-match outcomes and are not
added to forecast contexts.

## Structural alignment

```text
Lifecycle claims: 380
Kickoff claims:   380
Corner labels:    380
Three-way intersection: 380
```

## Point-in-time qualification

```text
POINT_IN_TIME_SUITABILITY: FAIL
```

The two prerequisite publishers support the dataset and published complete
records. The remaining failure is in the existing point-in-time provider: it
filters kickoff claims to the fixed Sprint 2 policy
`statsbomb-england-local-kickoff-v1` and `Europe/London`. The published La Liga
claims correctly use `statsbomb-spain-local-kickoff-v1` and `Europe/Madrid`, so
the provider sees zero eligible La Liga kickoffs.

Changing that fixed point-in-time kickoff-contract selection would be a
separate point-in-time contract/scope decision. It is not made by this bounded
prerequisite-publication route.

## Verification

```text
Focused explicit lifecycle/kickoff/corner scope integration test: PASS
Fresh-database storage integration suite: PASS (84 tests)
CLI parser tests: PASS
Lint: PASS
Type checks: PASS
make check: PASS
```

Protected EPL outcomes were not accessed. The admission population was not
reused; shared-pace admission, DCv3 diagnostics, candidate fitting,
authoritative Sprint 2 evaluation, promotion, and Phase 3 work were not run.
