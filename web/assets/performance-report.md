# Frontend performance report

Scope: production Next.js build on 30 September 2026.

- Build: passed with Next.js 16.3.7; `/performance` and `/predictions` prerender, `/` is dynamic only to choose the current date.
- Data loading: one competition request and one filtered fixture request on the main view. Forecast/context/external requests are deferred until a fixture expands.
- Rendering: competition/filter derivations are memoized; requests are aborted on filter changes; no polling, animation library, chart library or client state dependency is shipped.
- Assets: logo is inline SVG; no remote font, image or icon requests; no generated raster asset is shipped.
- Layout stability: fixed shell dimensions and explicit probability/fixture layouts avoid late asset shifts. Empty/loading states occupy the same workbench.
- Bundle controls: no duplicate React copy or large UI framework was added. Tailwind is compiled at build time.
- Build artifact measurement: `.next/static` is 712 KiB on disk; all JavaScript chunks total 197,798 bytes when individually gzip-compressed and concatenated for measurement. The largest uncompressed shared chunk is 229,145 bytes. These are build-wide assets, not a claim that every route downloads every chunk.
- Runtime limitation: Lighthouse was not used as an acceptance gate because the production data API requires the local database/provider setup. Playwright exercised desktop Chromium and mobile WebKit against deterministic intercepted API responses.
