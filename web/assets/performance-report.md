# Frontend performance report

Production baseline and final builds pass with Next.js 16.3.7. No UI framework,
chart library, animation library, or runtime state package was added. Requests
abort on filter changes; forecast/context load only after expansion. Inline SVG
logo reserves dimensions. Remote font CSS is the only new third-party request
and preserves the exact approved font families.

The final compressed production assets measure 310,051 bytes across all emitted
JavaScript and CSS, including framework/runtime chunks. App-route JavaScript is
22,805 bytes and CSS is 10,893 bytes compressed. No task dependency was added.

Lighthouse was not run: no Lighthouse CI is configured and production data needs
local service state. Deterministic Playwright covers the changed journeys.

3 October 2026 redesign check: production build passes. All emitted static
JavaScript and CSS total 318,844 gzip bytes across every route and shared
runtime; this is not a route-only transfer measurement. No dependency, image,
chart, animation, or state library was added. The changed route remains within
the existing Next.js client bundle, and its only raster asset is design evidence
excluded from the build.
