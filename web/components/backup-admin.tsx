"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AdminNavigation } from "@/components/admin-navigation";
import { TableScroll } from "@/components/table-scroll";
import type { SyncRun } from "@/lib/contracts";
import { DISPLAY_TIME_ZONE } from "@/lib/display-date";
import { api, ApiError } from "@/lib/api";
import { backupScopeLabel, type BackupAvailability, type BackupScope, type BackupView } from "@/lib/backup";

const button = "rounded-sm border border-[var(--outline)] px-4 py-2 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--secondary)] disabled:cursor-not-allowed disabled:opacity-50";
const panel = "rounded-sm border border-[var(--highest)] bg-[var(--lowest)] p-5";
const bytes = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? `${(value / 1_000_000_000).toLocaleString("en-GB", { maximumFractionDigits: 2 })} GB` : "Not measured";
const date = (value: unknown) => typeof value === "string" && Number.isFinite(Date.parse(value)) ? new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: DISPLAY_TIME_ZONE }).format(new Date(value)) : "Not recorded";

type ConfirmedBackup = { id: string; scope: BackupScope; digest: string | null };

function confirmationRequest(availability: BackupAvailability, prior: ConfirmedBackup | null): ConfirmedBackup | null {
  const { scope } = availability;
  if (!scope) return null;
  const digest = scope === "RECOVERABLE_ONLY" ? availability.unavailable_sha256 : null;
  if (prior?.scope === scope && prior.digest === digest) return prior;
  return { id: crypto.randomUUID(), scope, digest };
}

function useBackupState(initial: BackupView | null, initialError: string | null) {
  const [view, setView] = useState(initial), [statusError, setStatusError] = useState(initialError);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false), [confirm, setConfirm] = useState(false), [notice, setNotice] = useState("");
  const generation = useRef(0), controller = useRef<AbortController | null>(null), request = useRef<ConfirmedBackup | null>(null);
  const lastVerified = useRef(initial?.last_verified?.run_id);
  const primary = useRef<HTMLButtonElement>(null), confirmation = useRef<HTMLHeadingElement>(null);
  const progressHeading = useRef<HTMLHeadingElement>(null), notification = useRef<HTMLParagraphElement>(null);
  const focusResult = useRef(false), focusBack = useRef(false);
  const active = view?.runs.find((run) => run.status === "QUEUED" || run.status === "RUNNING");
  const isCurrent = useCallback((token: number, signal: AbortSignal) => token === generation.current && !signal.aborted, []);
  const publish = useCallback((next: BackupView, preview: boolean) => {
    if (next.last_verified && next.last_verified.run_id !== lastVerified.current) {
      setNotice("Backup completed and verified successfully."); lastVerified.current = next.last_verified.run_id;
    }
    setView(next); setConfirm(preview && next.availability.state === "READY");
  }, []);
  const load = useCallback(async (preview = false) => {
    controller.current?.abort(); const signal = new AbortController(); controller.current = signal;
    const current = ++generation.current; setBusy(true);
    try {
      const { view: next, error } = await (preview ? api.previewBackup(signal.signal) : api.backup(signal.signal));
      if (!isCurrent(current, signal.signal)) return;
      setStatusError(error);
      if (next) publish(next, preview);
    } finally { if (isCurrent(current, signal.signal)) setBusy(false); }
  }, [isCurrent, publish]);
  useEffect(() => () => { ++generation.current; controller.current?.abort(); }, []);
  useEffect(() => {
    if (confirm) confirmation.current?.focus();
    if (!confirm && focusBack.current) { primary.current?.focus(); focusBack.current = false; }
  }, [confirm]);
  useEffect(() => {
    if (focusResult.current) { (active ? progressHeading.current : notification.current)?.focus(); focusResult.current = false; }
  }, [active]);
  useEffect(() => {
    if (busy || confirm) return;
    const timer = window.setTimeout(() => void load(), active ? 2500 : 60_000);
    const visible = () => { if (!document.hidden) void load(); };
    document.addEventListener("visibilitychange", visible);
    return () => { window.clearTimeout(timer); document.removeEventListener("visibilitychange", visible); };
  }, [active, busy, confirm, load]);

  const submit = async () => {
    if (busy || !confirm || !view) return;
    const confirmed = confirmationRequest(view.availability, request.current);
    if (!confirmed) return;
    request.current = confirmed;
    setBusy(true); setActionError(null); controller.current?.abort(); ++generation.current;
    const signal = new AbortController(); controller.current = signal;
    try {
      const run = await api.startBackup(confirmed.id, confirmed.scope, confirmed.digest, signal.signal);
      if (signal.signal.aborted) return;
      request.current = null; setConfirm(false);
      focusResult.current = true;
      setView((previous) => previous ? { ...previous, runs: [run, ...previous.runs.filter((item) => item.run_id !== run.run_id)], safe_to_eject: false } : previous);
      setNotice("Backup submitted. Keep the drive connected until verification finishes.");
    } catch (cause) {
      const message = cause instanceof ApiError && cause.status === 409
        ? cause.message
        : "Backup submission could not be confirmed.";
      if (!signal.signal.aborted) setActionError(`${message} Refresh status before retrying. Retrying the same confirmation reuses its request ID.`);
    } finally { if (!signal.signal.aborted) setBusy(false); }
  };
  const cancel = async () => {
    if (!active || busy) return;
    setBusy(true); setActionError(null);
    controller.current?.abort(); ++generation.current;
    const signal = new AbortController(); controller.current = signal;
    try { await api.stopSyncRun(active.run_id, signal.signal); if (!signal.signal.aborted) { focusResult.current = true; setNotice("Cancellation requested. Check run and eject status before disconnecting."); } }
    catch { if (!signal.signal.aborted) setActionError("Backup cancellation could not be confirmed. Check the current run and retry if needed."); }
    finally { if (!signal.signal.aborted) { setBusy(false); void load(); } }
  };

  const dismissConfirmation = () => { focusBack.current = true; setConfirm(false); };
  const refresh = () => { setConfirm(false); setActionError(null); void load(); };
  return { view, statusError, actionError, busy, confirm, notice, primary, confirmation, progressHeading, notification, active, load, submit, cancel, refresh, dismissConfirmation };
}

