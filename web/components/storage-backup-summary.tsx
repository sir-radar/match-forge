import Link from "next/link";
import { api } from "@/lib/api";
import { backupScopeLabel, type BackupAvailability } from "@/lib/backup";
import { formatStorageBytes, formatStorageTime } from "@/lib/storage";

// Independent server data keeps a missing backup drive from hiding storage reviews.
export async function StorageBackupSummary() {
  const { view, error } = await api.backup(undefined, process.env.WEB_ORIGIN ?? "http://127.0.0.1:3000");
  return <section aria-labelledby="storage-backups" className="space-y-3 rounded-sm border border-[var(--outline)] p-5">
    <h2 id="storage-backups" className="text-xl font-semibold">Backup storage and recovery</h2>
    {error && <p role="alert">{error}</p>}
    {view && <BackupMeasurements availability={view.availability} />}
    <Link className="inline-block min-h-11 py-2 underline focus-visible:outline-2 focus-visible:outline-offset-4" href="/admin/backup">Inspect backup status and recovery history</Link>
  </section>;
}

function BackupMeasurements({ availability }: { availability: BackupAvailability }) {
  const prior = availability.prior_verified;
  return <>
    <p>{availability.message}</p>
    <dl className="grid gap-4 sm:grid-cols-3">
      <div><dt>Repository size at last verification</dt><dd>{formatStorageBytes(prior?.repository_file_bytes)}</dd></div>
      <div><dt>Packed growth at last verification</dt><dd>{formatStorageBytes(prior?.data_added_packed_bytes)}</dd></div>
      <div><dt>Connected backup drive free space</dt><dd>{formatStorageBytes(availability.drive?.free_bytes)}</dd></div>
    </dl>
    <p>Verified scope: {backupScopeLabel(prior?.scope)}. Unavailable dependencies: {prior?.unavailable_dependencies ?? availability.known_unavailable_dependencies ?? "Not measured"}.</p>
    {prior && <p>Last verified {formatStorageTime(prior.verified_at)}. Snapshot <code className="break-all">{prior.snapshot_id}</code>.</p>}
  </>;
}
