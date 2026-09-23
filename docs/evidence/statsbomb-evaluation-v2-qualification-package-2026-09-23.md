# StatsBomb Evaluation V2 qualification package — 2026-09-23

Status: `REQUEST SENT — WRITTEN PROVIDER AND CONTRACT EVIDENCE REQUIRED`

This package implements owner decision
`SELECT_STATSBOMB_PRIMARY_EVALUATION_V2_SOURCE_ROUTE_V1`. It does not accept an
agreement, spend money, request or retain data, admit a corpus, change a frozen
decision, implement the challenger, or execute Evaluation V2.

The approved non-binding request was sent to `sales@statsbomb.com` at
`2026-09-23T23:13:06Z`. Gmail displayed `Message sent`. No agreement, trial,
purchase, payment or data delivery was accepted or activated. See the
[send record](statsbomb-qualification-request-send-record-2026-09-24.md).

## Owner decision matrix

| Item | Finding | Qualification effect |
| --- | --- | --- |
| Exact candidate scope | Keep frozen StatsBomb Open Data La Liga 2015/16 as development-only. Use qualified Serie A 2015/16 as evaluation group 1. Request complete licensed Bundesliga 2023/24 and Ligue 1 2022/23 as evaluation groups 2 and 3. | Exact commercial availability and delivered match lists are provider-only evidence. No group is admitted here. |
| Nominal evaluation matches | Serie A 380 + Bundesliga 306 + Ligue 1 380 = **1,066**. | Serie A is exact repository evidence. The other counts are competition schedule totals and audited PitchAPI counts, not proof of StatsBomb delivery. |
| Projected eligible targets | Serie A **280 exact** + Bundesliga **about 216** + Ligue 1 **about 280** = **about 776** before provider-specific exclusions. | Clears 500 provisionally by about 276. Exact target plans require licensed bytes, qualification and the frozen prior-only rules. |
| Independent groups | Three men's competition-season groups, three competitions and two seasons. | Satisfies the structural minimum if all three qualify on one xG series and pass the firewall. |
| xG compatibility | Public pages expose StatsBomb xG, but not a fixed model/build shared by the four development/evaluation groups. September 2025 release notes say historical xG outputs changed, typically within 5%. | Provider must identify one fixed series and prove compatibility with pinned `shot.statsbomb_xg`. Same provider and field name are insufficient. |
| Reproducibility | JSON/XML/CSV/API delivery is advertised. Public terms do not promise an immutable snapshot, checksums, correction history or access to superseded versions. | Require a fixed export ID, schema, delivery timestamp, complete manifest, SHA-256 hashes, correction ledger and right to retain prior versions. |
| Stable identity | Public data uses competition, season, match, team and event IDs. Event IDs became deterministic only after the September 2025 API change. | Require written permanence/alias rules for competition, season, match, team, player, event and shot IDs, plus migration maps after corrections. |
| Point-in-time/provenance | Public indexes expose availability/update timestamps, but not immutable per-field history or the exact historical knowledge state. | Require the meaning and history of availability/update fields, source/export timestamps and correction timestamps. MatchForge still applies its own cutoff and same-kickoff rules. |
| Licensing | Current default Hudl terms conflict with permanent retention, model work and reproducibility archives. | Default terms are `UNQUALIFIED`. Rights must be in the signed Order or an expressly incorporated signed amendment. A sales email is not enough. |
| Pricing | No public StatsBomb licence price was found. Fees are set in the Order. No provider response or quote is available in retained evidence. | `UNKNOWN — QUOTE REQUIRED`. Current spend authority remains `$0`. Contract pricing may also be confidential. |
| Engineering effort | Lower than PitchAPI if the export matches existing StatsBomb JSON and xG semantics; otherwise material adapter and requalification work remains. | No source-specific engineering or acquisition is authorized before licensing and exact delivery approval. |
| PitchAPI contingency | Two audited groups remain `TECHNICALLY_COMPLETE_RESEARCH_ONLY`; 686 matches and about 496 ideal targets do not form a complete same-series replacement experiment. | Keep evidence and ten unused attempts unchanged. Mixing PitchAPI and StatsBomb xG remains forbidden. |

## Exact proposed StatsBomb scope

Development remains the pinned StatsBomb Open Data La Liga 2015/16 (`11/27`)
source. It cannot become an Evaluation V2 group.

The proposed evaluation corpus is:

| Role | Group | Nominal matches | Eligible-target basis | Current state |
| --- | --- | ---: | ---: | --- |
| Development only | La Liga 2015/16 (`11/27`) | 380 | not counted | Frozen development source; protected from evaluation use. |
| Evaluation 1 | Serie A 2015/16 (`12/27`) | 380 | 280 exact | `PASS_WITH_WARNINGS`; not admitted. Target-plan SHA-256 `da416965bc7d5c9a6cd382466768e61bd60f74ab0fbb30d8a82ab8dde262ed6c`. |
| Evaluation 2 | Bundesliga 2023/24 (public catalog `9/281`) | 306 | about 216 | Full licensed StatsBomb scope unproved. Public Open Data contains only Bayer Leverkusen's 34 league matches. |
| Evaluation 3 | Ligue 1 2022/23 (public catalog `7/235`) | 380 | about 280 | Full licensed StatsBomb scope unproved. Public Open Data contains only 32 matches. |

