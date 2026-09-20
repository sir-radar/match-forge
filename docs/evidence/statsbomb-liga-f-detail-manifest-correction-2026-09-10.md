# StatsBomb Liga F detail-manifest correction — 2026-09-10

Status: `BLOCKED`

The authorized event-identity correction succeeded for the frozen Liga F 2023/24
resource population: 240 selected matches map one-to-one to 240 exact event
paths and 240 exact lineup paths at pinned StatsBomb revision
`4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`. Every checked-out object passed
Git blob, SHA-256, JSON, and existing StatsBomb parser validation. Event
identity is bound by the selected match ID and exact `data/events/<id>.json`
path; the source payload has no top-level `match_id` field. Lineups use the
same existing path-bound source contract.

The governed materialization stopped before a new manifest could be published.
The normal data root already contains an immutable 480-resource manifest for
this exact scope. Its record for `data/events/3911496.json` is 1,901,120 bytes
with SHA-256 `d54bc4fd931f278801dc20e6bca6be6660ea689ecd5ee7eae5d7a542340f17c2`.
The pinned Git blob is 3,025,525 bytes with SHA-256
`ee9742816f7cb842bf3875f3a609a68a319f82139589c50d054bd12ce1ceb7a1`.
The mismatched existing bytes were moved without alteration to the local
quarantine path recorded in the companion JSON evidence. The immutable
manifest was not overwritten.

`SourceAcquirer` rejected recovery because the exact Git bytes do not match
that pre-existing manifest entry. No new detail manifest, source snapshot, or
canonical dataset was published. The complete machine-readable record is in
`statsbomb-liga-f-detail-manifest-correction-2026-09-10.json`.
