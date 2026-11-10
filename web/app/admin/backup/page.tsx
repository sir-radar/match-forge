import { BackupAdmin } from "@/components/backup-admin";
import { api } from "@/lib/api";
import type { BackupView } from "@/lib/backup";

export const dynamic = "force-dynamic";
export const metadata = { title: "Backup & Recovery · MatchForge" };

export default async function Page() {
  let initial: BackupView | null = null;
  let error: string | null = null;
  try { initial = await api.backup(AbortSignal.timeout(15_000)); }
  catch { error = "Backup status unavailable. Check local services and retry."; }
  return <BackupAdmin initial={initial} initialError={error} />;
}
