# MatchForge approved-design evidence

Source order: owner request dated 3 October 2026; route-specific `code.html` and
`screen.png`; owner correction dated 1 October 2026; earlier `code.html`; `screen.png`;
`web/BRIEF.md`; existing MVP.

All 12 supplied HTML prototypes were inspected: desktop collapsed fixtures,
expanded overview, markets, score matrix, H2H, team statistics, simulation
evidence, diagnostics, forecast history, both mobile states, and logo. All 10
valid PNG references were inspected at original dimensions. Analytics uses
`matchforge_analytics/DESIGN.md`; that directory has no `code.html`.

The collapsed-desktop `screen.png` is not an image; its complete contents are
`<FIFE Image failed to fetch>`. Its `code.html` remains authoritative.

Prototype football values are examples. Production renders only API values.
No public API currently exposes simulation-validation evidence, forecast
revision history, or research diagnostics, so those tabs render an explicit
unavailable/restricted state instead of fabricated evidence.

The `/predictions` redesign uses
`web/ui-designs/matchforge_desktop_external_predictions_page/code.html` and its
1187×1600 `screen.png` as authoritative desktop evidence. SHA-256 values:
`9f58aee13e0c7dabce78d62f7f95ad65ff6e0584c87e3bf948bda4e82ebb556f`
and `436bbe5ce20360f59d0f80eff45c5709629aee609b4f2af8d557091370821083`.
Responsive mobile behavior is inferred from existing MatchForge conventions.
Mock-only identity, checksums, totals, and provider claims are not production
contracts and were not copied. The table renders the complete selected-day
response without pagination. The reference Proof Log remains visibly disabled because
the current API exposes no proof-log operation.
