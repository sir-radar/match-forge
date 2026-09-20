# StatsBomb pinned match-list cache completion — 2026-09-09

## Result

```text
PINNED_STATSBOMB_MATCH_LIST_CACHE_COMPLETE
```

```text
Pinned revision: 4b73468fc5b0f1950f9f66fada70ad3a4f9327cb
Catalog identity: PASS
Candidate match-list resources required: 37
Materialized: 37
Reused: 0
Unavailable: 0
All JSON resources parse: PASS
All SHA-256 receipts recorded: PASS
Revision mixing detected: NO
Outcome fields used: NO
PINNED_METADATA_CACHE_COMPLETE: YES
```

The cache was materialized from a sparse checkout of the exact pinned commit.
Each local match-list byte sequence was compared with its matching Git blob at
that commit, without projecting or using any outcome field. The catalog remains
bound to the retained SHA-256:

```text
e6cd42f5d8956d6aa30fb917ce8d4c3b3df1879a93f02f8feba820930a6971fa
```

The machine-readable receipt includes all 37 source-relative paths, provider
competition and season IDs, byte counts, Git blob IDs, and SHA-256 values:
[statsbomb-pinned-match-list-cache-completion-2026-09-09.json](statsbomb-pinned-match-list-cache-completion-2026-09-09.json).

No event resource was acquired or read. No match-list structural ranking,
selection, forecast, fit, diagnostic, or evaluation was run. Frozen DCv3 and
all protected Sprint 2 populations remain unchanged.

## Next

```text
RETRY_LOCAL_PINNED_REPLICATION_CORPUS_SELECTION
```
