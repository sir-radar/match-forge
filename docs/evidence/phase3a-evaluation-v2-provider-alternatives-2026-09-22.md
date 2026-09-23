# Evaluation V2 provider alternatives — 2026-09-22

Status: `RESEARCH_ONLY`. No provider, season, target, or corpus is admitted.
No source data was purchased, downloaded, or ingested in this alternatives
investigation; Evaluation V2 was not run.

## Decision to make

The [frozen corpus policy](owner-decision-approve-phase3a-evaluation-v2-corpus-policy-2026-09-21.md)
requires three independent complete men's domestic-league seasons across at
least two competitions and two seasons, and at least 500 eligible targets.
The [isolated Serie A qualification](phase3a-serie-a-2015-16-isolated-qualification-2026-09-22.md)
supplies one group and 280 eligible targets, without admitting it to the
corpus. Two more complete groups and at least 220 more targets are needed.
The [frozen feature decision](owner-decision-approve-phase3a-xg-for-feature-mathematics-2026-09-21.md)
requires `shot.statsbomb_xg`; neither a different provider's xG nor an xG
model fitted from other events is an automatic substitute. The checked public
StatsBomb revision supplies no two further complete men's groups, as the
[source-discovery screen](phase3a-evaluation-v2-mens-source-discovery-2026-09-22.md)
records.

## Provider comparison

