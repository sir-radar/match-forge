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
path. `scripts/mvp-refresh.sh` invokes automated collection after the product sync. The repository's
systemd timer schedules the script daily at 06:00 `Africa/Lagos`; installation and alert delivery
on the operating host require separate verification.

## Current records, timing and correction policy

External selections remain immutable. Current reads select the latest captured
selection per source, resolved MatchForge fixture and market, ordered by its
latest retained capture observation. Unresolved records
stay separate; display names do not combine them. Conflicting picks captured at
the same latest time are excluded from source metrics and consensus. Original
capture timestamps are never advanced or backdated by an identical reimport.
Append-only capture observations establish the currently observed revision,
including a return to a previously seen pick. A revision first observed after
kickoff cannot inherit prospective credit from an earlier occurrence of that pick;
unchanged confirmations preserve its original prospective eligibility.

Prospective source hit rate counts only current selections first captured strictly
before kickoff, with verified fixture identity, an admissible source date and a
current WON/LOST settlement. Late capture is reported separately. Missing or
unverifiable dates cannot establish prospective evidence. These are descriptive
source statistics, not governed MatchForge research evaluation. Pending result
corrections immediately exclude obsolete settlements from both row displays and
source totals; immutable first-result records are retained only as history.

R2Bet and 1960Tips use full calendar-date validation. A source page with the wrong
day produces DATE_MISMATCH and no imported rows. The bounded recovery worker also
reviews retained date text: mismatches and unknown dates remain explicit and
cannot contribute settlement credit or comparisons. Source attempt history is
separate from the registry's qualification `checked_at` timestamp. Disabled and
out-of-window sources do not count as attempted failures; partial/all-source
failures produce a non-successful job summary while preserving successful imports.

A previously unmatched selection can acquire an append-only binding when its
original provider code and native fixture ID acquire an independently verified
MatchForge mapping. Mapping confidence, method, football validity and current
knowledge checks remain required. A missing native mapping never falls back to
team names. Selections without native identity evidence remain unresolved until
an authorized evidence route supplies it; this workflow does not authorize a new
identity mapping or provider request.

Imports, canonical result changes, result observations and mapping changes enqueue
settlement work transactionally. The normal PUBLIC_REPORTS worker processes a
bounded batch before comparisons; provider sync retains a bounded compatibility
entry point. Each selection checkpoints in a short SQL transaction, coordinates
comparison detail before settlement detail with SKIP LOCKED, and retains worker
publication fences. Rollback leaves pending generations. An explicit correction
sequence and predecessor preserve transitions back to an earlier result without
reusing or rewriting the old revision. The default batch is 128 for compatibility
calls and at most 32 for each scheduled public-report iteration.

The archive uses 20/50/100-row pages, with a maximum of 100 records. Source summaries
use one filtered aggregate query rather than loading every source archive.
Consensus is computed across the complete filtered current selection set, independent
of the visible page. It requires at least two distinct enabled public sources,
verified fixtures, matching supported markets/selections, pre-kickoff capture,
admissible dates and current comparison reports. A strict majority is required;
ties and single-source revisions do not create consensus. No external selection
changes MatchForge model inputs, fitted artifacts or published probabilities.

### Reviewed bindings for captures without native IDs

Automated recovery never invents a provider fixture ID from team names. When a
source capture has no native ID, an operator may explicitly review that immutable
capture against an existing verified native mapping with retained source evidence:

```sh
uv run python -m football.product.cli --database-url "$DATABASE_URL" \
  external-binding-review --prediction-id <capture-uuid> \
  --mapping-id <verified-mapping-uuid> --reason '<retained evidence and review rationale>'
```

The command requires a verified fixture and native mapping, confidence one,
compatible validity dates and a retained source snapshot. The binding records the
original source revision hash, mapping, snapshot and review reason. A retry leaves
one binding; a mapping revocation queues recovery and appends an unmatched state.
The original prediction, source text and capture times never change. Review after
kickoff receives no prospective accuracy or consensus credit, even if the original
capture was earlier. The source table labels these selections retrospective.
A held, ambiguous or missing native mapping remains unresolved until independent
evidence is available; this command does not approve identity mappings.


Comparisons, prospective aggregates and consensus wait for the current external
validation generation to complete. A newly queued correction hides the old
comparison immediately; settlement and comparison output cannot disagree about
which validation checkpoint is current. Standalone report generation does not
bypass this checkpoint. The normal public-report worker processes validation
before report work.
