# Temporal and point-in-time model

## Separate timelines

Historical source facts preserve distinct time dimensions:

- Football time: when a match or event occurred.
- Provider time: when the provider says information became available or changed.
- System knowledge time: when this system acquired and knew the representation.
- Valid time: domain interval during which a representation was true, when known.

System and valid intervals are half-open:

```text
[from, to)
```

`known_to IS NULL` means the provider-specific observation is currently known. It does not mean the fact remains true forever.

## Point-in-time predicate

The database exposes `football.known_at`:

```sql
known_from <= knowledge_cutoff
AND (known_to IS NULL OR known_to > knowledge_cutoff)
```

The supported Python boundary is `football.temporal.repository.PointInTimeRepository`. Callers must provide both canonical identity and provider identity; omitting the provider would make conflicting provider observations ambiguous.

Knowledge cutoffs must include a timezone. PostgreSQL stores system timestamps as `TIMESTAMPTZ`. Provider timestamps with uncertain timezone semantics retain raw text alongside parsed values.

## Current projections

`current_*_observations` views exist for operational current-state reads. They are convenience projections, not modelling inputs. Backtests and later feature builders must use an explicit knowledge cutoff.

## Correction example

```text
Snapshot A acquired Jan 1
Observation A known [Jan 1, Feb 1)

Snapshot B acquired Feb 1
Observation B known [Feb 1, ∞)
```

A cutoff before Feb 1 returns A. A cutoff exactly at Feb 1 returns B. Database exclusion constraints reject overlapping observations for the same canonical entity and provider.
