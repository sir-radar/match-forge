import { Suspense } from "react";
import { StorageAdmin } from "@/components/storage-admin";
import { StorageBackupSummary } from "@/components/storage-backup-summary";
import { storageStatus, type StorageView } from "@/lib/storage";

export const dynamic = "force-dynamic";
export const metadata = { title: "Storage Management · MatchForge" };
export default async function Page() {
  let initial: StorageView | null = null;
  let error: string | null = null;
  try { initial = await storageStatus(undefined, process.env.WEB_ORIGIN ?? "http://127.0.0.1:3000"); }
  catch { error = "Storage status unavailable. Check the local API and Admin access, then retry."; }
  return <StorageAdmin initial={initial} initialError={error}><Suspense fallback={<p role="status">Checking backup storage…</p>}><StorageBackupSummary /></Suspense></StorageAdmin>;
}
