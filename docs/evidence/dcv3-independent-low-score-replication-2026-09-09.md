# DCv3 independent low-score replication — 2026-09-09

## Ticket 02 terminal qualification result

```text
REPLICATION_DATASET_QUALIFICATION_FAILED

Selected corpus: StatsBomb La Liga 2016/2017
Provider competition / season: 11 / 2
Canonical competition: 01a051db-552e-782d-b2ac-b3f0ec58441b
Canonical season: 01a051db-5538-7604-a075-c0bff7c234f1
Canonical matches: 34
Required usable PIT matches: at least 120
Expected matches at selection: 380
```

The selection was frozen before the match list was acquired in
[dcv3-independent-low-score-replication-corpus-2026-09-09.md](dcv3-independent-low-score-replication-corpus-2026-09-09.md).
Only that selected season proceeded. No alternate season was selected after
the count became known.

The immutable match-list receipt was acquired and parsed successfully:

```text
Source revision: 4b73468fc5b0f1950f9f66fada70ad3a4f9327cb
Source snapshot: 01a087a2-7693-73db-b34b-1722bc7a73ce
Resource: data/matches/11/2.json
Resource SHA-256: f34be8ff144e889af756082410c9357dcadd380aa13f8ec85a1b344411f8722c
Bytes: 61,437
Parse status: parsed
Validation status: valid
```

The selected StatsBomb resource contains only 34 canonical matches. This is
below the map's hard minimum and cannot provide the 100-match warm-up, any
eligible replication targets, or a valid moving-block low-score diagnostic.

## Qualification gates

| Gate | Result |
| --- | --- |
| Publication integrity | PASS for acquired match-list receipt only |
| Season completeness | FAIL — 34 canonical matches, expected 380 |
| Canonical identity | PASS — one canonical competition and season resolved |
| Lifecycle | NOT RUN — no eligible dataset publication |
| Kickoff | NOT RUN — no eligible lifecycle claims |
| Point-in-time suitability | FAIL — zero usable PIT matches; minimum 120 |
| Protected EPL overlap | 0 |
| La Liga 2015/16 diagnostic overlap | 0 — distinct canonical season |

No normalized event dataset was published, no dataset version exists for this
scope, and no lifecycle claims were created. The raw source receipt remains
immutable; the temporary provider-capability addition was removed because this
unqualified scope is not an approved forecasting corpus.

## Stopped tickets

```text
Ticket 03 — replication forecast protocol: NOT RUN
Ticket 04 — frozen DCv3 forecasts: NOT RUN
Ticket 05 — frozen low-score replication protocol: NOT RUN
Ticket 06 — replication classification from forecasts: NOT RUN
Ticket 07 — owner handoff: REQUIRED
```

```text
Conclusion:
D. REPLICATION_INCONCLUSIVE

Reason:
Insufficient qualified replication population before forecast freeze.

Recommended next action:
AUTHORIZE_ONE_NEW_METADATA_ONLY_CORPUS_SELECTION
```

The next selection must be a new explicit owner authorization. It must start
with metadata-only corpus resolution and cannot reuse or retune this 34-match
scope.

```text
Frozen DCv3: UNCHANGED
La Liga diagnostic: NOT RETUNED
Replication diagnostic: NOT USED FOR TUNING
Candidate models: NOT FIT
Static heterogeneity challenger: NOT JUSTIFIED
Frozen EPL 280 outcomes: NOT ACCESSED
Protected EPL 100-match admission: NOT REUSED
Shared-pace admission: NOT RERUN
Authoritative evaluation: NOT RUN / NOT AUTHORIZED
Sprint 2: FAIL
Model promoted: false
Phase 3: BLOCKED / UNAUTHORIZED
Production model changes: NONE
```

Machine-readable result:
[dcv3-independent-low-score-replication-2026-09-09.json](dcv3-independent-low-score-replication-2026-09-09.json).
