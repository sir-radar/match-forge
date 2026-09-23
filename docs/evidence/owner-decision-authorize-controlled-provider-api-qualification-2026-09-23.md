# Owner decision: authorize controlled provider API qualification — 2026-09-23

```text
Decision ID: AUTHORIZE_CONTROLLED_PROVIDER_API_QUALIFICATION_V1
Status:      APPROVED — RESEARCH ONLY
Owner:       repository owner / sir-radar
Map:         phase3a-xg-for-evaluation-v2-freeze
Ticket:      Owner decision: authorize provider clarifications and account probes
```

The owner confirmed that existing API credentials are stored in the ignored
repository `.env` file for API-Football, football-data.org, and PitchAPI. Only
credential variable names may be recorded:

- `API_FOOTBALL_API_KEY`
- `FOOTBALL_DATA_DOT_ORG_API_TOKEN`
- `PITCH_API_TOKEN`

The owner authorized at most ten initial read-only requests per provider,
subject to any stricter provider limit, to verify competitions, historical
seasons, Bundesliga 2023/24 and Ligue 1 2022/23 coverage, match counts,
statistics, shot-level xG, model consistency, account entitlements, identifiers,
completeness, corrections, and rate limits.

Credentials must never enter source control, documentation, logs, reports, or
tool output. Responses may be inspected in memory and only sanitized aggregate
facts may be recorded. No raw response is retained.

Football-Data.co.uk and Understat remain limited to published-access-condition
research. Clearly authorized use does not require an extra inquiry; ambiguous or
restrictive terms remain explicit blockers. No prohibited automated acquisition
or inferred permission is allowed.

No bulk acquisition, permanent ingestion, provider activation, frozen-decision
change, model implementation, or Evaluation V2 execution is authorized.
Existing evidence, protected-data restrictions, published forecasts, baselines,
and the mandatory Rust simulation rule remain unchanged.