| Route | Complete men's seasons and shot xG | Cost and use rights | Reproducibility and MatchForge fit | Current verdict |
| --- | --- | --- | --- | --- |
| StatsBomb open data | Pinned Serie A 2015/16 qualifies as one source group; the checked public revision has no two more complete men's groups. Its events contain the frozen `shot.statsbomb_xg`. | Public research release, but the reviewed revision cannot supply the remaining corpus. Any new commercial entitlement has unknown price and terms. | Existing adapter, IDs, event/lineup shape, and feature decision fit this route. Pinned Git SHA and raw hashes support immutable replay. | Free route insufficient. |
| Licensed Hudl Statsbomb historical export | [Product description](https://www.hudl.com/products/statsbomb) advertises event data, xG, API and JSON/XML/CSV delivery across many competitions. **Neither full Bundesliga 2023/24 nor Ligue 1 2022/23 inventory, exact shot field, or export version is confirmed.** | Quote and data-retention/research rights unknown. A sales inquiry is not an offer, contract, or purchase authority. | Most plausible way to retain Decision 1 and the qualified Serie A source. Must prove a fixed export, exact pre-shot `shot.statsbomb_xg` semantics, event/lineup completeness, source hashes, and provider-ID mapping. A live API field named `xg` is not presumed equivalent. | First route to investigate; not yet qualifiable. |
| Understat | [Official site](https://understat.com/) lists Bundesliga, Serie A and Ligue 1 and says its xG comes from its own trained model. [Bundesliga 2023/24](https://understat.com/league/Bundesliga/2023) and [Ligue 1 2022/23](https://understat.com/league/Ligue_1/2022) are visible season leads. Complete fixture, shot, and eligible-target counts are unverified. | Pages are viewable without payment. No current official bulk-export license, redistribution/retention permission, versioned download, API service level, or price was found. Free page viewing is **not** permission for bulk acquisition. | Shot-level xG is displayed in match views, but a documented export contract and stable model/source version are missing. Different xG values require a new feature ID, provider adapter and identity mapping, plus development/evaluation comparability review. | Possible redesign only after rights, data and owner decisions; not a drop-in free corpus. |
| Public Wyscout/Pappalardo Figshare release | The [dataset paper](https://iris.cnr.it/bitstream/20.500.14243/362201/1/prod_412387-doc_145167.pdf) identifies full 2017/18 men's La Liga, Serie A, Bundesliga, Premier League and Ligue 1 seasons; [collection v5](https://figshare.com/collections/Soccer_match_event_dataset/4415000/5) is public. The [published event schema](https://figshare.com/articles/dataset/Events/7770599) has shots, times, periods, tags, IDs and positions but **no shot xG field**. | Download is publicly available under CC BY 4.0 with attribution. The [commercial Wyscout pricing page](https://www.hudl.com/products/wyscout/pricing) instead asks for a quote for data/API packages; no free shot-xG entitlement is shown. | Figshare DOI/version and file checksums could pin raw events, but a separate xG derivation would be a different experiment. MatchForge has no approved Wyscout xG provider contract. EPL in this release remains excluded by the protected-data firewall. | Strong free event coverage; cannot supply the frozen xG feature. |
| FotMob public pages | Official pages retain [Bundesliga 2023/24](https://www.fotmob.com/leagues/54/matches/bundesliga?season=2023-2024) and [Ligue 1 2022/23](https://www.fotmob.com/leagues/53/overview/ligue-1?season=2022-2023) tables/results. FotMob describes xG in matches and player views; current pages show per-shot xG. Complete historical shot coverage remains unverified. | [FotMob's terms](https://www.fotmob.com/tos.txt) require written consent for use of displayed data and expressly forbid automated, systematic, regular, or bulk retrieval. Private non-commercial research does not remove that restriction. No public data-license price or authorized bulk API was found. | FotMob says detailed match data and xG are powered by Opta. No stable export, schema/version, correction history, retention right, or source hash is available through public pages. FotMob/Opta xG is not `shot.statsbomb_xg`. | Not qualifiable through free public access. Written permission plus a versioned export would be required before acquisition research. |

The Figshare release's complete-season statement is a publisher claim, not a
MatchForge fixture/lifecycle check. Its [matches file](https://figshare.com/articles/dataset/Matches/7770422)
and events file have versioned public records, but no files were downloaded
here. The commercial [Wyscout Events Pack](https://www.hudl.com/products/wyscout/data-api)
advertises event locations, not a verified per-shot xG entitlement. The
[StatsBomb FAQ](https://www.hudl.com/products/statsbomb/faq) supports xG and
API availability in general, not either named season or a specific export.
Understat's public site does not state an export or reuse license. These are
limits of the checked evidence, not assertions that a vendor cannot supply
the missing material privately.

## FotMob follow-up — 2026-09-23

FotMob is not a free acquisition route under its current terms. Public pages
show enough product coverage to make a permission inquiry reasonable, but not
enough to qualify a source. The historical Bundesliga table records 18 clubs
with 34 matches each; the Ligue 1 table records 20 clubs with 38 matches each.
Under ideal round-order screening, targets after a 10-match warm-up would be
216 and 280 respectively. Those are capacity estimates only. Missing shot xG,
uneven kickoff order, lifecycle exclusions, source corrections, and integrity
checks can reduce them; exact eligible counts are `NOT_RUN`.

[FotMob's xG announcement](https://www.fotmob.com/nl/topnews/3627-live-xg-data-is-now-fotmob)
defines xG as a shot's scoring likelihood and says xG appears in matches,
lineups, team pages and player pages. Current match pages also expose results,
kickoff, lineups and aggregate xG. This does not prove that every shot from
both named seasons is retained, that penalties and periods can be selected
exactly, or that one unchanged Opta model produced all values. FotMob's public
URLs expose league IDs, but no official stable match/shot ID or bulk API
contract was found.

Direct Opta access is commercial, not a free FotMob workaround. Stats Perform
advertises [deep historical data and Expected Goals](https://www.statsperform.com/products/opta-data/)
and says [pricing is quote-based](https://www.statsperform.com/faqs/stats-perform-faqs-pricing-licensing/).
No price, exact seasons, research terms, export version, or per-shot field was
verified for MatchForge.

No exact Decision 1 amendment is ready for approval. The provider field name,
model/version, period and penalty semantics, and stable source contract are
unknown. If written FotMob or Opta terms later supply those facts, the owner
would need to approve a new feature ID rather than reuse
`MATCHFORGE_NPXG_FOR_LAST10_V1`, replace `shot.statsbomb_xg` with the exact
licensed pre-shot xG field, and amend Decision 2 so development and evaluation
use one comparable provider/model version. All other mathematics and leakage
rules would remain unchanged. Until then, inventing an `OptaV1` contract or
scraping undocumented endpoints is prohibited.

## Qualification risks shared by all routes

- A web season page or catalog count cannot establish complete league coverage,
  100% finite retained-shot xG, exact kickoff times, lifecycle, or 220 eligible
  targets. Each group needs isolated raw snapshots, immutable source and
  normalized dataset IDs/hashes, a full fixture check, and exact target plan.
- Retrospective research must use the approved fixed-snapshot knowledge mode.
  Record acquisition time and source revision; construct features only from
  earlier eligible matches in the same season. Freeze every same-kickoff batch
  before revealing outcomes. Provider-postprocessed xG must not be treated as
  historically published unless that claim is separately supported.
- Map provider match/team identities to stable MatchForge IDs using explicit
  evidence. Do not join providers by names or approximate shot times. Prove
  zero intersection with protected EPL and development-source IDs without
  opening protected outcomes.
- Keep the existing goals-only baselines, immutable published forecasts,
  mandatory future Rust simulation boundary, and frozen evaluation thresholds
  unchanged. No route permits a new forecast or Evaluation V2 run now.

## Recommended route and stop points

Ask Hudl Statsbomb for a **non-binding written availability and license
answer** for two complete men's domestic seasons, initially Bundesliga
2023/24 and Ligue 1 2022/23. Those are examples to check, not approved or
confirmed inventory. A usable response must identify exact season coverage,
match/event/lineup export, pre-shot `shot.statsbomb_xg` definition and model
version, stable export/snapshot identity, correction policy, kickoff/timezone
and lifecycle fields, permitted retention/hash publication and research use,
delivery format, and a non-binding price. If either example is unavailable,
ask for other complete men's domestic seasons satisfying the same two-group,
second-competition and second-season needs. A written answer is followed by
owner review; it grants no acquisition or ingestion authority.

This is the least disruptive route **if** the vendor can document a compatible
export and acceptable terms. No currently verified source meets all frozen
rules. If it fails, Understat requires a new owner-approved feature decision,
revised development/evaluation source policy, and a newly approved complete
pre-registration before any implementation. The free Wyscout release cannot
repair the present blocker without designing or sourcing another shot-xG
model, which would change the hypothesis.

## Conditional Decision 1 amendment for Understat

Do **not** apply this text yet. It is a precise proposal only if a lawful,
complete, versioned Understat shot export is first demonstrated and the owner
chooses that route. In [Decision 1](../governance/phase3a-xg-for-evaluation-v2-freeze-proposal.md),
replace only the following feature-source entries:

```text
Feature ID:       MATCHFORGE_UNDERSTAT_NPXG_FOR_LAST10_V1
Provider field:   Understat's per-shot xG value in one owner-approved,
                  immutable, versioned export, with its field name, model
                  version, source ID and SHA-256 recorded before use
Included shots:  regulation periods 1 and 2; every non-penalty shot whose
                  type, period, team and xG can be mapped unambiguously
Excluded shots:  penalties and all other periods; ambiguity fails source
                  qualification, never silently drops an event
```

Retain Decision 1's match sum, 10-prior-match same-season window, reference
mean, log signal, one coefficient, optimization, invalid-value failures, and
same-kickoff seal **unchanged**. Do not reuse
`MATCHFORGE_NPXG_FOR_LAST10_V1` for incompatible xG values. Use one xG
provider/model version for both development and authoritative groups; no
StatsBomb/Understat value mixing or approximate cross-provider shot joins.
If an Understat export cannot prove penalty and period semantics or stable
pre-shot xG values, reject this amendment rather than weaken those rules.

This is not merely a Decision 1 edit. Decision 2's StatsBomb-based development
source and already qualified Serie A group would need explicit replacement or
requalification under a coherent same-provider design. Exact source groups,
target counts and firewall IDs would need new qualification and a new corpus
freeze. The complete preregistration must be updated and explicitly approved
again before implementation tickets can be released. Costs and rights remain
unknown, so the owner should not approve the amendment on this record alone.

For Wyscout's free release, **no Decision 1 field substitution is available**:
its published schema lacks shot xG. Fitting an xG model or obtaining a separate
licensed metric would be a new hypothesis and governance route, not a narrow
amendment.

## Bounded StatsBomb inquiry

The repository owner supplied the sender name and reply address for the
inquiry. On 2026-09-22 the official [Hudl professional contact form](https://www.hudl.com/contact/sales/professional)
was inspected. It requires a phone number and states that submission consents
to promotional, marketing and sales contact. No phone number or such consent
was supplied, so **the form was not submitted**. An older [StatsBomb report](https://blogarchive.statsbomb.com/uploads/2023/01/Major-League-Soccer-2022-StatsBomb-360-Report.pdf)
publishes `sales@statsbomb.com`, but its current routing was not verified and
no email-send channel was available in that session. On 2026-09-23 the owner
reported that the email was sent. No vendor response or quote has been
received.

Draft for a direct email, subject to owner choice of channel:

```text
To: sales@statsbomb.com
From: [repository owner — reply address intentionally omitted from source control]
Subject: Non-binding research inquiry — versioned men's historical event data

Hello Hudl Statsbomb team,

I am researching whether a fixed historical export could support a
reproducible football-model evaluation. This is an
availability and terms inquiry only; I am not requesting a trial, purchase,
account, or delivery of data.

Could you confirm whether complete men's Bundesliga 2023/24 and Ligue 1
2022/23 regular seasons are available as versioned match metadata, events and
lineups? If not, which two other complete men's domestic-league seasons in
different competitions and seasons could be supplied? We need a per-shot
pre-shot xG value demonstrably equivalent to StatsBomb Open Data's
shot.statsbomb_xg, including its model/version and correction policy. Please
describe export formats, stable revision identifiers, kickoff/timezone and
match lifecycle fields, and whether terms permit retaining immutable raw
bytes, checksums and derived aggregate qualification evidence for research.

Please also provide an indicative, non-binding price and any limits on
research, local retention, reproducibility or publication of aggregate
findings. We do not need Premier League or La Liga data. No data should be
sent or charged for in response to this inquiry.

Thank you,
[repository owner]
```

## Owner boundary

No decision is being approved here. Before acquiring any source, the owner
must choose the provider route and authorize exact scopes, terms/cost and
isolated acquisition. An Understat route additionally requires the explicit
Decision 1 and Decision 2 amendments described above. Exact corpus membership
and Evaluation V2 execution remain separate later approvals. Follow-up work
is tracked in the Wayfinder map; the existing men's source-qualification
ticket remains open. FotMob public access is rejected as a free source unless
written consent and an exact versioned export change the available evidence.
