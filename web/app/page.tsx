import { Suspense } from "react";
import { BackupReminder } from "@/components/backup-reminder";
import { FixtureExplorer } from "@/components/fixture-explorer";

import { displayDay } from "@/lib/display-date";

export const dynamic = "force-dynamic";

export default function Home() {
  return <>
    <Suspense fallback={null}><BackupReminder /></Suspense>
    <FixtureExplorer initialDate={displayDay()} />
  </>;
}
