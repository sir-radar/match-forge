import { api } from "@/lib/api";
import { backupReminder } from "@/lib/backup";
import { BackupReminderBanner } from "@/components/backup-reminder-banner";

// Rendered inside Suspense on the landing page, so a slow drive check never delays fixtures.
// A failed status check shows nothing here; Backup & Recovery reports the error.
export async function BackupReminder({ now = new Date() }: { now?: Date }) {
  const { view } = await api.backup(undefined, process.env.WEB_ORIGIN ?? "http://127.0.0.1:3000");
  const reminder = view && backupReminder(view, now);
  return reminder ? <BackupReminderBanner reminder={reminder} /> : null;
}
