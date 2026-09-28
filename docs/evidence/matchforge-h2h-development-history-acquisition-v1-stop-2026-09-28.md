# MatchForge H2H development-history acquisition stop

## Classification

`ACQUISITION_FAILED`

The acquisition stopped fail-closed after 383 of the maximum 1,167 requests. There were no retries or rate-limit responses. No model was fitted or evaluated, no new target was created, no confirmation data was acquired, and V6 was not created.

## Provider discrepancy

Premier League 2023/24 completed its 380-fixture manifest and all 380 shot resources. The next authorized manifest, La Liga 2023/24, returned 379 finished fixtures rather than the frozen nominal 380. Girona and Mallorca each appear in only 37 fixtures; the returned manifest contains Girona 5–3 Mallorca on 2023-09-23 but omits the Mallorca-home meeting against Girona.

The exact full-season guard returned `FULL_SEASON_MATCH_COUNT_MISMATCH` before La Liga mapping or shot acquisition. Serie A was not requested after the stop.

| Season | Nominal | Finished returned | Mapped | Shot resources | Shots | Valid npxG shots | Penalties | Own goals | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Premier League 2023/24 | 380 | 380 | 380 | 380 | 10,538 | 10,382 | 107 | 49 | Partial snapshot; not admitted |
| La Liga 2023/24 | 380 | 379 | 0 | 0 | 0 | 0 | — | — | Failed manifest count |
| Serie A 2023/24 | 380 | 0 | 0 | 0 | 0 | 0 | — | — | Not requested |

## Snapshot and backup

Attempted snapshot ID: `cee3a221-f81b-550d-a9b4-e7804c99dd04`.

No qualified snapshot identity or snapshot SHA-256 was created. The read-only partial primary contains 766 files and 12,244,333 bytes, with inventory SHA-256 `ca156d2f2852551a31d6ba30a04e8e17c5ae2f41a570d0536456e67d323392a3`. It is explicitly unqualified and cannot be used as H2H history. No backup was created because backup sealing occurs only after complete qualification.

## Coverage and firewall

Coverage requalification and the final package firewall were not run because the authorized three-season package was incomplete. A diagnostic firewall check on the partial Premier League history passed with zero intersections against fixed development targets, V5 spent targets/scopes, prior spent PitchAPI fixtures/scopes, and protected StatsBomb fixtures/scopes. This is not package qualification, and partial resources were not admitted. The existing coverage remains:

| Coverage | Targets |
|---|---:|
| 0 prior | 346 |
| 1+ | 924 |
| 2+ | 169 |
| 3+ | 120 |
| 5+ | 0 |

Per-competition 2+/3+ coverage remains Bundesliga 169/120 and Premier League, La Liga, and Serie A 0/0. The 600/300 global floors fail, and only one competition has at least 150 two-meeting targets. H2H research remains `H2H_RESEARCH_NOT_CURRENTLY_SUPPORTABLE`.

## Owner boundary

No retry is authorized. The next owner decision must either authorize a new acquisition revision after the missing La Liga fixture becomes available or authorize a different exact development-history source. Model fitting, model evaluation, confirmation use, promotion, and V6 remain unauthorized.
