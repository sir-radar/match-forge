# UI state matrix

| Surface | Loading | Empty | Partial | Error | Success | Mobile |
| --- | --- | --- | --- | --- | --- | --- |
| Fixtures | Skeleton status | No fixtures for date/filter | Fixture remains visible without forecast | Retry block; previous data retained during refresh | Competition groups and probability rows | Compact stacked teams, horizontal filters, fixed bottom navigation |
| Expanded match | Panel loading | Context-specific unavailable message | Forecast can render without H2H/standings/team stats | Independent context, forecast and external-source retries | Overview, markets, matrix, H2H, team statistics, standings, external tabs | Inline expansion, horizontally scrollable tabs/matrix |
| Performance | Loading status | No published forecasts | `UNRATED` below 50 settlements | Retry block | League metrics and baseline comparison | Two-column summary and scrollable data |
| External predictions | Loading status | No approved selections | Source audit remains available | Predictions/source failures isolated | Filters, selections, consensus, source tracking | Scrollable filters and tables |

Network races use an abort signal and generation guard. The latest filter/date request wins; stale responses cannot overwrite it. Malformed responses fail at the TypeScript runtime contract boundary.
