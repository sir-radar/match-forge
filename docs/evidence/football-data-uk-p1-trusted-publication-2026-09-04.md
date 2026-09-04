# Football-Data.co.uk Phase 1B P1 trusted publication

Status: local acceptance-database evidence

The ten frozen P1 rows each had one reviewed `AUTO_ACCEPTED` match decision and
the same date and full-time score as the current StatsBomb observation. They
were published as separate Football-Data score observations; the existing
StatsBomb observations were not changed.

## Published change set

- PostgreSQL change-set row: `01a06e7d-d7cd-7c67-8fd0-ccf5314dd701`
- Change-set key:
  `6e97ee54da585d16978063166044220e78be8af659f903fde1de2c292f087d21`
- Change-set ID: `football-data-uk-p1-trusted-publication-20260904`
- Sync run: `01a06e71-a6b9-75dc-886c-9f722feaea6b`
- Source: `mmz4281/1516/E0.csv`, SHA-256
  `bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085`
- Resolution policy: `FootballDataUkPhase1BMatchResolutionV1`
- Quality-policy reference: `FootballDataUkHistoricalLeagueCsvV1`
- Knowledge time: `2026-09-04T16:20:55.150645+00:00`

The change set has ten added Football-Data match observations, one for each
frozen P1 row. It leaves football-time bounds null because the source gives a
date and local kickoff time but no timezone or kickoff instant.

An identical replay returned `verified_existing` with the same ten observation
IDs and the same change-set ID. It created no duplicate rows and no provider
cursor. The controlled synthetic score discrepancy remains one open
`CONFLICT_UNRESOLVED` quarantine record and created no trusted publication.

Sprint 2 remains `FAIL`; Phase 3 remains blocked.
