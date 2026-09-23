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
approved rules are `statsbomb-england-local-kickoff-v1` for the Sprint 2 EPL corpus,
`statsbomb-spain-local-kickoff-v1` for the diagnostic La Liga 2015/16 corpus, and
`statsbomb-italy-local-kickoff-v1` for isolated Serie A 2015/16 research qualification.
The Spain and Italy rules require domestic country facts and use `Europe/Madrid` and
`Europe/Rome`, respectively, with the same pinned `tzdata 2026.3` runtime and recorded
TZif checksum. The Italy authorization does not admit a corpus or authorize Evaluation V2.

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

For an already-published non-Sprint-2 StatsBomb dataset, publish through the
explicit immutable route:

```bash
football resolve kickoff --dataset-version <uuid> --source-snapshot <uuid>
```

The route requires the exact published normalized dataset/source pair and
complete lifecycle evidence from that pair. It selects only one existing
approved domestic policy from the exact competition fact at the lifecycle
knowledge cutoff. The fixed Sprint 2 command remains bound to its EPL corpus.

Point-in-time history and label-free forecast contexts consume exact approved kickoff claims. The
authoritative historical evaluation declares `retrospective-fixed-snapshot-v1` knowledge mode
because Open Data does not prove historical provider-availability timestamps.

For point-in-time selection, the provider resolves the domestic country from the exact published
dataset/source pair's lifecycle-bound competition fact at the requested knowledge cutoff. It then
requires exactly one approved policy and binds both its claim version and timezone in every
kickoff lookup. England resolves to `statsbomb-england-local-kickoff-v1` / `Europe/London`; Spain
resolves to `statsbomb-spain-local-kickoff-v1` / `Europe/Madrid`; Italy resolves to
`statsbomb-italy-local-kickoff-v1` / `Europe/Rome`. Unknown, international, or
ambiguous scope facts fail closed; the provider never falls back to the England policy.
