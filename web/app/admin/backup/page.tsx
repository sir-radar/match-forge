import { BackupAdmin } from "@/components/backup-admin";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";
export const metadata = { title: "Backup & Recovery · MatchForge" };

export default async function Page() {
  const { view, error } = await api.backup(undefined, process.env.WEB_ORIGIN ?? "http://127.0.0.1:3000");
  return <BackupAdmin initial={view} initialError={error} />;
}
