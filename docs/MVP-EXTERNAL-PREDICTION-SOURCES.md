# MVP external prediction sources

Checked 30 September 2026. Collection is fail-closed: no automated adapter is enabled without clear public access and permission for the intended reuse. Login-only, paid/VIP, CAPTCHA-protected, rate-limit-circumvented and anti-bot-bypassed content is prohibited.

| Source | URL | Public | Dated | Markets / coverage | Login / paid | Automated-access assessment | Adapter / enabled | Known issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R2Bet | https://r2bet.com | Public pages exist | No reliable mandatory date found | Football selections; paid boundaries exist | No login for public pages; paid material exists | `REVIEW_REQUIRED` | `DISABLED` / no | No clear collection or reuse permission found. |
| 1960Tips | https://www.1960tips.com | Public free tips exist | Yes | Common football tip markets and multiple leagues | Free and paid content | `UNSUPPORTED_TERMS` | `DISABLED` / no | April 2026 terms prohibit distribution, republication, public display, and other reuse without written permission. |
| SlyBet | https://slybet.net | Public pages exist | No reliable mandatory date found | Football prediction pages | Public pages; paid status unclear | `REVIEW_REQUIRED` | `DISABLED` / no | Robots allows crawling; reuse terms remain unverified. |
| MatchOutlook | https://www.matchoutlook.com/todays-football-predictions | Public | Yes | Daily football predictions | Public and paid presentation | `UNSUPPORTED_TERMS` | `DISABLED` / no | Current terms prohibit reproduction or lifting of site material. |
| Forebet | https://www.forebet.com | Public presentation | Yes | Broad football predictions | Public and paid presentation | `UNSUPPORTED_ANTI_BOT` | `DISABLED` / no | Managed anti-bot challenge; MatchForge will not circumvent it. |

The persistence and API framework preserves source page, displayed prediction date, original date text, collection time, competition, teams, mapped market/selection, revision, fixture mapping and settlement. Repeated changed picks create new immutable revisions. Supported mappings include 1/X/2, 1X, X2, BTTS/GG, over 2.5 and under 2.5. An enabled `manual_import` adapter accepts owner-supplied JSON only; it does not scrape or grant permission to reuse a source.

`make external-predictions` and its `DATE=` / `SOURCE=` variants return `NO_APPROVED_SOURCES` when no approved import file is configured. Set `MVP_EXTERNAL_PREDICTIONS_IMPORT_FILE` to an owner-approved JSON file to run the append-only import during the same command and scheduled job. Set `SOURCE=` to the reviewed source code when the file contains that source's records; otherwise records retain the generic `manual_import` source. `scripts/mvp-refresh.sh` is the scheduler entry point. The systemd timer runs it at 06:00 `Africa/Lagos`.

No consensus or source-performance claim is produced when zero approved selections exist. Once records exist, the daily sync settles supported selections from matched completed fixtures. `/predictions` groups consensus without changing MatchForge probabilities and filters source performance by source, league, market, and date range.
