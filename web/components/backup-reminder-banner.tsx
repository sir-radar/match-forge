"use client";

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import type { BackupReminder } from "@/lib/backup";
import { DISPLAY_TIME_ZONE } from "@/lib/display-date";

const STORAGE_KEY = "matchforge.backup-reminder.dismissed";
const dueLabel = (value: string) => new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: DISPLAY_TIME_ZONE }).format(new Date(value));

function readDismissed(): string | null {
  try { return window.localStorage.getItem(STORAGE_KEY); } catch { return null; }
}
function subscribe(changed: () => void) {
  window.addEventListener("storage", changed);
  return () => window.removeEventListener("storage", changed);
}

function message({ dueAt, overdue, driveConnected }: BackupReminder): string {
  const when = dueAt === null ? "No verified backup exists yet." : overdue ? `Backup overdue since ${dueLabel(dueAt)}.` : `Backup due ${dueLabel(dueAt)}.`;
  return driveConnected ? `${when} The backup drive is connected; start the backup when ready.` : `${when} Connect the backup drive.`;
}

export function BackupReminderBanner({ reminder }: { reminder: BackupReminder }) {
  // The server snapshot counts as dismissed, so a closed reminder never flashes on load.
  const dismissed = useSyncExternalStore(subscribe, readDismissed, () => reminder.dismissKey);
  const [closed, setClosed] = useState(false);
  if (closed || dismissed === reminder.dismissKey) return null;
  const close = () => {
    try { window.localStorage.setItem(STORAGE_KEY, reminder.dismissKey); } catch { /* closes for this page view only */ }
    setClosed(true);
  };
  return <div role="alert" className="m-4 mb-0 flex flex-wrap items-center gap-3 border-l-4 border-[var(--warning)] bg-[var(--container)] px-4 py-3 text-sm">
    <p className="min-w-0 flex-1"><b className="mr-2 text-[var(--warning)]">Backup reminder</b>{message(reminder)}</p>
    <Link href="/admin/backup" className="min-h-11 content-center underline">Backup &amp; Recovery</Link>
    <button type="button" onClick={close} className="min-h-11 min-w-11 cursor-pointer border border-[var(--outline)] px-3">Dismiss</button>
  </div>;
}