type BackupState = ReturnType<typeof useBackupState>;

export function BackupAdmin({ initial, initialError = null }: { initial: BackupView | null; initialError?: string | null }) {
  const state = useBackupState(initial, initialError);
  const { view, statusError, actionError, busy, notice, notification } = state;
  return <div className="page sync-admin space-y-6">
    <AdminNavigation />
    <header className="page-heading"><div><small>Local operations</small><h1>Backup &amp; Recovery</h1><p>Encrypted recovery points on your external drive. Every backup starts with your confirmation.</p></div></header>
    {statusError && <div className={panel}><p role="alert">{statusError}</p>{view && <p>Showing the last successful check. Refresh status before starting a backup or ejecting the drive.</p>}</div>}
    {actionError && <p role="alert" className={panel}>{actionError}</p>}
    <p role="status" aria-live="polite" tabIndex={-1} ref={notification}>{notice || (busy ? "Checking backup status…" : "")}</p>
    <BackupReminder view={view} />
    <BackupCoverage view={view} />
    <p>Monthly manual backups may leave about a month of changes without an external recovery point. The previously desired 24-hour protection target is not guaranteed. Make an extra manual backup before significant migrations or maintenance.</p>
    <div className="grid gap-5 md:grid-cols-2">
      {view && <BackupDrivePanel availability={view.availability} />}
      <BackupLatestPanel view={view} />
    </div>
    <BackupControls state={state} />
    <BackupConfirmation state={state} />
    <BackupProgress state={state} />
    <p>{!statusError && view?.safe_to_eject ? "At the last status check, no backup or repository locks were active. Use macOS Eject before disconnecting." : "Keep the drive connected during backup or verification. Safe-to-eject status is not confirmed."}</p>
    <BackupHistory view={view} />
    <details className={panel}><summary>Recovering on another Mac</summary><p>Retain the recovery password separately from this Mac. Install the pinned tools, authenticate the enrolled repository, restore a selected recovery point into new storage, and run the isolated database restore procedure in the operator recovery guide. Keep the operating database untouched until a separately approved recovery.</p><p>Normal MatchForge use does not require the external drive. Connecting it never starts a backup. Reminders follow the configured recovery policy and reset after a verified backup of that scope.</p></details>
  </div>;
}

