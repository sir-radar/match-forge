"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function AdminNavigation() {
  const pathname = usePathname();
  return <nav aria-label="Admin navigation" className="resolution-nav">
    <Link href="/admin/data-sync" aria-current={pathname === "/admin/data-sync" ? "page" : undefined}>Data Sync</Link>
    <Link href="/admin/resolution" aria-current={pathname === "/admin/resolution" ? "page" : undefined}>Resolution Center</Link>
  </nav>;
}
