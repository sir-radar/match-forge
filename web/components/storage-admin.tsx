"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { AdminNavigation } from "@/components/admin-navigation";
import { TableScroll } from "@/components/table-scroll";
import {
  formatStorageBytes, formatStorageTime, startStorageReview, storageStatus,
  type StorageResource, type StorageReview, type StorageView,
} from "@/lib/storage";

const button = "min-h-11 rounded-sm border border-[var(--outline)] px-4 py-2 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--secondary)] disabled:opacity-50";
const panel = "rounded-sm border border-[var(--outline)] p-4";
const summary = "cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-4";

export function StorageAdmin({ initial, initialError = null, children }: {
  initial: StorageView | null; initialError?: string | null; children?: ReactNode;
}) {
  const [view, setView] = useState(initial);
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  async function load(submit = false) {
    if (controller.current) return;
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError(null);
    try {
      if (submit) {
        await startStorageReview(request.signal);
        if (request.signal.aborted) return;
        setNotice("Dry-run review submitted. Refresh status after the job completes.");
      }
      const next = await storageStatus(request.signal);
      if (!request.signal.aborted) setView(next);
    } catch (cause) {
      if (!request.signal.aborted) {
        setError(cause instanceof Error ? cause.message : "Storage status unavailable. Retry when connected.");
      }
    } finally {
      controller.current = null;
      if (!request.signal.aborted) setBusy(false);
    }
  }

  return <main className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-8">
    <AdminNavigation />
    <header className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-widest">Operations</p>
      <h1 className="text-3xl font-semibold">Storage Management</h1>
      <p>Reviews are dry runs. Resource actions run only for eligible resources after exact owner approval; protected resources cannot be deleted here.</p>
    </header>
    <div className="flex flex-wrap gap-3">
      <button type="button" className={button} disabled={busy} onClick={() => void load()}>Refresh storage status</button>
      <button type="button" className={button} disabled={busy || !view || view.state === "MIGRATION_PENDING"} onClick={() => void load(true)}>Run dry-run review</button>
      <Link className={button} href="/admin/backup">Backup &amp; Recovery</Link>
    </div>
    <div role="status" aria-live="polite">{busy ? "Checking storage…" : notice}</div>
    {error && <p role="alert">{error} {view?.latest && "Existing measurements remain visible."}</p>}
    {view && <StorageResults view={view} />}
    {children}
    <Link className="inline-block min-h-11 py-2 underline" href="/admin/data-sync">Inspect lifecycle jobs in Data Sync</Link>
  </main>;
}

function StorageResults({ view }: { view: StorageView }) {
  return <>
    <p>{view.message}</p>
    {view.latest && <>
      <ReviewDetails review={view.latest} />
      <details className={panel}>
        <summary className={summary}>Review identity and cleanup approvals</summary>
        <p className="mt-3 break-all">Manifest SHA-256: {view.manifest_sha256}</p>
        <p className="break-all">Work item: {view.work_id}</p>
        <p>Owner review receipts: {view.approvals.length}. Cleanup requires separate approval for exact resources.</p>
      </details>
    </>}
    <CapacityHistory history={view.history} />
  </>;
}

function ReviewDetails({ review }: { review: StorageReview }) {
  const actions = new Map(review.actions.map((action) => [action.resource_id, action]));
  return <>
    <p>Measured {formatStorageTime(review.observed_at)}. File allocation can include shared APFS extents. PostgreSQL bytes overlap Docker volume usage.</p>
    <dl className="grid gap-4 rounded-sm border border-[var(--outline)] p-5 sm:grid-cols-3">
      <div><dt>Available disk capacity</dt><dd className="text-2xl font-semibold">{formatStorageBytes(review.capacity.free_bytes)}</dd></div>
      <div><dt>Disk capacity</dt><dd className="text-2xl font-semibold">{formatStorageBytes(review.capacity.total_bytes)}</dd></div>
      <div><dt>Physical space reclaimed</dt><dd className="text-2xl font-semibold">0 bytes</dd></div>
    </dl>
    <section aria-labelledby="storage-alerts">
      <h2 id="storage-alerts" className="text-xl font-semibold">Storage alerts</h2>
      {review.alerts.length
        ? <ul className="list-disc space-y-2 pl-5">{review.alerts.map((alert, i) => <li key={i}>{alert}</li>)}</ul>
        : <p>No capacity alerts in this review.</p>}
    </section>
    <StorageDistribution resources={review.resources} />
    <section className="space-y-3" aria-labelledby="storage-resources">
      <h2 id="storage-resources" className="text-xl font-semibold">Resources and protection</h2>
      <p>{review.actions.filter((action) => action.action === "QUARANTINE_REVIEW_REQUIRED").length} resources proposed for quarantine review.</p>
      {review.resources.map((resource) => <ResourceDetails key={resource.resource_id}
        resource={resource} action={actions.get(resource.resource_id)} />)}
    </section>
  </>;
}

