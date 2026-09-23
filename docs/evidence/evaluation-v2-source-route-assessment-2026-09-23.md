# Evaluation V2 source-route assessment — 2026-09-23

Status: `BLOCKED — OWNER SOURCE-ROUTE DECISION PREPARED`

This research compares two possible routes. It does not qualify a provider,
authorize contact or purchase, retain raw data, admit a corpus, amend a frozen
decision, implement a model, or authorize Evaluation V2.

## Decision matrix

| Requirement | Licensed StatsBomb arrangement | PitchAPI amendment |
| --- | --- | --- |
| Current route state | `CONDITIONALLY_FEASIBLE — AWAITING PROVIDER EVIDENCE` | `CONDITIONALLY_FEASIBLE — AWAITING PROVIDER EVIDENCE AND AMENDMENTS` |
| Data availability | Hudl advertises post-match event data, API delivery and JSON/XML/CSV across 200+ competitions. Exact complete men's seasons, match counts, events, lineups and shot-xG coverage are not public. | Audit proved 306 Bundesliga 2023/24 and 380 Ligue 1 2022/23 matches, 686/686 shot resources and 17,873 valid shots. A third evaluation group and a separate development group remain unproved. |
| xG consistency | Same provider name is not enough. Hudl's September 2025 release changed historical xG outputs, typically within 5%. Need one attested export/model series and proof it matches the frozen `shot.statsbomb_xg` contract. | Upstream supplier and model/version are unknown. Need one provider-attested series across one development group and at least three evaluation groups. Mixing PitchAPI and StatsBomb xG is forbidden. |
| Historical reproducibility | Live API data is mutable. A fixed export needs an export/revision ID, file manifest, checksums, correction/reissue policy and permission to keep earlier versions. | Current API has no immutable revision, prior-version access or correction ledger. A 2026 capture cannot prove older publication state. Need a provider-issued frozen export/snapshot cohort, revision history and a ruling on the frozen knowledge-mode requirement. |
| Licensing | Hudl's public MSA requires Content deletion after the subscription and, unless expressly permitted, restricts downloading and training models with Content. An Order Form/SOW must expressly grant immutable retention, backups, model fitting and reproducible private evaluation. | Public API access is free, but no reviewed public terms grant immutable retention, private model research, post-access use, correction snapshots or aggregate/hash publication. Need a provider-issued grant or governing terms. |
| Expected provider cost | `UNKNOWN — QUOTE REQUIRED`. Public pages publish no StatsBomb price; fees belong in the Order Form/SOW. | Published API price is $0, but any contractual grant or frozen export cost is unknown. Engineering and governance cost is materially higher. |
| Engineering effort | Lower if a fixed export matches existing Open Data JSON and xG semantics: reuse the StatsBomb adapter, raw store, normalization, qualification, target-plan and firewall code. Higher if delivery/schema/model differs. | High: new retained acquisition path and adapter, normalization, MatchForge ID mapping, correction/version handling, new feature ID, new development source, three evaluation groups, target plans, firewall and full pre-registration changes. |
| 500-target minimum | Feasible in principle, not proved. Existing qualified Serie A contributes 280. Complete Bundesliga 2023/24 and Ligue 1 2022/23 would add about 216 and 280 ideal targets after warm-up, for about 776 total before exclusions. | Audited groups provide at most about 496 ideal targets before exclusions, below 500 and only two groups. Route needs at least one more evaluation group; because StatsBomb groups cannot count, it also needs a separate PitchAPI development group. |
| Main blockers | Exact inventory; xG model/version and equivalence; fixed export identity; corrections and prior versions; retention/model-use rights; price; delivery terms; exact eligible targets/firewall. | Governing terms; retention/model-use rights; upstream xG supplier/model/version; one-series proof across four groups; immutable revisions; correction history; ID migration; historical availability/knowledge-mode ruling; extra group inventory; exact targets/firewall. |

## Public evidence

