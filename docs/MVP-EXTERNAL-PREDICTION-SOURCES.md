# MVP external prediction sources

Checked 29 September 2026. Collection is fail-closed: no adapter is enabled without clear public access and permission for the intended automated reuse. Login-only, paid/VIP, CAPTCHA-protected, rate-limit-circumvented and anti-bot-bypassed content is prohibited.

| Source | URL | Public | Dated | Markets / coverage | Login / paid | Automated-access assessment | Adapter / enabled | Known issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R2Bet | https://r2bet.com | Public pages exist | No reliable mandatory date found | Football selections; paid boundaries exist | No login for public pages; paid material exists | `REVIEW_REQUIRED` | `DISABLED` / no | No clear collection or reuse permission found. |
| 1960Tips | https://www.1960tips.com | Public free tips exist | Yes | Common football tip markets and multiple leagues | Free and paid content | `REVIEW_REQUIRED` | `DISABLED` / no | Robots rules allow some pages but permission for automated reuse is not explicit. |
| SlyBet | https://slybet.net | Public pages exist | No reliable mandatory date found | Football prediction pages | Public pages; paid status unclear | `REVIEW_REQUIRED` | `DISABLED` / no | Robots allows crawling; reuse terms remain unverified. |
| MatchOutlook | https://www.matchoutlook.com/todays-football-predictions | Public | Yes | Daily football predictions | Public and paid presentation | `UNSUPPORTED_TERMS` | `DISABLED` / no | Current terms prohibit reproduction or lifting of site material. |
| Forebet | https://www.forebet.com | Public presentation | Yes | Broad football predictions | Public and paid presentation | `UNSUPPORTED_ANTI_BOT` | `DISABLED` / no | Managed anti-bot challenge; MatchForge will not circumvent it. |

The persistence and API framework preserves source page, displayed prediction date, original date text, collection time, competition, teams, mapped market/selection, revision, fixture mapping and settlement. Repeated changed picks create new immutable revisions. Supported mappings include 1/X/2, 1X, X2, BTTS/GG, over 2.5 and under 2.5.

`make external-predictions` and its `DATE=` / `SOURCE=` variants are operational and currently return `NO_APPROVED_SOURCES`. That is the correct safe result, not a collection failure. `scripts/mvp-refresh.sh` is the scheduler entry point. The systemd service/timer under `infrastructure/systemd` schedules it for 06:00 `Africa/Lagos`; operators install it after configuring the deployment user, path and environment file.

No source consensus or source-performance claim is produced when zero approved selections exist. Once records exist, the daily sync deterministically settles supported 1X2, double-chance, BTTS, and 2.5-goal selections from matched completed fixtures; `/predictions` groups consensus without changing MatchForge probabilities and reports source hit rate from those stored outcomes.
