# Phase 3A Serie A 2015/16 isolated qualification — 2026-09-22

Status: `PASS_WITH_WARNINGS` for one independent men's source group.
Evaluation V2 corpus membership: **not approved or frozen**.

The owner authorized the [research-only Italy policy and isolated publication](owner-decision-authorize-phase3a-serie-a-isolated-qualification-2026-09-22.md)
after the [pinned raw-source screen](phase3a-serie-a-2015-16-source-qualification-2026-09-22.md).
All publication and claim writes used database
`football_phase3a_serie_a_20260922` and data root
`.local/phase3a-serie-a-qualification-20260922`. The normal database was used
only for an identity-only, read-only overlap comparison.

## Exact source and dataset

```text
Provider scope:                statsbomb_open_data 12/27, men's Serie A 2015/16
Source Git SHA:               4b73468fc5b0f1950f9f66fada70ad3a4f9327cb
Pinned match-list SHA-256:    613cd3cc70699ba613cb1b3c27b4c8a01b0b5fa28415e09c928d020208905c7a
Original 761-file manifest:  2d0bb941dbec283118185b3bf5261184a6d16a118381348539703b089efd3944
Isolated catalog manifest:  fec76df71be0ff7c3b0350c9183916377fde1c5343eaf568a3e9cac8f760de2a
Isolated match manifest:    856a4b13c6386d79146de85eb9a719eef1437e5e81ab32b0f32b5e9c955cad82
Isolated detail manifest:   425a64df301fcf999d8e06eed4598a7ce45eb088ee8877257ebb7200de0e67dd
Detail source snapshot ID:  01a0c80e-8d2a-7b1b-9516-4a1f82a5e849
Dataset version ID:         8bfec1dd-5bf7-5162-b56a-7e63f77b0b88
Dataset manifest SHA-256:   760592efe5c8d6ce698105003b336f2c2849c00c74b3d6948fbec7c75eb7106d
Quality policy SHA-256:     7a772e2a9cb1131283b1c11d7ebb6bfb55a4eeb7137384868fd6ac457df2419b
```

`scripts/stage_phase3a_serie_a_isolated_source.py` checked each original
resource against the pinned source manifest before publishing three isolated
manifests. Its repeat run verified the same bytes and manifest hashes. The
existing canonical ingestion and dataset-integrity verifier then accepted
760 registered detail resources, 380 normalized event files, and 1,353,739
events. Dataset manifest and every file checksum passed. Source bytes and
dataset files remain immutable.

The source match list contains a complete 380-match regular season: 20 men's
teams, 38 appearances each, all ordered home/away pairs, and no missing local
date or kickoff. Both raw and normalized scans found 9,998 Shots, 121
penalties excluded, and 9,877 retained regulation non-penalty Shots. All
retained Shots have finite provider `shot.statsbomb_xg` in `[0, 1]` and a
mapped Shot type, MatchForge team, player, and valid source location. All 760
team-match non-penalty xG totals are positive; the minimum is `0.083188705`.

## Validation warnings

The governed dataset validator returned `warnings`: 632 `WARNING` findings,
zero `QUARANTINE` and zero `FATAL` findings. Its rule counts were:

| Rule | Count | Qualification effect |
| --- | ---: | --- |
| `SB_UNKNOWN_EVENT_TYPE` | 510 | Preserved with null canonical mapping; no retained Shot lacks its Shot mapping. |
| `SB_NONMONOTONIC_POSITION_STINT` | 118 | Lineup/stint warning; player stints are not an xG-for feature. |
| `SB_CONFLICTING_PLAYER_FACT` | 2 | Player country/name disagreement; no retained Shot lacks a MatchForge player or team mapping. |
| `SB_EVENT_LOCATION_OUT_OF_BOUNDS` | 1 | The affected event is a Pass, not a retained Shot. |
| `SB_IMPOSSIBLE_EVENT_TIMESTAMP` | 1 | The affected event is a Half End; event-index fallback is retained, and all lifecycle checks passed. |

These warnings are not silently cleared. A future feature using stints,
unmapped event types, the affected Pass location, or that Half End timestamp
needs its own review. They do not change the frozen team non-penalty xG-for
input or the exact target count here.

## Lifecycle, kickoff, and prior-only targets

The existing validated-dataset publishers created 380 completed lifecycle
claims, 380 `statsbomb-italy-local-kickoff-v1` claims, and 380 corner-label
claims required by the existing point-in-time reader. Repeat calls returned
`verified_existing` for all three. All 380 stored local date/time fields match
the pinned match list; each stored UTC instant matches `Europe/Rome` conversion
under pinned `tzdata 2026.3`. There are 227 distinct kickoff batches.

The research target plan used `retrospective-fixed-snapshot-v1`, a fixed
observed knowledge cutoff of `2026-09-22T07:52:00Z` (after the latest kickoff
claim at `07:50:52Z`), 10 prior team matches, and the existing two-hour
retrospective outcome-availability lag. It contains 280 scored, label-free
eligible targets in 171 kickoff batches; 100 matches are excluded as warm-up.
The minimum retained home and away histories are both 10. The largest
eligible batch has eight matches, with no team repeated within a batch.
Using the existing 100-match competition-history check or only the frozen
10-team-match rule produced the identical target set.

```text
Target-set SHA-256: 3ad13fea1f52bb31c671f8b5ed4ecd56af0ef233f01798e99e72795ffcc1a733
Plan SHA-256:       da416965bc7d5c9a6cd382466768e61bd60f74ab0fbb30d8a82ab8dde262ed6c
```

The plan is stored under the isolated root's `reports/qualification/target-plans`
directory and a repeat build returned `verified_existing`. An earlier
non-authoritative research plan used a next-day knowledge cutoff. It was
superseded before qualification or any evaluation; its plan hash
`9791079a3a0fbfb4fcbf36265a1850faeb2f2ebac73d927f7e3169bd93873eee`
must not be used. The corrected plan's cutoff is observed, not future.

## Protected and development firewall

The [identity-only comparison](../../scripts/verify_phase3a_serie_a_firewall.py)
mapped the isolated 280 target MatchForge IDs to StatsBomb provider match IDs,
then compared them with all 380 protected EPL `2/27` and all 380 development
La Liga `11/27` provider match IDs in the normal database. Both all-match and
target intersections were exactly zero. No protected admission or frozen
280-target population, scores, outcomes, forecasts, or evaluation reports were
read. Using the entire comparison seasons is stronger than comparing only
their protected target subsets.

## Decision boundary

This is one qualified group in one competition and one season, yielding 280
of Decision 2's required 500 eligible targets. Decision 2 still needs at
least two additional independent men's groups, at least one other competition,
and at least one other season. No authoritative corpus ID or membership is
frozen. Phase 3A xG-for implementation and Evaluation V2 remain blocked;
Sprint 2 remains `FAIL`. No model was fit, forecast published, Evaluation V2
outcome revealed, or Rust simulation changed.
