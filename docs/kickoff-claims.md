# Match kickoff claims

## Boundary

StatsBomb Open Data supplies `match_date` and timezone-naive `kick_off` for the approved EPL
2015/16 corpus. MatchForge preserves those provider fields and leaves
`match_observations.kickoff_at = NULL`; it does not silently label local time as UTC.

`Sprint2KickoffClaimPublisher` creates a separate immutable UTC kickoff claim only when:

- every target has an approved lifecycle claim and exact match observation;
- local match date and local kickoff time are present;
- the exact competition observation identifies a domestic England competition; and
- pinned `tzdata 2026.3` maps the local time to one unambiguous `Europe/London` instant.

Nonexistent and ambiguous daylight-saving local times fail closed. Another country, international
competition, timezone, or timezone-data version requires a separately reviewed claim rule. The
current rule is `statsbomb-england-local-kickoff-v1`.

## Lineage and reproducibility

Each `match_kickoff_claims` row binds:

- canonical match, competition, and season;
- exact lifecycle claim and match observation;
- exact competition observation;
- preserved local date and time;
- `Europe/London`, `tzdata 2026.3`, and the exact TZif SHA-256;
- resolved UTC kickoff;
- deterministic evidence JSON and SHA-256 identity; and
- system knowledge time for the derived claim.

The checked-in runtime dependency supplies timezone bytes on every supported platform. Identical
publication verifies existing claims. Source, policy, or timezone-data changes create new evidence
instead of rewriting an existing claim.

## Operator command

```bash
football resolve sprint2-kickoffs
```

The command publishes the whole approved corpus atomically. Partial lifecycle coverage, missing
local time, ambiguous time, unsupported competition geography, or conflicting lineage fails the
transaction.

Point-in-time history and label-free forecast contexts consume exact approved kickoff claims. The
authoritative historical evaluation declares `retrospective-fixed-snapshot-v1` knowledge mode
because Open Data does not prove historical provider-availability timestamps.
