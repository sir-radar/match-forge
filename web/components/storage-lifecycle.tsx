"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { TableScroll } from "@/components/table-scroll";
import { formatStorageBytes, formatStorageTime } from "@/lib/storage";
import {
  storageManagement,
  type LifecycleRecord, type LifecycleState, type LifecycleStatus, type MaintenanceReport, type MaintenanceStatus,
} from "@/lib/storage-management";

const panel = "rounded-sm border border-[var(--outline)] p-4";
const button = "min-h-11 rounded-sm border border-[var(--outline)] px-3 py-2 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--secondary)] disabled:cursor-not-allowed disabled:opacity-50";
const stateTone: Record<LifecycleState, string> = {
  ACTIVE: "border-[var(--primary)] text-[var(--primary)]",
  WAITING: "border-[var(--outline)]",
  ELIGIBLE: "border-[var(--secondary)] text-[var(--secondary)]",
  DELETING: "border-[var(--secondary)] text-[var(--secondary)]",
  BLOCKED: "border-[var(--warning)] text-[var(--warning)]",
  DELETED: "border-[var(--outline)]",
  ABSENT: "border-[var(--outline)]",
};
const stateLabel: Record<LifecycleState, string> = {
  ACTIVE: "Active", WAITING: "Waiting", ELIGIBLE: "Eligible", BLOCKED: "Blocked", DELETING: "Deleting", DELETED: "Deleted", ABSENT: "Gone",
};
const severityTone = { INFO: "", WARNING: "text-[var(--warning)]", CRITICAL: "text-[var(--error)]" };

/** Remaining time until a deadline, in hours and minutes; "due" once it passed. */
export function countdown(deadline: string | null, now: number): string {
  if (!deadline) return "Not complete";
  const ms = Date.parse(deadline) - now;
  if (ms <= 0) return "Due";
  const minutes = Math.ceil(ms / 60_000);
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

function useLoader<T>(load: () => Promise<T>) {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  const refresh = useCallback(async () => {
    try {
      const next = await load();
      if (mounted.current) { setValue(next); setError(null); }
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : "Unavailable.");
    }
  }, [load]);
  useEffect(() => {
    mounted.current = true;
    let cancelled = false;
    void Promise.resolve().then(() => { if (!cancelled) void refresh(); });
    return () => { cancelled = true; mounted.current = false; };
  }, [refresh]);
  return { value, error, refresh };
}

function owner(record: LifecycleRecord): string {
  if (record.resource_class === "WORKTREE") return `Branch ${String(record.owner_ref.branch ?? "unknown")}`;
  const pid = record.owner_ref.pid, host = record.owner_ref.host;
  return `${record.owner_kind === "HARNESS_CHILD" ? "Child of test run" : "Test run"} ${String(pid ?? "?")} on ${String(host ?? "?")}`;
}

