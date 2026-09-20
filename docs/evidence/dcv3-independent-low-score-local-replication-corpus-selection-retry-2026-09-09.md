# Local Pinned Replication Corpus Selection Retry

Status: `LOCAL_PINNED_REPLICATION_CORPUS_SELECTION_COMPLETE`

This append-only record completes the authorized outcome-blind local selection. It used only the verified match-list cache at the pinned revision; no network, event resource, score, result, model, forecast, or diagnostic access occurred.

## Source and boundary checks

- Pinned revision: `4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`
- Catalog SHA-256: `e6cd42f5d8956d6aa30fb917ce8d4c3b3df1879a93f02f8feba820930a6971fa` (`PASS`)
- Match-list cache: `COMPLETE` (37 / 37 required candidate resources; source-byte and JSON checks passed)
- Outcome fields used for selection: `NO`
- Usable-PIT minimum semantics: `TOTAL_CORPUS`
- Candidates screened: `37`
- Candidates with at least 120 matches: `8`
- Structurally PIT-feasible candidates: `8`
- Complete eligible candidates: `4`

## Ranking resolution

The authorization lists La Liga first but explicitly says COMPLETE coverage outranks a merely expected league label. I therefore rank coverage class first, then apply the remaining frozen order. Every available La Liga scope is below the 120-match hard floor, so none is eligible; this explicit guard remains part of the deterministic method.

Coverage is structural only: COMPLETE means the cached team schedule contains the inferred double round-robin total with one match for every directed home-away pairing. NEAR_COMPLETE is at least 90% of that inferred total without repeated directed pairings; otherwise it is PARTIAL. It does not claim nominal provider or league coverage.

## Shortlist

| Rank | Competition | Season | Provider IDs | Country | Matches | Structural targets | Coverage | Kickoff policy | Pipeline |
| ---: | ----------- | ------ | ------------ | ------- | ------: | -----------------: | -------- | -------------- | -------- |
| 1 | Liga F | 2023/2024 | 182 / 281 | Spain | 240 | 140 | COMPLETE | EXISTING_APPROVED | REVIEW |
| 2 | FA Women's Super League | 2023/2024 | 37 / 281 | England | 132 | 32 | COMPLETE | EXISTING_APPROVED | REVIEW |
| 3 | Serie A | 2015/2016 | 12 / 27 | Italy | 380 | 280 | COMPLETE | NEW_KICKOFF_POLICY_RESEARCH_REQUIRED | REVIEW |
| 4 | Frauen Bundesliga | 2023/2024 | 135 / 281 | Germany | 132 | 32 | COMPLETE | NEW_KICKOFF_POLICY_RESEARCH_REQUIRED | REVIEW |
| 5 | FA Women's Super League | 2020/2021 | 37 / 90 | England | 131 | 31 | NEAR_COMPLETE | EXISTING_APPROVED | REVIEW |

- Rank 1 match-list SHA-256: `ea93b27a4d1101ba62792c88b5770bdacd904cefdf38671382698f5c2298628a`
- Rank 2 match-list SHA-256: `f0f3a5509f0ca9a1b5315b3a78d86d1c4c6909be5d16f2999c2d2295d6f3a22e`
- Rank 3 match-list SHA-256: `613cd3cc70699ba613cb1b3c27b4c8a01b0b5fa28415e09c928d020208905c7a`
- Rank 4 match-list SHA-256: `78d01ecb20035bb8bbd94001065ec0f92ea747cb053b4aafca8b1051be12a7d3`
- Rank 5 match-list SHA-256: `a9ea5e5e3c6f7b2e070ab9c3f3c23d6757545d7a6aa81fa4fbb9c443218597c2`

All shortlist entries are `REVIEW` for pipeline compatibility: generic StatsBomb resources and canonical ingestion are present, but the current versioned provider capability declaration does not yet list these exact scopes. No implementation was made here.

## Selected corpus

`REPLICATION_CORPUS_SELECTED`

- Provider: StatsBomb Open Data
- Competition: Liga F
- Season: 2023/2024
- Provider competition / season: `182 / 281`
- Country: Spain
- Source revision: `4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`
- Match-list path: `data/matches/182/281.json`
- Match-list SHA-256: `ea93b27a4d1101ba62792c88b5770bdacd904cefdf38671382698f5c2298628a`
- Actual / unique provider matches: `240 / 240`
- Structurally eligible post-warm-up targets: `140`
- Coverage: `COMPLETE`
- Kickoff policy: `EXISTING_APPROVED` (statsbomb-spain-local-kickoff-v1, Europe/Madrid)
- Pipeline compatibility: `REVIEW`
- Protected overlap: `0`
- Selection metadata SHA-256: `3288fc23a26362177160a3c86b619935176f8006b9568005f01d4afd7f855133`
- Selection frozen: `YES`

## Stop boundary

No selected-corpus qualification, event acquisition, source/event dataset publication, canonicalization, lifecycle or kickoff claim publication, target-forecast creation, score access, DCv3 fitting, or low-score diagnostic was performed. Owner review is required before the next authorized route.

Recommended next action: `AUTHORIZE_SELECTED_REPLICATION_CORPUS_QUALIFICATION`

## Full structural screen

The machine-readable companion contains every candidate's path, cache SHA-256, counts, chronology span, teams, target count, coverage evidence, kickoff policy, pipeline assessment, protected-overlap result, and eligibility decision. No score-derived fields are present.