function BackupReminder({ view }: { view: BackupView | null }) {
  if (!view?.reminder_due) return null;
  const last = view.backup_age_seconds !== null;
  return <aside aria-label="Monthly backup reminder" className={panel}><strong>Monthly backup due</strong><p>{last ? "Your recovery point was verified at least 30 days ago." : "No verified recovery point is recorded for this policy."} Connect your enrolled drive and choose Back Up Now.</p></aside>;
}
function BackupCoverage({ view }: { view: BackupView | null }) {
  if (!view) return null;
  const { scope, known_unavailable_dependencies: unavailable, prior_verified: prior } = view.availability;
  const fullVerified = view.last_full_recovery?.summary?.verified_at ?? (prior?.full_recovery ? prior.verified_at : null);
  return <section className={panel} aria-labelledby="backup-coverage">
    <h2 id="backup-coverage">Recovery policy</h2>
    <p>{scope ? backupScopeLabel(scope) : "Recovery policy could not be checked."}</p>
    {scope && <p>{unavailable === null ? "No reviewed inventory is configured." : `${unavailable.toLocaleString("en-GB")} unavailable dependencies in the reviewed inventory.`}</p>}
    {(scope || fullVerified) && <p>{fullVerified ? `Last full recovery verified ${date(fullVerified)}.` : "Full recovery has yet to pass isolated verification."}</p>}
  </section>;
}
function BackupDrivePanel({ availability }: { availability: BackupAvailability }) {
  return <section className={panel} aria-labelledby="backup-drive"><h2 id="backup-drive">External drive &amp; repository</h2>
        <p>{availability.message}</p>
        {availability.drive && <dl className="space-y-2 break-words"><dt>Volume identity</dt><dd>{availability.drive.volume_uuid}</dd><dt>Capacity / available</dt><dd>{bytes(availability.drive.capacity_bytes)} / {bytes(availability.drive.free_bytes)}</dd><dt>Filesystem</dt><dd>{availability.drive.filesystem} · {availability.drive.filesystem_encrypted ? "Filesystem encrypted" : "Filesystem encryption not verified; Restic encryption required"}</dd></dl>}
        {availability.drive && <p>Authenticated encrypted repository</p>}
      </section>;
}
function selectedBackupSummary(view: BackupView | null) {
  const prior = view?.availability.prior_verified;
  if (view?.last_verified) return { summary: view.last_verified.summary, prior: null };
  if (prior && prior.scope === view?.availability.scope) return { summary: prior, prior };
  return { summary: null, prior: null };
}

