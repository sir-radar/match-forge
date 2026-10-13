import { DataSyncAdmin } from "@/components/data-sync-admin";
import { displayDay } from "@/lib/display-date";

export const dynamic = "force-dynamic";
export default function Page() { return <DataSyncAdmin initialDate={displayDay()} />; }