export function LifecyclePanel() {
  const { value, error, refresh } = useLoader<LifecycleStatus>(storageManagement.lifecycle);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);
  if (error) return <p role="alert" className="text-[var(--error)]">{error} <button type="button" className={button} onClick={() => void refresh()}>Retry</button></p>;
  if (!value) return <p>Loading five-hour cleanup…</p>;
  if (!value.deployed) return <p className={panel}>The lifecycle migration has not been deployed. Nothing is tracked or deleted automatically.</p>;
  const p = value.policy;
  return <div className="grid gap-4">
    <div className={panel}>
      <h3 className="text-lg font-semibold">Five-hour cleanup policy</h3>
      {p ? <p className="mt-1 text-sm">
        Deletes completed {p.test_databases ? "test databases" : ""}{p.test_databases && p.worktrees ? " and " : ""}{p.worktrees ? `worktrees merged into ${p.worktrees.target_ref}` : ""} after{" "}
        {Math.round(p.inactivity_seconds / 3600)} hours without activity. Checks every {Math.round(p.check_interval_seconds / 60)} minutes,
        at most {p.max_per_run} per run. Approved by {p.approved_by} ({p.approval_record}).
      </p> : <p className="mt-1 text-sm">Not enabled by the storage policy. Resources are tracked only after it is enabled.</p>}
      <p className="mt-1 text-sm">Measured reclaimed by this policy: {formatStorageBytes(value.reclaimed_bytes)}.</p>
    </div>
    <TableScroll label="Tracked resources">
      <table className="w-full min-w-[56rem] text-left text-sm">
        <caption className="sr-only">Resources tracked by the five-hour cleanup policy</caption>
        <thead><tr><th scope="col">Resource</th><th scope="col">State</th><th scope="col">Owner</th><th scope="col">Last activity</th>
          <th scope="col">Eligible in</th><th scope="col">Blockers</th><th scope="col">Reclaimed</th></tr></thead>
        <tbody>
          {value.resources.length === 0 && <tr><td colSpan={7}>No tracked resources.</td></tr>}
          {value.resources.map((r) => <tr key={r.identity_key} className="border-t border-[var(--outline)] align-top">
            <td><span className="font-semibold">{r.resource_class === "WORKTREE" ? "Worktree" : "Test database"}</span><br /><span className="break-all">{r.location}</span></td>
            <td><span className={`inline-block rounded-sm border px-2 text-xs font-semibold ${stateTone[r.state]}`}>{stateLabel[r.state]}</span></td>
            <td>{owner(r)}</td>
            <td>{formatStorageTime(r.last_activity_at)}</td>
            <td>{r.state === "WAITING" ? countdown(r.eligible_at, now) : r.state === "ELIGIBLE" ? "Due" : "—"}</td>
            <td>{r.blockers.length ? <ul className="list-disc pl-4">{r.blockers.map((b) => <li key={b}>{b}</li>)}</ul> : "None"}</td>
            <td>{r.reclaimed_bytes == null ? "—" : formatStorageBytes(r.reclaimed_bytes)}</td>
          </tr>)}
        </tbody>
      </table>
    </TableScroll>
    {value.unregistered_test_databases.length > 0 && <div className={panel} role="note">
      <h3 className="font-semibold">Test databases without a creation record</h3>
      <p className="text-sm">These are never deleted automatically. Review them in Databases and record a disposition.</p>
      <ul className="mt-2 list-disc pl-5 text-sm">{value.unregistered_test_databases.map((u) => <li key={u.oid}>{u.name} ({formatStorageBytes(u.bytes)})</li>)}</ul>
    </div>}
    <details className={panel}>
      <summary className="cursor-pointer font-semibold">Audit trail ({value.events.length} latest events)</summary>
      <ul className="mt-2 grid gap-1 text-sm">{value.events.map((e, i) => <li key={`${e.identity_key}-${e.recorded_at}-${i}`}>
        {formatStorageTime(e.recorded_at)} · <span className="font-semibold">{e.event}</span> · <span className="break-all">{e.identity_key}</span>
      </li>)}</ul>
    </details>
  </div>;
}

function ReportCard({ report }: { report: MaintenanceReport }) {
  return <li className={panel}>
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <h4 className="font-semibold">{report.cadence[0] + report.cadence.slice(1).toLowerCase()} report {report.slot}</h4>
      <span className={report.alerts ? "text-[var(--warning)]" : ""}>{report.state === "RUNNING" ? "Running" : `${report.alerts} alert${report.alerts === 1 ? "" : "s"}`}</span>
    </div>
    {report.error && <p role="alert" className="text-[var(--error)]">Check failed: {report.error}</p>}
    <ul className="mt-2 grid gap-1 text-sm">{report.findings.map((f, i) => <li key={`${f.task}-${i}`} className={severityTone[f.severity]}>
      <span className="font-semibold">{f.severity === "INFO" ? "" : `${f.severity}: `}{f.task.replace(/_/g, " ")}</span> — {f.message}
      {f.bytes != null && ` (${formatStorageBytes(f.bytes)})`}{f.count != null && ` · ${f.count}`}
      {f.items && f.items.length > 0 && <details><summary className="cursor-pointer">Details</summary><ul className="list-disc pl-5">{f.items.map((item) => <li key={item} className="break-all">{item}</li>)}</ul></details>}
    </li>)}</ul>
    <p className="mt-1 text-xs">Started {formatStorageTime(report.started_at)}{report.finished_at ? `, finished ${formatStorageTime(report.finished_at)}` : ""}</p>
  </li>;
}

export function MaintenancePanel() {
  const { value, error, refresh } = useLoader<MaintenanceStatus>(storageManagement.maintenance);
  if (error) return <p role="alert" className="text-[var(--error)]">{error} <button type="button" className={button} onClick={() => void refresh()}>Retry</button></p>;
  if (!value) return <p>Loading maintenance reports…</p>;
  return <div className="grid gap-4">
    <div className={panel}>
      <h3 className="text-lg font-semibold">Scheduled maintenance</h3>
      {value.policy ? <p className="mt-1 text-sm">Daily: capacity, growth (warning above {formatStorageBytes(value.policy.growth_warning_bytes_per_day)} a day), abandoned
        resources (more than {value.policy.max_non_operating_databases} non-operating databases) and backup health. Weekly: artifacts unchanged for{" "}
        {value.policy.stale_after_days} days and measured savings. Monthly: recovery integrity and redundant databases. Reports never delete anything.</p>
        : <p className="mt-1 text-sm">Not enabled by the storage policy.</p>}
    </div>
    {value.reports.length === 0 ? <p>No maintenance reports yet.</p>
      : <ul className="grid gap-3">{value.reports.map((r) => <ReportCard key={r.run_id} report={r} />)}</ul>}
  </div>;
}
