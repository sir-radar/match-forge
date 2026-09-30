# Visual comparison report

Compared 29 September 2026 at 1440×1000 desktop and iPhone 13 viewport using deterministic Playwright data.

Reference sources: every relevant `web/ui-designs` fixture desktop tab, both mobile fixture states, `matchforge_analytics`, `matchforge_logo`, and `web/BRIEF.md`.

Implemented matches the dark continuous analytical workbench: fixed competition rail, dense grouped fixture rows, emerald/cyan probability encoding, inline expansion, compact provenance, horizontally scrolling analysis tabs, score matrix, dark tables, responsive mobile stacking, fixed mobile navigation and the exact supplied SVG logo geometry.

Intentional differences:

- Simulation evidence, diagnostics and forecast-history tabs are not presented as active MVP evidence because the owner did not authorize a new Rust simulation pass or research claims. The stored model/version/cutoff record is shown instead.
- Material-symbol web fonts and remote mock assets were removed; semantic text controls and the supplied inline SVG logo avoid runtime third-party asset dependencies.
- Unavailable real fields render explicit states instead of the reference mock values.
- Performance and external-prediction pages reuse the analytics cards/tables because no dedicated source screen exists.

The corrupted 28-byte desktop-collapsed `screen.png` was not usable; its `code.html`, the expanded desktop screenshots and both mobile screenshots supplied the collapsed-row evidence.
