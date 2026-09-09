# StatsBomb canonical-event bundle batching correction — 2026-09-09

## Scope

This correction addresses the read-only performance diagnosis in
`statsbomb-canonical-event-staging-performance-2026-09-09.md`: canonical event
publication repeated the complete staging sequence once for each event resource.

The correction was developed in the isolated worktree
`/private/tmp/football-simulation-canonical-event-batching` on branch
`ft/canonical-event-bundle-batching`, using only temporary
`football_storage_test_<pid>` databases. The active La Liga publication remains
in `/Users/radar/Desktop/football-simutation` on
`ft/sprint2-diagnostic-research`, using database `football`; it was not
modified, restarted, signalled, or used for correction verification.

Base code SHA: `c733cc34be07009c8f5f1948123f075b35b63291`.

## Change

Old path:

```text
for each event resource
  _event_rows(resource)
  _publish_event_batch(rows)
```

New path:

```text
for each event resource
  collect _event_rows(resource)
_publish_event_batch(all_rows)
```

The parsed `StatsBombBundle` already retains all event resources and event
objects. The correction adds only a bounded list of the COPY row tuples for
that already-loaded bundle, then releases it after the one existing COPY/stage
sequence. It does not add a second event parse, a new data source, a chunking
contract, or a second transaction.

The stage table, COPY use, ANALYZE, publication SQL, indexes, mappings,
constraints, source lineage, and one-transaction boundary are unchanged.

## Structural performance evidence

| Property | Before | After |
| --- | ---: | ---: |
| `_publish_event_batch` granularity | one event resource | complete detail bundle |
| Expected La Liga calls (380 event resources) | 380 | 1 |
| Stage sequences per complete detail bundle | 380 | 1 |

The focused two-resource fixture instruments `_publish_event_batch` and proves
one call containing all four provider event IDs. The original call path was
one call per `MatchEvents` resource, so the test is a direct structural
equivalence/performance check; no arbitrary speed-up threshold is used.

## Logical equivalence and failure preservation

The focused fixture verifies, for two match event resources:

- one batch contains every logical event exactly once;
- four event catalog rows, four provider mappings, and four snapshot-scoped
  observations are published;
- each provider event identity is preserved;
- duplicate provider event identities across resources fail before source
  registration with the existing `CanonicalIngestionError`;
- the existing full canonical-ingestion integration suite passes on a fresh
  migrated database.

The fixture asserts the stable logical catalog/mapping/observation population
instead of physical generated IDs. Existing source acquisition canonicalizes
resource order before parsing, so this correction preserves its governed source
order rather than introducing a new ordering rule.

## Verification

- Focused one-bundle call, no-loss/no-duplication, and duplicate fail-closed
  coverage: PASS.
- Fresh-database canonical storage and ingestion integration suite: PASS.
- Ruff formatting and lint: PASS.
- Production mypy for `canonical.py`: PASS.
- `make check` with repository-pinned Go toolchain: PASS.
- Active publication database used by correction tests: NONE.

Dataset qualification is not implied by this correction. No optimized La Liga
publication was started; the original in-progress run remains the only active
La Liga publication.
