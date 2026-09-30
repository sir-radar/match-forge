# MVP completion audit

Checked 30 September 2026 against the owner request “MatchForge MVP Completion Enforcement”. Status values are `PASS`, `PARTIAL`, `NOT_APPLICABLE`, and `FAIL`.

| ID | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Preserve existing work | PASS | Task diff keeps `web/ui-designs/`, research evidence, model artifacts, migrations, and APIs. |
| 2 | Research remains paused | PASS | `docs/project-status.json`; no research, model fitting, calibration, promotion, or probability adjustment changed. |
| 3 | Capability truth | PASS | `football/product/sync.py`; context flags start false and become true only after stored history exists. API-Football no longer advertises unimplemented H2H/team-stat calls. |
| 4 | Current forecasts | PASS | `make mvp-sync DATE=2026-10-10 MAX_HISTORY_LEAGUES=20`: six real EPL fixtures, 380 history matches, 20 standings rows, five forecasts. Ten-match rule unchanged. |
| 5 | Multi-source fallback | PASS | `football/product/football_data_org.py`; explicit competition map in `football/product/sync.py`; fixture, history, standings, and reconstructed-standings routes. |
| 6 | H2H product contract | PASS | `GET /v1/fixtures/{id}/context`; meeting rows, summary counts, aggregate goals, optional xG, limited-history state, and display-only UI notice. |
| 7 | Team statistics | PASS | Context API derives recent goals and averages only from stored completed matches; advanced unavailable fields remain absent. |
| 8 | `/performance` | PASS | `GET /v1/performance`; continent, country, league, rating, and minimum-count filters; league table contains rating, forecasts, 1X2, top-three, top-five, Brier, log loss, and recent Brier. |
| 9 | `/predictions` | PASS | Date, source, continent, country, competition, market, and agreement filters; required row fields and empty state. |
| 10 | External collection | PASS | R2Bet, 1960Tips, SlyBet, and MatchOutlook returned HTTP 200 and parsed 29 supported public selections. Forebet returned HTTP 403 and remains `TECHNICALLY_UNAVAILABLE`; no bypass was attempted. `docs/MVP-EXTERNAL-PREDICTION-SOURCES.md`; `make external-predictions DATE=2026-09-30`. |
| 11 | External storage/revisions | PASS | `football.external_predictions`; append-only revision hash; `football/product/external_predictions.py`; parser/import tests. |
| 12 | Market normalization | PASS | `football/product/domain.py`; `test_product_domain.py`; manual-import parser tests. |
| 13 | Agreement logic | PASS | Python and Go tests prove probability-derived agreement independent of source count. |
| 14 | Consensus | PASS | `web/components/predictions-page.tsx`; stored selections are grouped without altering MatchForge forecasts. |
| 15 | External-source performance | PASS | Filtered source, league, market, and date-range API/UI with tracked, settled, correct, hit-rate, and MatchForge-agreement metrics. |
| 16 | Product model label | PASS | Main fixture and performance UI display “MatchForge Forecast”; `MVP_FORECAST` remains internal. |
| 17 | Preserve UI design | PASS | Existing dense fixture layout, inline expansion, mobile layout, tabs, dark styling, and design assets remain. |
| 18 | History/simulation/diagnostics | PASS | Stored forecast details display; no simulation or unauthorized research claim was added. |
| 19 | Caching/rate limits | PASS | External adapters fetch one requested page per source per run and parse the cached response in memory. The daily schedule makes one pass; it does not recursively crawl. Source failures are isolated. |
| 20 | Scheduled jobs | PASS | `scripts/mvp-refresh.sh` runs sync then external import/collection; systemd timer remains 06:00 Africa/Lagos. |
| 21 | Focused tests | PASS | Provider transport, empty-response fallback selection, leakage boundary, market mapping, import parsing, rating, agreement, H2H/team summaries, UI, mobile, and accessibility coverage. |
| 22 | Frontend in main gate | PASS | Root `make check` includes frontend lint, typecheck, unit tests, and production build; CI runs Playwright/axe. |
| 23 | One-command startup | PASS | `make dev` remains PostgreSQL + migrations + Go API + Next.js; `.env.example` documents both provider tokens and optional import file. |
| 24 | Evidence matrix | PASS | This file plus live command output and repository tests. |
| 25 | Critical completion gate | PARTIAL | Live fixture → history → stored forecast → API/UI is proven. Live external collection stored 29 selections across four sources. Live result settlement/performance for the 2026-10-10 forecasts cannot occur before those matches finish; deterministic settlement/performance tests cover the path meanwhile. |
| 26 | Required verification | PARTIAL | `make check` passed: 633 Python tests, 15 Rust tests, Go tests, lint/type/static checks, package builds, project-status validation, and frontend lint/type/unit/build checks. `make integration` passed fresh migrations, storage invariants, and PostgreSQL/Redis/Go service checks. Live external collection inserted 29 rows; the immediate rerun inserted 0. PR #134 is open; its CI must pass before merge. |
| 27 | Final delivery report | PASS | PR description and final owner handoff include required counts, providers, tests, limitations, and research state. |
| 28 | Stop conditions | PASS | No access-control bypass, fabricated data, weaker history rule, research restart, or forecasting-math change. |

## Current live counts

```json
{
  "catalog_competitions": 1240,
  "first_division_records": 643,
  "second_division_records": 67,
  "fixture_only_competitions": 1239,
  "forecastable_competitions": 1,
  "verification_date": "2026-10-10",
  "live_fixtures": 6,
  "stored_history_matches": 380,
  "standings_rows": 20,
  "generated_forecasts": 5,
  "external_automated_adapters": 4,
  "external_manual_import_adapters": 1
}
```

## Completion classification

```text
MVP_PRODUCT_IMPLEMENTATION_COMPLETE
MVP_AUTOMATED_EXTERNAL_PREDICTION_COLLECTION_ENABLED_4_SOURCES
FOREBET_AUTOMATED_COLLECTION_TECHNICALLY_UNAVAILABLE
MVP_LIVE_SETTLEMENT_EVIDENCE_PENDING_MATCH_COMPLETION
MODEL_RESEARCH_PAUSED_FOR_MVP
```

Do not publish `MVP_COMPLETE` until the five live forecasts settle after kickoff, their league-performance records are visible, and the PR CI run passes.
