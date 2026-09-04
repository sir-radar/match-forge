# Football-Data.co.uk Phase 1B P1 acceptance corpus

Status: frozen acceptance input evidence

This record identifies the exact bounded corpus for the Football-Data.co.uk
second-provider Phase 1B proof. It is not a Phase 1B/2B gate result, a Sprint 2
result, a model-promotion decision, or Phase 3 authorization.

## Immutable manifest

- Contract: `FootballDataUkAcceptanceCorpusManifestV1`
- Corpus ID: `football-data-uk-phase1b-p1-20260904`
- Manifest SHA-256:
  `175beb4f90a897444f8396b21fbf4f3d6ac8a52c30ec0c25b5b941b40d1efcae`
- Local immutable artifact:
  `manifests/provider=football_data_uk/corpus_sha256=175beb4f90a897444f8396b21fbf4f3d6ac8a52c30ec0c25b5b941b40d1efcae/acceptance-corpus-manifest-v1.json`
- Manifest creation time: `2026-09-04T17:00:00+00:00`

The local artifact is content-addressed. Publishing the identical manifest a
second time returned `verified_existing`.

## Frozen sources

| Role | Resource identity | Rows | Header SHA-256 |
| --- | --- | ---: | --- |
| Schema and attribution | `football_data_uk/notes.txt/sha256/6ecd41a98ad2751372817e7e6f1709bfeb433c53dd9aeda330fd926a5471452d` | — | — |
| Completed-season coverage | `football_data_uk/mmz4281/2526/E0.csv/sha256/3e3a8352f9ada6789c508d6ca184424421fed56a30400904a4a327c583407e62` | 380 | `8274a4f2a2dab29d3028b37dde161535722f60010d5247398600dd26d910f3c5` |
| StatsBomb overlap | `football_data_uk/mmz4281/1516/E0.csv/sha256/bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085` | 380 | `031626f50503f9f68b84ee0f9c230eb8c4f235562e700448a22bef4bb0c06809` |

The receipt bundle remains
`manifests/provider=football_data_uk/acquisition_sha256=507d51f57ebcda6565d5877823cd57f12720fe7f26c02a2e279f26691843f955/acquisition-evidence-v1.json`.
Coverage reports remain content-addressed separately under
`reports/provider=football_data_uk/`.

## P1 selection

- Selection contract: `FootballDataUkOverlapPrefixSelectionV1`
- Selected source record indexes: `1` through `10`
- Trusted selected record index: `1`
- Provider team-label universe: 20 labels
- Required corners fields: `HC` and `AC`, present for the selected proof rows

The trusted index is based on the approved context-only resolution route. Match
identity uses the reviewed canonical competition, season, ordered team IDs, and
provider date; it does not use scores, results, or aggregate statistics. The
reviewed team crosswalk is recorded in
[`football-data-uk-team-crosswalk-2026-09-04.md`](football-data-uk-team-crosswalk-2026-09-04.md).

Football-Data.co.uk remains a Tier B aggregate match/statistical source. This
corpus supplies no events, lineups, 360 data, invented timezone, or strict
historical provider knowledge timestamp.

## Governance boundary

Sprint 2 remains `FAIL`; `RETAIN_FAIL_AND_STOP` remains authoritative. This
corpus neither changes `Sprint2BaselineGatePolicyV1` nor authorizes challenger
work, model promotion, a Sprint 2 rerun, or Phase 3. The next proof work must
persist source lineage, resolution decisions, reconciliation/quarantine, and
trusted `CanonicalChangeSetV1` publication before the unchanged Phase 1B/2B
acceptance gate can be rerun.