function StorageDistribution({ resources }: { resources: StorageResource[] }) {
  const usage = new Map<string, { bytes: number; incomplete: boolean }>();
  for (const resource of resources) {
    if (resource.kind !== "directory" && resource.backend !== "postgres") continue;
    const basis = resource.backend === "postgres" ? "database bytes" : "allocated file bytes";
    const label = `${resource.subsystem} (${basis})`;
    const prior = usage.get(label) ?? { bytes: 0, incomplete: false };
    usage.set(label, {
      bytes: prior.bytes + (resource.backend === "postgres" ? resource.logical_bytes : resource.allocated_bytes ?? 0),
      incomplete: prior.incomplete || !resource.complete,
    });
  }
  return <details className={panel}>
    <summary className={summary}>Storage distribution by subsystem</summary>
    <dl className="mt-3 grid gap-3 sm:grid-cols-2">
      {Array.from(usage, ([label, entry]) => <div key={label}>
        <dt>{label}</dt>
        <dd>{entry.incomplete && "At least "}{formatStorageBytes(entry.bytes)}</dd>
      </div>)}
    </dl>
  </details>;
}

function ResourceDetails({ resource, action }: { resource: StorageResource; action?: StorageReview["actions"][number] }) {
  return <details className={panel}>
    <summary className={`${summary} [overflow-wrap:anywhere]`}>
      {resource.location} — {resource.protected ? "Protected" : resource.state}{!resource.complete && " (incomplete measurement)"}
    </summary>
    <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
      <div><dt>Subsystem</dt><dd>{resource.subsystem}</dd></div>
      <div><dt>Owner</dt><dd>{resource.owner || "Unknown"}</dd></div>
      <div><dt>Logical size</dt><dd>{formatStorageBytes(resource.backend === "git" ? null : resource.logical_bytes)}</dd></div>
      <div><dt>Allocated size</dt><dd>{formatStorageBytes(resource.allocated_bytes)}</dd></div>
      {resource.archive && <ArchiveSizes resource={resource} archive={resource.archive} />}
    </dl>
    <ul className="mt-3 list-disc space-y-1 pl-5">{resource.blockers.map((blocker, i) => <li key={i}>{blocker}</li>)}</ul>
    {action && <div className="mt-3 space-y-1">
      <p>{action.action === "PRESERVE" ? "Preserve" : "Quarantine review required"}. Expected physical savings: {formatStorageBytes(action.expected_physical_savings)}.</p>
      <p>Rollback: {action.rollback}</p>
    </div>}
  </details>;
}

function ArchiveSizes({ resource, archive }: { resource: StorageResource; archive: NonNullable<StorageResource["archive"]> }) {
  return <>
    <div><dt>Deduplicated logical bytes</dt><dd>{formatStorageBytes(resource.logical_bytes - archive.unique_bytes)}</dd></div>
    <div><dt>Compression reduction</dt><dd>{formatStorageBytes(archive.unique_bytes - archive.packed_bytes)}</dd></div>
    <div><dt>Verified packed size</dt><dd>{formatStorageBytes(archive.packed_bytes)}</dd></div>
    <div><dt>Archive verified</dt><dd>{formatStorageTime(archive.verified_at)}</dd></div>
  </>;
}

function CapacityHistory({ history }: { history: StorageReview[] }) {
  return <section aria-labelledby="storage-history">
    <h2 id="storage-history" className="text-xl font-semibold">Capacity history</h2>
    {history.length ? <TableScroll label="Storage capacity history"><table>
      <caption className="sr-only">Daily storage review history</caption>
      <thead><tr><th scope="col">Measured</th><th scope="col">Free capacity</th><th scope="col">Resources</th><th scope="col">Alerts</th></tr></thead>
      <tbody>{history.map((entry, i) => <tr key={`${entry.observed_at}-${i}`}>
        <th scope="row">{formatStorageTime(entry.observed_at)}</th><td>{formatStorageBytes(entry.capacity.free_bytes)}</td>
        <td>{entry.resources.length}</td><td>{entry.alerts.length}</td>
      </tr>)}</tbody>
    </table></TableScroll> : <p>No completed reviews yet.</p>}
  </section>;
}
