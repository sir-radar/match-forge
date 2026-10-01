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
          <Link href="/">Fixtures</Link>
          <Link href="/performance">Performance</Link>
          <Link href="/predictions">External predictions</Link>
          <Link href="/admin/data-sync">Admin</Link>
        </nav>
        <div className="feed-state"><span aria-hidden="true" /> Data synced</div>
      </header>
      <main id="main">{children}</main>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        <Link href="/">Fixtures</Link>
        <Link href="/performance">Performance</Link>
        <Link href="/predictions">Predictions</Link>
        <Link href="/admin/data-sync">Admin</Link>
      </nav>
      <footer className="footer-note">
        MatchForge forecasts are independent probability estimates. No bookmaker odds, betting slips, or guarantees.
      </footer>
    </div>
  );
}
