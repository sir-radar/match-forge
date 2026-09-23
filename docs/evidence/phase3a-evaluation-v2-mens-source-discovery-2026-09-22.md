# Phase 3A Evaluation V2 men's source discovery — 2026-09-22

Status: `RESEARCH_ONLY`. No additional group qualified or admitted.

The owner authorized source discovery, not acquisition, licensing, provider
integration, a feature-contract amendment, corpus freeze, or Evaluation V2.
The frozen [Decision 2](owner-decision-approve-phase3a-evaluation-v2-corpus-policy-2026-09-21.md)
still requires three complete men's domestic league seasons spanning two
competitions and two seasons, with at least 500 eligible targets. The qualified
Serie A 2015/16 group contributes 280 targets, so two more groups and at least
220 more eligible targets are required. [Decision 1](owner-decision-approve-phase3a-xg-for-feature-mathematics-2026-09-21.md)
still binds the feature to StatsBomb `shot.statsbomb_xg`.

## Public StatsBomb revision screen

On 2026-09-22, `git ls-remote https://github.com/hudl/open-data.git
refs/heads/master` returned `4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`:
the same revision already pinned locally. Read-only checks of that revision's
previously retained match lists found:

| Men's group | Matches in list | Match-list SHA-256 | Screen |
| --- | ---: | --- | --- |
| [Bundesliga 2023/24, `9/281`](https://raw.githubusercontent.com/hudl/open-data/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/data/matches/9/281.json) | 34 | `13dff90f126d9f73da410ae3292b2773744657d3ba968a2b7a9c02135033581c` | One-club release; below 120 and not a complete league. |
| [Bundesliga 2015/16, `9/27`](https://raw.githubusercontent.com/hudl/open-data/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/data/matches/9/27.json) | 34 | `1fd6519dc64f268e40395a2e65c82f1feb9974c2705253a2af2c37aa34a5655d` | Below 120 and not a complete league. |
| [Ligue 1 2021/22, `7/108`](https://raw.githubusercontent.com/hudl/open-data/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/data/matches/7/108.json) | 26 | `a3b2c322f18a621305720bbf79d68f581441de8657ca53b33901fcf867bf0c0f` | Below 120 and not a complete league. |
| [Ligue 1 2022/23, `7/235`](https://raw.githubusercontent.com/hudl/open-data/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/data/matches/7/235.json) | 32 | `8cab2c24952ef2668d57bb7de6c2ba93227a38fba3a3dcd9d425e5749f515f8a` | Below 120 and not a complete league. |
| [Ligue 1 2015/16, `7/27`](https://raw.githubusercontent.com/hudl/open-data/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/data/matches/7/27.json) | 377 | `733c7cf47bd7a19d9acae5add722c32b404664d949377057a280bd0b0f0d2464` | Missing three fixtures; not complete. |
| [MLS 2023, `44/107`](https://raw.githubusercontent.com/hudl/open-data/4b73468fc5b0f1950f9f66fada70ad3a4f9327cb/data/matches/44/107.json) | 6 | `40d2d668c9f0ac26349dd268ee3325b011031f6322612d0b728b80a1b3c6ff6d` | Below 120 and not a complete league. |

Each listed match has a male home and away team, a regular-season stage, and a
local date and kickoff; those facts do not repair missing fixtures. The
[StatsBomb free-data description](https://blogarchive.statsbomb.com/de/neuigkeiten/freie-daten-bayer-leverkusen-bundesliga-meister/)
confirms that `9/281` covers Bayer Leverkusen's season, not the league.
StatsBomb's [Ligue 1 release note](https://blogarchive.statsbomb.com/news/the-2015-16-big-5-leagues-free-data-release-ligue-1/)
explicitly identifies the three uncollected 2015/16 matches. A corrected
public revision could be screened if one appears, but none was present at the
checked head. Older revisions have not been shown to supply both missing
groups across a second season. No protected EPL match list or admission was
opened for this screen.

## Route A — licensed StatsBomb historical exports (recommended for inquiry)

Ask Hudl Statsbomb whether it can license **two complete men's domestic league
seasons**, for example full Bundesliga 2023/24 and full Ligue 1 2022/23, with
match metadata, events, and lineups in a versioned export retaining the exact
pre-shot `shot.statsbomb_xg` meaning. These are **requested scopes**, not
confirmed inventory or approved acquisitions. The proposed pair adds a second
competition and season relative to Serie A 2015/16. The vendor describes
[broad competition coverage, event data, xG, and JSON delivery](https://www.hudl.com/en_gb/products/statsbomb),
but the [entitled competition/season list is customer-specific](https://live-data-api-guide.statsbomb.com/designing-queries/common-queries.html).
Commercial availability, historical depth, licensing terms, exact export
schema, and usable snapshot identity remain unverified.

This is the shortest route that might preserve Decision 1 without changing the
xG model. A live-API `xg` field is **not** presumed equivalent to the frozen
`shot.statsbomb_xg` field merely because both are named xG; a schema and value
comparison or an explicit owner amendment is required. A vendor proposal must
identify the exact two scopes and rights to retain immutable raw bytes and
publish reproducible research evidence. If approved, acquire into isolated
roots, then independently verify complete coverage, exact hashes, all retained
Shot xG, lifecycle and kickoff, prior-only targets, and zero protected and
development overlap. No target count can be claimed before that work.

## Route B — another xG provider (requires a feature amendment)

[Understat](https://understat.com/) publicly lists men's Bundesliga, Serie A,
and Ligue 1 xG seasons, including
[Bundesliga 2023/24](https://understat.com/league/Bundesliga/2023) and
[Ligue 1 2022/23](https://understat.com/league/Ligue_1/2022). Its own site
describes a separately trained xG model. This establishes an investigation
lead, **not** complete fixture, retained-Shot, lineage, licensing, or
point-in-time qualification. It cannot be substituted under Decision 1:
provider xG values are not `shot.statsbomb_xg`, and existing StatsBomb event
and lineup contracts cannot be silently inferred from shot pages. Before any
acquisition, the owner would need to approve a different feature/provider
contract, a licensed or explicitly permitted data path, identity mapping,
event and kickoff prerequisites, and comparability controls. Such an amendment
would change the frozen hypothesis and may require a new pre-registration.
This route is lower priority than a compatible StatsBomb export.

## Boundary and next decision

No currently checked public source revision qualifies the two missing groups.
No new data was acquired, normalized, or admitted, and no source or evaluation
outcomes were used. The owner must choose whether to authorize a bounded
commercial StatsBomb availability/licensing inquiry for two named complete
men's seasons, or separately propose a Decision 1 provider amendment. An
inquiry is not permission to purchase or ingest. Ticket
`Qualify independent men's Evaluation V2 sources` remains open until exact
source and target qualification passes.