Hudl states that StatsBomb provides post-match event data, xG, API access and
JSON/XML/CSV delivery. Public pages do not confirm either candidate season or
an export version. The [September 2025 release notes](https://www.hudl.com/releases/statsbomb)
also state that API fixes changed historical xG outputs and made event IDs
deterministic. Therefore a live API entitlement alone is not a reproducible
source contract. See the [product FAQ](https://www.hudl.com/products/statsbomb/faq)
and [product page](https://www.hudl.com/products/statsbomb).

The current [Hudl Master Subscription Agreement](https://static.hudl.com/craft/legal/Hudl-Master-Subscription-Agreeement_2026-02-09.pdf)
limits Content to the subscription term, requires deletion when the term ends,
and restricts copying, downloading and model training except where expressly
permitted. These are planning findings, not legal advice. The negotiated Order
Form/SOW must resolve them before MatchForge can retain or fit on licensed data.

PitchAPI documents `shots[].expected_goals`, explicit period groups and
`situation=Penalty`, and advertises free access. It also says providers train
different xG models and its September 2026 changelog records rebuilt leagues
receiving new IDs while old IDs began returning `404`. See the
[PitchAPI documentation and changelog](https://pitchapi.dev/). Public
documentation still does not identify the supplier/model for the audited
seasons or grant immutable retention.

## Requirements that need provider evidence

Neither route can establish these internally:

1. Exact competition-season inventory, official match totals, complete event,
   lineup, period, penalty, kickoff, lifecycle and shot-xG coverage.
2. Exact xG owner, field, model/version, recalculation history and proof that
   one series covers every development and evaluation group.
3. Fixed export or snapshot identity, schema version, file manifest, checksums,
   correction/reissue history and access to retained prior versions.
4. Stable provider identifiers or a complete migration map.
5. Written rights for acquisition, immutable raw retention, backups, model
   fitting, reproducible private evaluation, post-term/post-access use,
   attribution and permitted aggregate/hash evidence.
6. Exact price, taxes, term, support/export fees, delivery method and delivery
   schedule where applicable.

Provider evidence does not replace MatchForge qualification. After authorized
delivery, each route still needs exact completeness, MatchForge ID mapping,
finite retained-shot xG, eligible-target counts, same-kickoff isolation and
zero protected/development intersection.

## Work independent of route selection

Current provider-neutral snapshot, hash, dataset-build, correction, identity,
cutoff and firewall machinery already exists and has synthetic coverage. No new
production abstraction is justified now.

The following may proceed only under their existing or a separate narrow
authorization:

- record this decision and keep the source-route ticket current;
- rotate the exposed football-data.org credential as an owner action;
- maintain or extend synthetic-only source-manifest, correction, identity,
  same-kickoff and firewall tests when a concrete gap is identified;
- finish source-neutral pre-registration text that does not choose provider,
  corpus membership or unset evidence.

These cannot proceed independently: provider adapter/acquisition work, raw
retention, real-data qualification, exact target counts, corpus hashes,
feature fitting, Evaluation V2 or source-specific baseline reproduction. Rust
simulation remains under its separate authorization and acceptance boundary.

## Proposed licensed StatsBomb plan

1. Owner separately authorizes one bounded StatsBomb follow-up or request for
   proposal. The existing inquiry remains passive until then.
2. Obtain a written inventory and proposal covering at least two additional
   complete men's domestic seasons, one attested xG series, a fixed export,
   corrections/prior versions, permitted retention/model use and a quote.
3. Owner approves exact seasons, maximum total cost, negotiated Order Form/SOW,
   delivery format and isolated acquisition scope. Purchase and delivery remain
   separate actions.
4. If xG is not proved compatible with frozen `shot.statsbomb_xg`, stop or
   separately approve Decision 1 and Decision 2 amendments before acquisition.
5. Owner authorizes isolated acquisition and retention, then qualification.
6. After qualification passes, owner separately freezes exact corpus IDs,
   manifests, target hashes and firewall evidence.
7. Owner separately freezes the completed pre-registration, releases model
   implementation, and later authorizes the one authoritative Evaluation V2
   run. Mandatory Rust requirements remain unchanged.

## Proposed PitchAPI amendment plan

1. Owner separately authorizes a bounded provider/legal evidence request. More
   API calls are not useful and the ten remaining attempts stay unused.
2. Obtain governing terms or a grant, upstream xG supplier/model/version,
   one-series proof across four groups, immutable export/revision history,
   correction and ID-migration rules, exact extra-season inventory and cost.
3. Owner approves a new provider-specific feature ID and Decision 1 amendment,
   keeping all existing mathematics and fail-closed rules unchanged.
4. Owner approves a Decision 2 amendment: one new PitchAPI development group,
   at least three new PitchAPI evaluation groups, at least two competitions and
   seasons, and at least 500 eligible targets, all on one frozen xG series.
   Existing StatsBomb evidence remains preserved but does not count.
5. Owner authorizes exact acquisition, raw retention, request budget,
   credentials, adapter/ingestion work and isolated qualification.
6. After all four groups qualify, owner separately freezes the development and
   evaluation manifests, target hashes, exclusions and firewall.
7. Owner separately reapproves the full pre-registration, releases model
   implementation, and later authorizes Evaluation V2. Mandatory Rust
   requirements remain unchanged.

## Recommendation

Prefer the licensed StatsBomb route because it is the shortest route that may
preserve the frozen feature and reuse the qualified Serie A group. Keep its
status `AWAITING_PROVIDER_EVIDENCE`; do not authorize purchase or acquisition.

Keep PitchAPI as a contingency amendment route. It has strong technical
coverage but needs a full same-series replacement experiment and more provider
evidence. Do not weaken target, group, competition, season, separation,
reproducibility or retention requirements for either route.
