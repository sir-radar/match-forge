# DCv3 local pinned replication-corpus selection — 2026-09-09

## Result

```text
LOCAL_PINNED_METADATA_COPY_INCOMPLETE
```

The local StatsBomb cache is verified against the required pinned revision,
but it does not contain any match-list resource for a remaining candidate. The
only local match lists are the already-excluded La Liga 2015/16 and failed La
Liga 2016/17 scopes. Selection is therefore not frozen.

```text
LOCAL_SOURCE_TYPE: cache
LOCAL_SOURCE_PATH: .local/football-data/raw/provider=statsbomb_open_data/
snapshot=4b73468fc5b0f1950f9f66fada70ad3a4f9327cb
PINNED_SOURCE_REVISION: 4b73468fc5b0f1950f9f66fada70ad3a4f9327cb
SOURCE_REVISION_VERIFIED: YES

CATALOG_SHA256: e6cd42f5d8956d6aa30fb917ce8d4c3b3df1879a93f02f8feba820930a6971fa
CATALOG_IDENTITY: PASS

OUTCOME_FIELDS_USED_FOR_SELECTION: NO
USABLE_PIT_MINIMUM_SEMANTICS: TOTAL_CORPUS
```

The catalog has 40 named senior domestic top-flight competition-seasons. Three
are excluded before scanning: protected Premier League 2015/16, consumed La
Liga 2015/16, and failed La Liga 2016/17. The remaining 37 expected match-list
paths are unavailable locally, so no candidate count, structural PIT estimate,
coverage classification, kickoff-policy result, pipeline result, shortlist, or
ranking can be truthfully produced.

The exact missing paths and the full terminal record are in
[dcv3-independent-low-score-local-replication-corpus-selection-2026-09-09.json](dcv3-independent-low-score-local-replication-corpus-selection-2026-09-09.json).

No event resource was read. No score, outcome, forecast, fit, evaluation, or
diagnostic value was accessed. Frozen DCv3 and all protected Sprint 2 scopes
remain unchanged.
