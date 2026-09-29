# MatchForge H2H development-history acquisition V3 result

## Classification

`H2H_DEVELOPMENT_HISTORY_INSUFFICIENT`

PitchAPI fixture `m_3ir3kE` is Spezia 1–3 Hellas Verona, kicked off at `2023-06-11T18:45:00Z`, status `finished`, competition `l_0ALvwF` Serie A, season `2022/2023`. PitchAPI match detail reports `round_name: final`, `has_playoff: false`, and no separate stage field. Official Lega Serie A material identifies the fixture as the 2022/23 relegation play-out (`Spareggio Salvezza`). It was excluded as `POSTSEASON_FIXTURE_EXCLUDED_BY_FROZEN_COMPETITION_STAGE_RULE`; its raw manifest and match-detail evidence remain retained.

The frozen rule admits only fixtures in the ordinary regular-season schedule. It excludes verified relegation, promotion, championship, qualification, and other postseason league stages. Score, participants, H2H coverage gain, model results, and target-count convenience cannot decide eligibility. Ambiguity returns `PROVIDER_COMPETITION_STAGE_AMBIGUOUS`.

All acquired historical scopes passed complete directed-schedule checks. No postseason fixture was found in Bundesliga 2024/25, Premier League 2022/23, Premier League 2023/24, or Serie A 2023/24. Serie A 2022/23 passed after the single verified exclusion, leaving exactly 380 regular-season fixtures.

## Acquisition and coverage

Serie A 2022/23 contains 9,682 shots and 9,543 valid npxG shots after excluding 108 penalties and 31 own goals. It changed global 3+ coverage from 457 to 507 but did not change global 2+ coverage:

| Coverage | Targets |
|---|---:|
| 1+ | 1,069 |
| 2+ | 593 |
| 3+ | 507 |
| 5+ | 3 |

Per-competition 2+/3+ coverage is Bundesliga 169/120, Premier League 224/201, and Serie A 200/186. All three competitions pass the 150-target 2+ floor. Global 3+ passes. Global 2+ remains seven short.

Bundesliga 2023/24 has enough theoretical capacity to close seven targets, but it is both a V5-protected scope and a prior-spent PitchAPI evaluation scope. Acquiring it would deterministically fail the frozen firewall. The bounded extension was not acquired.

## Snapshot, backup, and firewall

No qualified `MATCHFORGE_H2H_DEVELOPMENT_HISTORY_V3` final snapshot was created because the 600-target 2+ floor failed. The completed immutable intermediate acquisition snapshot is `d0da187c-88d0-5eb1-b08b-01bdaf097622`, SHA-256 `09280f173008cffd4a05f7b71859b0588814d552e7dea8b5846474bebbd5e308`.

Primary and independent backup each contain 3,061 files. Their inventories match at SHA-256 `430ad4efd52bbd06551dea11547bef1a553d05f42cb67b901f31621dc43a12af`; both are read-only.

The completed-package firewall passes with zero intersections across fixed development targets, V5 spent targets, prior spent PitchAPI fixtures/scopes, protected StatsBomb fixtures/scopes, V5 protected scopes, and confirmation-reserved targets. Strict prior kickoff and same-kickoff sealing remain active.

V2 remains `PROVIDER_DATA_INCOMPLETE`; its result and report hashes are unchanged. No H2H model was fitted or evaluated. No confirmation data or V6 work occurred. H2H research is not supportable under the frozen coverage floor.

## Owner boundary

Next owner decision: `AUTHORIZE_OR_DECLINE_FIREWALL_SAFE_H2H_HISTORY_EXTENSION_V1`.

Any new history must avoid all spent/protected targets and scopes, preserve the frozen regular-season rule, and be able to close the exact seven-target 2+ gap. Otherwise close the H2H route without fitting or evaluation.
