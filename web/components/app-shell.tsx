import Link from "next/link";
import type { ReactNode } from "react";
import { Logo } from "@/components/logo";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="topbar">
        <Link href="/" className="brand-link"><Logo /></Link>
        <nav aria-label="Primary navigation">
          <Link href="/">Matches</Link>
          <Link href="/performance">Performance</Link>
          <Link href="/predictions">External predictions</Link>
          <Link href="/admin/data-sync">Admin</Link>
        </nav>
        <div className="shell-tools">
          <label className="global-search" title="Global search is not exposed by the MVP API"><span className="material-symbol" aria-hidden="true">search</span><span className="sr-only">Global search unavailable</span><input type="search" placeholder="Search unavailable" disabled /><kbd>Soon</kbd></label>
          <span className="timezone">UTC+0 <i>/ Local</i></span>
          <div className="feed-state"><span aria-hidden="true" /> Feed: Live</div>
          <span className="profile-mark material-symbol" aria-hidden="true">person</span>
        </div>
      </header>
      <main id="main">{children}</main>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        <Link href="/"><span className="material-symbol" aria-hidden="true">analytics</span>Fixtures</Link>
        <Link href="/performance"><span className="material-symbol" aria-hidden="true">monitoring</span>Performance</Link>
        <Link href="/predictions"><span className="material-symbol" aria-hidden="true">table_view</span>Predictions</Link>
        <Link href="/admin/data-sync"><span className="material-symbol" aria-hidden="true">science</span>Admin</Link>
      </nav>
      <footer className="footer-note">
        MatchForge forecasts are independent probability estimates. No bookmaker odds, betting slips, or guarantees.
      </footer>
    </div>
  );
}