function BackupLatestPanel({ view }: { view: BackupView | null }) {
  const { summary, prior } = selectedBackupSummary(view);
  const age = view?.backup_age_seconds;
  const {
    verified_at, captured_at, logical_bytes, data_added_packed_bytes, repository_file_bytes,
    volume_free_space_change_bytes, full_recovery,
  } = summary ?? {};
  const restore = full_recovery ? "Full recovery verified" : "Recoverable data verified";
  return <section className={panel} aria-labelledby="backup-latest">
    <h2 id="backup-latest">Last verified backup for this policy</h2>
    {view ? <dl className="space-y-2">
      <dt>Verified</dt><dd>{date(verified_at)}</dd>
      <dt>Recovery point captured</dt><dd>{date(captured_at)}</dd>
      <dt>Current backup age</dt><dd>{age == null ? "Not recorded for this policy" : `${Math.floor(age / 86400)} days`}</dd>
      <dt>Recommended next backup</dt><dd>{date(view?.next_due_at)}</dd>
      <dt>Last backup / newly stored data</dt><dd>{bytes(logical_bytes)} / {bytes(data_added_packed_bytes)}</dd>
      <dt>Repository files at last verification</dt><dd>{bytes(repository_file_bytes)}</dd>
      <dt>Volume space used during last backup</dt><dd>{bytes(volume_free_space_change_bytes)}</dd>
      <dt>Isolated restore</dt><dd>{summary ? restore : "Not recorded"}</dd>
      {prior && <><dt>Recovery point from operator receipt</dt><dd className="break-all">{prior.snapshot_id}</dd></>}
    </dl> : <p>Retry status to load verified recovery points.</p>}
  </section>;
}
function BackupControls({ state }: { state: BackupState }) {
  const { busy, active, confirm, statusError, primary, load, refresh } = state;
  const availability = state.view?.availability;
  return <div className="flex flex-wrap gap-3"><button tabIndex={0} ref={primary} className={`${button} bg-[var(--secondary)] text-[var(--lowest)]`} disabled={busy || !!statusError || !!active || confirm || availability?.state !== "READY" || !availability.scope} onClick={() => void load(true)}>Back Up Now</button><button tabIndex={0} className={button} disabled={busy} onClick={refresh}>{statusError ? "Retry status" : "Refresh drive status"}</button></div>;
}
function BackupConfirmation({ state }: { state: BackupState }) {
  const { confirm, confirmation, busy, submit, dismissConfirmation } = state;
  const availability = state.view?.availability;
  if (!confirm || !availability?.scope) return null;
  const recoverable = availability.scope === "RECOVERABLE_ONLY";
  return <section className={panel} aria-labelledby="backup-confirm">
    <h2 id="backup-confirm" tabIndex={-1} ref={confirmation}>Confirm manual backup</h2>
    <p><strong>{backupScopeLabel(availability.scope)}</strong></p>
    {recoverable && <p>Confirm that this recovery point excludes the {availability.known_unavailable_dependencies?.toLocaleString("en-GB")} declared unavailable dependencies. Complete historical and model artifact recovery remains unverified.</p>}
    <p>{availability.impact}</p>
    <p>Estimated files {availability.referenced_files.toLocaleString("en-GB")} · {bytes(availability.referenced_bytes)}. Estimated staging {bytes(availability.estimated_staging_bytes)}. Actual size can grow during export.</p>
    <p>Earlier verified recovery points are retained.</p>
    <div className="flex flex-wrap gap-3">
      <button tabIndex={0} className={button} onClick={() => void submit()} disabled={busy}>{recoverable ? "Confirm recoverable-only backup" : "Confirm full recovery backup"}</button>
      <button tabIndex={0} className={button} disabled={busy} onClick={dismissConfirmation}>Go back</button>
    </div>
  </section>;
}
function BackupProgress({ state }: { state: BackupState }) {
  const { active, busy, progressHeading, cancel } = state;
  if (!active) return null;
  return <section className={panel} aria-labelledby="backup-progress"><h2 id="backup-progress" tabIndex={-1} ref={progressHeading}>Backup in progress</h2><p role="status">{active.status} · {typeof active.summary.current_phase === "string" ? active.summary.current_phase : "Preparing recovery point"}</p><progress aria-label="Backup in progress" className="w-full" /><button tabIndex={0} className={button} disabled={busy} onClick={() => void cancel()}>Cancel backup</button></section>;
}
function BackupHistory({ view }: { view: BackupView | null }) {
  if (!view) return null;
  return <section aria-labelledby="backup-history"><h2 id="backup-history">Recent recovery points &amp; attempts</h2>{view.runs.length === 0 ? <p>No backup attempts recorded.</p> : <TableScroll label="Backup history"><table><caption className="sr-only">Latest 20 manual backup attempts; failed attempts do not replace verified recovery points</caption><thead><tr><th scope="col">Requested</th><th scope="col">Scope</th><th scope="col">Verification</th><th scope="col">Recovery point</th><th scope="col">New stored data</th><th scope="col">Details</th></tr></thead><tbody>{view.runs.map((run) => <BackupHistoryRow key={run.run_id} run={run} />)}</tbody></table></TableScroll>}</section>;
}

function BackupHistoryRow({ run }: { run: SyncRun }) {
  const verified = run.status === "SUCCEEDED" && run.summary.verified === true;
  const unavailable = run.summary.unavailable_dependencies;
  return <tr><th scope="row">{date(run.requested_at)}</th><td>{backupScopeLabel(run.parameters.scope)}</td><td>{verified ? (run.parameters.scope ? "Isolated restore verified" : "Legacy byte verification") : run.status}{typeof unavailable === "number" && unavailable > 0 && <p>{unavailable.toLocaleString("en-GB")} unavailable</p>}</td><td className="max-w-56 break-all">{typeof run.summary.snapshot_id === "string" ? run.summary.snapshot_id : "Not available"}</td><td>{bytes(run.summary?.data_added_packed_bytes)}</td><td>{typeof run.summary.message === "string" ? run.summary.message : run.error_message ?? ""}</td></tr>;
}