The projected total is 1,066 nominal evaluation matches and about 776 eligible
targets. The Bundesliga and Ligue 1 projections assume a complete regular
season and exclude the first ten team appearances under the frozen warm-up.
Postponements, missing resources, lifecycle failures, ID mapping, same-kickoff
rules and the protected/development firewall can reduce the exact count.

Serie A may be combined with the licensed groups only if StatsBomb provides a
technical attestation and MatchForge confirms that the licensed pre-shot xG is
the same fixed series as the pinned La Liga and Serie A `shot.statsbomb_xg`
values. The partial public Bundesliga and Ligue 1 overlaps provide a future
value-comparison check. If that proof fails, the unchanged route stops. A new
four-group export or a different xG build would require separate Decision 1
and Decision 2 amendments and is not authorized by this decision.

No protected EPL source, protected target population, outcome or forecast may
be accessed. The qualified Serie A firewall remains evidence only; the two new
groups need their own exact MatchForge-ID firewall checks before admission.

## Public evidence and remaining provider proof

Hudl's [StatsBomb FAQ](https://www.hudl.com/products/statsbomb/faq) states that
post-match event data and xG are available through an API and JSON, XML and CSV
formats, and advertises integration with R and Python for bespoke modelling.
It says the product covers more than 200 competitions. Those statements do not
identify the requested full seasons, match totals, export version or licence.

