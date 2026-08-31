# Match corner labels

Sprint 2 corner outcomes are immutable derived labels, not mutations of provider observations or
pre-match forecast context. Run:

```bash
football resolve sprint2-corners
```

The resolver requires complete `statsbomb-terminal-event-score-v1` lifecycle coverage from one
validated normalized event dataset. It verifies each registered Parquet file against its physical
checksum before reading it. Publication is atomic and idempotent; an identical retry returns
`verified_existing`.

## Exact StatsBomb rule

One corner is counted only when all four provider fields agree:

```text
event type id: 30
event type name: Pass
pass type id: 61
pass type name: Corner
```

Text such as `play_pattern.name = From Corner` does not count. A partial ID/name match is a
vocabulary conflict and fails publication. Every qualifying event must have a unique canonical
event ID, the expected canonical match ID, and either the exact home or away canonical team ID.
Zero is a valid team count when the validated event stream contains no qualifying corner for that
team.

## Lineage and temporal boundary

Each `statsbomb-pass-type-61-corner-v1` row binds:

- canonical match, home team, and away team;
- exact scored match observation and completed lifecycle claim;
- dataset version, source snapshot, source resource, and dataset file;
- validator run and registered physical/logical Parquet checksums;
- ordered qualifying canonical event IDs and home/away counts.

The label's `known_from` equals its lifecycle claim's validated evidence time. Corner outcomes may
enter completed historical training/evaluation rows only after the applicable football and
knowledge cutoffs. They never enter `ForecastMatchContextV1`, so target outcomes remain
structurally unavailable before prediction.
