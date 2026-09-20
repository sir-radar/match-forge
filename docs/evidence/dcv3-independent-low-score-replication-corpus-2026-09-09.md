# DCv3 independent low-score replication corpus selection — 2026-09-09

## Ticket 01 — selected corpus

```text
REPLICATION_CORPUS_SELECTED

Provider: StatsBomb Open Data
Competition: La Liga
Season: 2016/2017
Provider competition / season: 11 / 2
Expected canonical matches: 380
Source revision: 4b73468fc5b0f1950f9f66fada70ad3a4f9327cb
Catalog path / SHA-256: data/competitions.json /
e6cd42f5d8956d6aa30fb917ce8d4c3b3df1879a93f02f8feba820930a6971fa
Match-list path: data/matches/11/2.json
Selection metadata SHA-256: 9737623813d72c3d009f12fa89017d4e43a1a54726f9db3e600b2859c73c9c80
```

No eligible additional competition-season is already published in the local
governed evidence: EPL 2015/16 is protected and La Liga 2015/16 is consumed
diagnostic evidence. The pinned StatsBomb catalog was then inspected without
fetching a candidate match list, event resource, score, forecast, or diagnostic
result.

La Liga 2016/17 is the first preferred distinct La Liga season after 2015/16,
ordered by season start. It keeps provider, domestic competition, league format,
and Spain kickoff-policy support constant while selecting a distinct season.
The expected 380 matches follow the ordinary 20-club double round-robin format;
Ticket 02 must verify the exact count from immutable source and canonical
publication before any forecast or outcome is accessed.

This selection is based only on provider catalog metadata and fixed selection
order. It is not based on goals, 0-0 rate, rho, CRPS, NLL, forecasts, or
diagnostic performance. Canonical dataset, source-snapshot, and match identities
do not exist until the selected season is acquired and published.

The machine-readable selection record is
[dcv3-independent-low-score-replication-corpus-2026-09-09.json](dcv3-independent-low-score-replication-corpus-2026-09-09.json).
