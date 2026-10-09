# MVP external prediction sources

Checked 30 September 2026 under `EXTERNAL_PREDICTION_USAGE_MODE=PRIVATE_LOCAL`.
This qualification covers private local comparison only. It does not authorize public
redistribution. Collection stores structured prediction facts, not copied pages or articles.

Qualification used one ordinary `GET` per source. No login, payment, CAPTCHA, managed
challenge, stealth technique, or anti-bot bypass was used.

| Source | Public page reachable | Login required | Paid content required | Ordinary request works | Anti-bot block | Predictions parsed | Date parsed | Fixtures parsed | Markets parsed | Final status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R2Bet | Yes | No | No for collected public picks; separate VIP content exists | Yes, HTTP 200 | No | Yes, 18 selections | Yes, `30th , Wed Sep 2026` | Yes, 18 | Yes, 18 supported selections | `ENABLED` |
| 1960Tips | Yes | No | No for collected free tips; separate VIP content exists | Yes, HTTP 200 | No | Yes, 4 selections | Yes, `Wed, 30 Sep 2026` | Yes, 4 | Yes, 4 | `ENABLED` |
| SlyBet | Yes | No | No | Yes, HTTP 200 | No | Yes, 4 selections | Yes, `30.09.26` | Yes, 4 | Yes, 4 | `ENABLED` |
| MatchOutlook | Yes | No | No for collected public picks; separate paid presentation exists | Yes, HTTP 200 | No | Yes, 3 supported selections | Yes, relative daily page resolved to `2026-09-30` | Yes, 3 | Yes, 3 supported selections | `ENABLED` |
| Forebet | Public presentation exists, but collector request is blocked | No login prompt reached | No public payment gate reached | No, HTTP 403 | Yes, managed anti-bot response | No | No | No | No | `TECHNICALLY_UNAVAILABLE` |

Terms notes:

- R2Bet and SlyBet: no explicit automation permission found. This does not block private local collection.
- 1960Tips and MatchOutlook: restrictive reuse terms remain recorded. Collection is limited to the structured facts needed for private local comparison and is not redistributed.
- Forebet: the adapter remains disabled because ordinary direct retrieval receives HTTP 403. MatchForge does not attempt circumvention.

The enabled adapters preserve source URL, displayed or resolved prediction date, original date
text, capture time, competition text, team text, normalized market and selection, immutable
revision identity, and fixture-match result. Supported mappings include 1/X/2, 1X, X2,
BTTS/GG, over 1.5, over 2.5, under 2.5, and under 3.5. Unsupported provider markets are
stored verbatim rather than dropped or silently reinterpreted. Parsers retain a known provider
market family where the page supplies one; otherwise they use market `UNMAPPED`. These rows
remain visible but report `UNABLE_TO_EVALUATE` until MatchForge has a probability contract for
the selection.

`make external-predictions` runs all enabled sources independently. `DATE=YYYY-MM-DD` limits
parsing to that prediction date, and `SOURCE=<source>` runs one source. R2Bet supports a dated
URL. SlyBet checks both its landing page and `/football-predictions/` and considers only a table
whose displayed date matches the requested date. It uses one mirrored copy: the landing page when
available, otherwise `/football-predictions/`. It never combines the two copies.
The other enabled sites expose today/yesterday/tomorrow or recent dated tables; requests outside
those published windows report `NO_DATE_PAGE` or no matching predictions. One source failure does
not fail successful sources. Each configured page is fetched once per source run and reused by
that source parser.

An optional `MVP_EXTERNAL_PREDICTIONS_IMPORT_FILE` still invokes the append-only manual import
path. `scripts/mvp-refresh.sh` invokes automated collection after the product sync. The systemd
timer runs the script daily at 06:00 `Africa/Lagos`.