The Hudl-owned [Open Data repository](https://github.com/hudl/open-data) shows
the StatsBomb JSON layout and provider IDs. Hudl's
[free-data page](https://statsbomb.com/what-we-do/hub/free-data/) says the
Bundesliga 2023/24 release covers Bayer Leverkusen's 34 league matches, not the
full league. The retained pinned catalog likewise contains only 32 Ligue 1
2022/23 matches. Public catalog presence is not commercial inventory proof.

The [StatsBomb release notes](https://www.hudl.com/releases/statsbomb) state
that the 22 September 2025 API migration made event IDs deterministic,
increased xG precision and changed historical xG outputs, typically within 5%,
after fixes. Later releases changed event schema versions and backfilled some
metrics. A live API entitlement is therefore not a fixed historical export.

Only StatsBomb can supply the following evidence:

1. Exact commercial inventory and delivered match IDs/counts for the two
   requested full seasons, including postponed, abandoned and missing matches.
2. Complete match metadata, lineups, events, periods, penalty classification,
   kickoffs, lifecycle state and finite pre-shot xG for every retained shot.
3. xG model owner, exact model/build/export version, historical recalculation
   dates and proof of one series across pinned La Liga, Serie A, Bundesliga and
   Ligue 1.
4. Fixed export/snapshot ID, schema versions, delivery and effective timestamps,
   file manifest, provider checksums and permission for MatchForge SHA-256s.
5. Correction and revision policy, notice timing, change logs, versioned
   replacement exports, prior-version availability and no silent overwrite.
6. Stable competition, season, match, team, player, event and shot identifiers,
   including alias/migration rules after corrections or re-imports.
7. Meaning and history of match availability/update timestamps and any more
   detailed point-in-time/source metadata.
8. Exact price, currency, taxes, term, support/export fees, delivery schedule,
   quote validity and licence structure.

Provider evidence does not replace MatchForge qualification or owner approval.

## Required contract rights and amendments

The current [Hudl MSA](https://www.hudl.com/legal/msa), updated 14 September
2026, is unqualified for this work. Its default provisions require Content
deletion/destruction and cessation at subscription end (§1.6), restrict copying,
derivative works, benchmarking and ML/AI model development unless expressly
permitted (§2.6), and require immediate cessation of Content use after
termination (§9.4). The [AUP](https://www.hudl.com/acceptable-use-policy)
separately restricts downloading unless a written agreement permits it.
Marketing or sales statements do not create contractual rights.

The signed Order, or a signed amendment expressly incorporated into it, must:

1. grant perpetual internal retention and use after expiry/termination for the
   exact raw export, manifests, hashes, source details, backups, corrections
   and superseded versions needed to reproduce and audit Evaluation V2;
2. expressly permit export, download, copying, local storage, normalization,
   hashing, private statistical and ML modelling, derived features, forecasts,
   calibration, evaluation and mandatory Rust simulation;
3. grant perpetual internal retention/use of derived datasets, fitted
   artifacts, forecasts, calibration and simulation outputs, and evaluation
   evidence, with no post-term deletion duty for those items;
4. make the exact scope, match list, fields, formats, schemas, stable IDs, xG
   model/build/export version, snapshot ID, timestamps, manifest and checksums
   contractual delivery requirements;
5. require correction notices, versioned replacements, a change log, retention
   and use of prior versions, and disclosure of historical xG recalculation;
6. permit confidential backup/disaster-recovery copies and approved internal
   compute or contractor access needed for the work;
7. permit aggregate, non-reconstructive evaluation results and reproducibility
   statements, and state exact attribution rules, while allowing a ban on raw
   redistribution; and
8. state survival after termination and explicit precedence over conflicting
   MSA §§1.5–1.7, 2.6 and 9.4 and AUP restrictions.

The MSA gives the Order the highest precedence. An SOW is incorporated into an
applicable Order for professional services; MatchForge must not assume that a
standalone SOW or sales email overrides the MSA. A signed quote may itself be
an Order, so no quote or proposal may be signed under the `$0` authorization.

## Engineering after licensing

After a separate owner approval of price, final agreement and exact delivery:

1. obtain separate authorization for the delivery method, access credentials,
   request budget if applicable, isolated data root and raw retention;
2. preserve the delivered bytes without modification and record the provider
   export ID, contract scope, complete file manifest and SHA-256 hashes;
3. compare schema and xG semantics with the existing StatsBomb adapter; add only
   the smallest licensed-export adapter changes actually required;
4. verify xG values on the public overlap and the provider's same-series
   attestation before any feature or corpus work;
5. map provider competition, season, match, team, player, event and shot IDs to
   MatchForge IDs while preserving every provider ID and correction alias;
6. validate match/event/lineup completeness, retained non-penalty shot xG,
   lifecycle, kickoff/timezone, correction and source details;
7. build exact prior-only target plans with same-kickoff batching and run the
   protected/development firewall without opening protected outcomes;
8. return exact eligible counts, manifests, hashes, warnings and failures for a
   separate owner decision on corpus membership;
9. only after corpus approval, freeze the complete pre-registration; then use
   separate approvals for challenger implementation, verification and the one
   authoritative Evaluation V2 run. Rust requirements remain unchanged.

Source-neutral hash, snapshot, identity, correction, target-plan and firewall
machinery already exists. Before licensing, only decision records, provider
questions, contract review and concrete synthetic regression tests can proceed.
Provider-specific adapters, acquisition, raw retention, real-data qualification,
target counts, corpus hashes, model fitting and Evaluation V2 cannot.

## Owner approval sequence

1. Confirm the action-time send of the prepared non-binding request. This may
   transmit the owner's sender name and reply address to StatsBomb; it must not
   include payment details or accept terms.
2. After a written response arrives, approve or reject the exact season/export
   scope, xG compatibility evidence, proposed contract exceptions and quoted
   price. Reviewing a proposal does not authorize acceptance.
3. If acceptable, separately authorize the final signed Order/amendment and
   raise the `$0` ceiling to an explicit total amount. No signature or purchase
   may occur before this decision.
4. Separately authorize data delivery/acquisition, credentials or request
   budget, isolated storage and raw retention under the approved agreement.
5. After engineering qualification, approve or reject exact corpus membership,
   source/dataset manifests, target hashes, exclusions and firewall evidence.
6. Separately freeze the complete pre-registration and release the challenger
   implementation and verification tickets.
7. Separately authorize the single authoritative Evaluation V2 run. Preserve
   the mandatory Rust simulation requirement and all frozen thresholds.

## Non-binding provider request

The exact request should ask StatsBomb for a proposal, not an Order, trial,
account or data delivery:

```text
Subject: Non-binding proposal request — fixed historical StatsBomb export for private model evaluation

Please provide a non-binding technical and commercial proposal for complete
men's Bundesliga 2023/24 and Ligue 1 2022/23 match metadata, lineups and event
data. No data, trial, account, Order, SOW or paid service should be activated.

For each season, please provide the exact match list/count and confirm complete
shot coverage, penalty/period fields, kickoff/timezone and lifecycle metadata.
Identify the pre-shot xG field and exact model/build/export version. Confirm
whether it is one fixed series compatible with the StatsBomb Open Data
shot.statsbomb_xg values in La Liga 2015/16, Serie A 2015/16 and the public
partial Bundesliga 2023/24 and Ligue 1 2022/23 releases.

Please describe a fixed historical export: export/snapshot ID, schema versions,
delivery/effective timestamps, file manifest/checksums, stable competition,
season, match, team, player, event and shot IDs, point-in-time/source metadata,
and the correction/revision policy including prior-version retention.

Please provide draft written terms that expressly permit permanent private raw
and derived-data retention, backups, normalization, hashing, statistical/ML
model development, features, forecasts, calibration, evaluation, simulation,
and internal reproducibility archives after contract end. Please also state
aggregate publication and attribution rules and all deletion obligations.

Finally, provide an itemized non-binding quote: currency, taxes, licence term,
export/support fees, delivery schedule and quote validity. MatchForge currently
has zero spending authority and will not accept or sign any agreement in
response. Please do not send data or activate access.
```

## Decision

StatsBomb **could** satisfy Evaluation V2 without weakening the frozen rules,
and the proposed scope has enough provisional targets. It is not yet qualified.
The route remains blocked until written provider evidence, a compliant draft
agreement and a quote return for owner review. If the fixed xG series, permanent
reproducibility rights, exact inventory or 500-target margin cannot be proved,
the route fails under the current frozen requirements; those requirements must
not be relaxed.
