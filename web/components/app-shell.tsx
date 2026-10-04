"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Logo } from "@/components/logo";
import { Icon } from "@/components/icon";
import { BackToTop } from "@/components/back-to-top";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const current = (href: string) => pathname === href ? "page" as const : undefined;

  if (pathname === "/predictions") {
    return (
      <div className="min-h-screen bg-[#0f131c]">
        <a className="skip-link" href="#main">Skip to content</a>
        {children}
      </div>
    );
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="topbar">
        <Link href="/" className="brand-link"><Logo /></Link>
        <nav aria-label="Primary navigation">
          <Link href="/" aria-current={current("/")}>Matches</Link>
          <Link href="/performance" aria-current={current("/performance")}>Performance</Link>
          <Link href="/predictions" aria-current={current("/predictions")}>External predictions</Link>
          <Link href="/admin/data-sync" aria-current={current("/admin/data-sync")}>Admin</Link>
        </nav>
        <div className="shell-tools">
          <label className="global-search" title="Global search is not exposed by the MVP API"><Icon name="search" /><span className="sr-only">Global search unavailable</span><input type="search" placeholder="Search unavailable" disabled /><kbd>Soon</kbd></label>
          <span className="timezone">UTC+0 <i>/ Local</i></span>
          <div className="feed-state"><span aria-hidden="true" /> Feed: Live</div>
          <Icon name="person" className="profile-mark" />
        </div>
      </header>
      <main id="main" tabIndex={-1}>{children}</main>
      {pathname === "/" && <BackToTop />}
      <nav className="mobile-nav" aria-label="Mobile navigation">
        <Link href="/" aria-current={current("/")}><Icon name="analytics" />Fixtures</Link>
        <Link href="/performance" aria-current={current("/performance")}><Icon name="monitoring" />Performance</Link>
        <Link href="/predictions" aria-current={current("/predictions")}><Icon name="table" />Predictions</Link>
        <Link href="/admin/data-sync" aria-current={current("/admin/data-sync")}><Icon name="science" />Admin</Link>
      </nav>
      <footer className="footer-note">
        MatchForge forecasts are independent probability estimates. No bookmaker odds, betting slips, or guarantees.
      </footer>
    </div>
  );
}
