# Phase 3A Serie A 2015/16 source qualification — 2026-09-22

Status: `RAW_SOURCE_COVERAGE_PASS`; Evaluation V2 corpus eligibility:
`NOT_DETERMINED`.

The repository owner authorized only research qualification and acquisition
of StatsBomb Serie A 2015/16 (`12/27`) pinned events and lineups. The
[decision record](owner-decision-authorize-phase3a-serie-a-source-qualification-2026-09-22.md)
does not admit this group to Evaluation V2.

## Verified acquisition

```text
Provider:              statsbomb_open_data
Competition / season:  12 / 27 (men's Serie A 2015/16)
Source Git SHA:        4b73468fc5b0f1950f9f66fada70ad3a4f9327cb
Match-list SHA-256:    613cd3cc70699ba613cb1b3c27b4c8a01b0b5fa28415e09c928d020208905c7a
Source manifest SHA:   2d0bb941dbec283118185b3bf5261184a6d16a118381348539703b089efd3944
Source resources:      761 = 1 match list + 380 events + 380 lineups
Data root:             .local/football-data
```

The immutable source manifest is at
`.local/football-data/manifests/provider=statsbomb_open_data/snapshot=4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/scope=952a7528d436c9c5c1032875fdbc7b24b06f32da2a41b2c93edabe6c3c1debff/source-manifest-v1.json`.
Acquisition used `scripts/acquire_phase3a_serie_a_2015_16.py` against that
data root. The script checks the frozen match-list hash and exact `12/27`
capability, fetches only that list's event/lineup resources from the pinned
commit, preserves bytes through `ImmutableRawStore`, and publishes a
`SourceManifestV1`. No other provider scope was acquired by this command.

`scripts/screen_phase3a_serie_a_2015_16_raw.py` re-read every manifest
resource and checked its path, size, and SHA-256 before counting. The match
list contains 380 unique matches, 20 teams appearing 38 times each, all
380 ordered home/away pairs, only regular-season stage, men's teams, and no
missing local date or kickoff field. Each match has an event file and a
two-team lineup file. Across 1,353,739 event rows, 9,998 are Shots; 121
penalty Shots are excluded and 9,877 regulation non-penalty Shots remain.
All 9,877 have finite `shot.statsbomb_xg` in `[0, 1]`. No outside-period
Shots were found. This is raw source coverage, not a normalized-dataset or
point-in-time qualification result. The machine-readable summary is
[here](phase3a-serie-a-2015-16-source-qualification-2026-09-22.json).

As a read-only policy candidate check, the existing local-kickoff resolver
converted all 380 match dates and local times unambiguously with
`Europe/Rome` and pinned `tzdata 2026.3`, yielding 227 distinct kickoff
batches. This does **not** approve an Italy policy or publish a kickoff claim.

## Open qualification gates

- No canonical Serie A event dataset version, dataset-manifest hash, or
  registered source-snapshot ID has been produced. Raw source identity does
  not stand in for those identities.
- The current approved domestic kickoff policies cover England and Spain,
  not Italy. `Europe/Rome` remains a candidate only. No Italian
  timezone/kickoff claim was approved or published.
  Lifecycle claims, canonical identity checks, and point-in-time target
  reconstruction were not run.
- Exact prior-10 eligible team-history counts, target count, same-kickoff
  isolation, target-outcome sealing, and protected/development target-manifest
  intersection are `NOT_RUN`. Provider IDs alone do not prove the exact
  firewall intersection.
- Even a later fully qualified Serie A group supplies only one independent
  men's competition-season group in one season. Decision 2 still requires at
  least three groups, two competitions, two seasons, and 500 eligible scored
  targets. The reviewed pinned catalog contains no other structurally complete
  eligible men's group after protected EPL and development La Liga exclusions.

No protected EPL source, target, or outcome, development La Liga source or
target, Evaluation V2 outcome, or model forecast was accessed for this
acquisition or screen. No xG-for model, Evaluation V2 run, production forecast
change, baseline change, or Rust simulation change was made.
