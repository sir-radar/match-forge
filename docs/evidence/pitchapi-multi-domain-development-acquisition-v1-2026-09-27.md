# PitchAPI multi-domain development acquisition result

## Result

`PITCHAPI_MULTI_DOMAIN_DEVELOPMENT_ACQUISITION_V1` finished as
`DEVELOPMENT_CORPUS_QUALIFIED`.

The exact five development-only groups produced 1,270 eligible targets across
four competitions and two seasons. The 1,200-target floor passed. Outcome
counts are 518 home wins, 322 draws, and 430 away wins. Every group passed its
200-target and 40-per-outcome-class requirements.

| Group | Nominal / valid matches | Shots / valid npxG | Eligible targets |
| --- | ---: | ---: | ---: |
| Bundesliga 2024/25 | 306 / 305 | 7,954 / 7,846 | 215 |
| Bundesliga 2025/26 | 306 / 306 | 8,130 / 8,001 | 216 |
| Premier League 2024/25 | 380 / 380 | 9,883 / 9,767 | 280 |
| La Liga 2024/25 | 380 / 380 | 9,065 / 8,909 | 280 |
| Serie A 2024/25 | 380 / 380 | 9,250 / 9,109 | 279 |

Bundesliga 2024/25 fixture `m_3ICf7e` was provider-labelled `awarded` and was
quarantined before shot acquisition, target construction, and history updates.
No replacement fixture or group was introduced.

## Integrity

Canonical mapping passed with 1,751 fixture aliases, 80 team aliases, no
ambiguity, and no unresolved admitted fixture. The development corpus has zero
intersection with all 712 V5 targets, all 928 prior spent PitchAPI targets, and
760 protected StatsBomb fixture identities. Scope-level intersections are also
zero.

Snapshot `9acd90ce-b847-5ab4-8e2b-b98d5602da70` has identity SHA-256
`5d179ba9933ee2284d3646a1298f0305c355a5cf178e5e580fe974b28e97b1e5`.
The corpus manifest SHA-256 is
`2ace8fb86f8881dae1baeb5c7cdb277e1174e124eb264def17f658b9550c2193`;
the firewall SHA-256 is
`8b67bb05d52768b8163ce205db2fbc127f22ff879206b1f9fd11ff46b9c87704`.

Primary and backup contain identical independent file inventories. Their
inventory SHA-256 is
`ba9f941a7e209929c9c3aa77deed8de410a644f7fc90b9a91186beecf5a8f594`.
Both trees are read-only. Combined logical size is 122,630,054 bytes.

## Request and provider limits

The three immutable acquisition revisions used 1, 2, and 1,757 calls: 1,760
task-wide, below the frozen 1,794 hard ceiling. The completed revision had no
retry or rate-limit response.

PitchAPI does not expose the upstream xG model version or correction history.
The snapshot freezes exact raw values and provider-labelled penalty, own-goal,
period, and shot-situation semantics, but cannot reconstruct an upstream model
version that the provider does not publish. Confirmation reserve requirements
exist, but no confirmation groups have been selected or acquired.

No model was fitted. V6 and confirmation were not executed.

## Owner boundary

The acquired corpus supports preparing
`TRANSFERABLE_ROLLING_NPXG_FOR_AGAINST_DIXON_COLES_V2` research. The next owner
decision is whether to authorize the separately prepared development-only model
implementation, preregistration, and comparison package. That decision must not
authorize confirmation acquisition or execution, V6, promotion, or deployment.
