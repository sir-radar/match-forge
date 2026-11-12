"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { TableScroll } from "@/components/table-scroll";
import { formatStorageBytes, formatStorageTime } from "@/lib/storage";
import {
  classificationLabel, recoveryLabel, storageManagement,
  type CompareStatus, type ManagedResource, type StorageActionName, type StorageInventory, type StorageOperation, type StoragePlan,
} from "@/lib/storage-management";

const button = "min-h-11 rounded-sm border border-[var(--outline)] px-3 py-2 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--secondary)] disabled:cursor-not-allowed disabled:opacity-50";
const danger = `${button} border-[var(--error)] text-[var(--error)]`;
const field = "min-h-11 w-full rounded-sm border border-[var(--outline)] bg-[var(--lowest)] px-3 text-sm";
const panel = "rounded-sm border border-[var(--outline)] p-4";
const badgeTone: Record<string, string> = {
  PROTECTED: "border-[var(--primary)] text-[var(--primary)]",
  REVIEW_REQUIRED: "border-[var(--warning)] text-[var(--warning)]",
  ELIGIBLE: "border-[var(--secondary)] text-[var(--secondary)]",
};
const actionLabel: Record<StorageActionName, string> = { DELETE: "Delete", QUARANTINE: "Quarantine", RESTORE: "Restore", PURGE: "Permanently delete" };
type Tab = "databases" | "resources" | "operations";

export function StorageManagement() {
  const [inventory, setInventory] = useState<StorageInventory | null>(null);
  const [comparisons, setComparisons] = useState<CompareStatus[]>([]);
  const [operations, setOperations] = useState<StorageOperation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("databases");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [plan, setPlan] = useState<StoragePlan | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true; // Re-arm after a StrictMode or Suspense remount.
    return () => { mounted.current = false; };
  }, []);

  const load = useCallback(async (refresh = false) => {
    try {
      const [next, ops] = await Promise.all([storageManagement.inventory(refresh), storageManagement.operations()]);
      if (!mounted.current) return;
      setInventory(next.inventory); setComparisons(next.comparisons); setOperations(ops); setError(null);
      const actionable = new Set(next.inventory.resources.filter((r) => r.actions.length).map((r) => r.resource_id));
      setSelected((current) => new Set([...current].filter((id) => actionable.has(id))));
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : "Storage management unavailable.");
    }
  }, []);
  useEffect(() => {
    // A microtask, not a timer: background tabs throttle timers for minutes.
    let cancelled = false;
    void Promise.resolve().then(() => { if (!cancelled) void load(); });
    return () => { cancelled = true; };
  }, [load]);
  const active = operations.some((o) => o.state === "PENDING" || o.state === "RUNNING") || comparisons.some((c) => c.state === "QUEUED" || c.state === "RUNNING");
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void load(), 4000);
    return () => clearInterval(timer);
  }, [active, load]);

  async function run(task: () => Promise<void>) {
    setBusy(true); setNotice("");
    try { await task(); } catch (cause) { setError(cause instanceof Error ? cause.message : "Request failed."); }
    finally { if (mounted.current) setBusy(false); }
  }
  const preview = (action: StorageActionName, ids: string[]) => run(async () => {
    const next = await storageManagement.preview(action, ids);
    setPlan(next); setError(null);
  });
  const compare = (ids: string[]) => run(async () => {
    const result = await storageManagement.compare(ids);
    setNotice(`${String(result.queued)} comparison(s) queued. Results appear when they finish.`); await load();
  });

  if (!inventory) {
    return <section aria-labelledby="manage-heading" className="space-y-3">
      <h2 id="manage-heading" className="text-2xl font-semibold">Resource management</h2>
      {error ? <p role="alert">{error} <button type="button" className={button} onClick={() => void load()}>Retry</button></p> : <p role="status">Loading resources…</p>}
    </section>;
  }
  const resources = inventory.resources;
  return <section aria-labelledby="manage-heading" className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="manage-heading" className="text-2xl font-semibold">Resource management</h2>
      <button type="button" className={button} disabled={busy} onClick={() => void run(() => load(true))}>Re-measure resources</button>
    </div>
    <Overview inventory={inventory} />
    <div role="status" aria-live="polite">{notice}</div>
    {error && <p role="alert" className="text-[var(--error)]">{error}</p>}
    {plan && <PlanPanel plan={plan} onClose={() => setPlan(null)} onDone={async (message) => { setPlan(null); setSelected(new Set()); setNotice(message); setTab("operations"); await load(); }} />}
    <div role="tablist" aria-label="Storage views" className="flex flex-wrap gap-2">
      {(["databases", "resources", "operations"] as Tab[]).map((name) => <button key={name} type="button" role="tab" id={`tab-${name}`}
        aria-selected={tab === name} aria-controls={`panel-${name}`} className={`${button} ${tab === name ? "bg-[var(--high)]" : ""}`}
        onClick={() => setTab(name)}>{name === "databases" ? "Databases" : name === "resources" ? "All resources" : `Operations (${operations.length})`}</button>)}
    </div>
    <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
      {tab === "operations"
        ? <OperationsTable operations={operations} onCancel={(batch) => void run(async () => { await storageManagement.cancel(batch); await load(); })} />
        : <ResourceExplorer key={tab} resources={tab === "databases" ? resources.filter((r) => r.backend === "postgres") : resources}
          databases={tab === "databases"} comparisons={comparisons} selected={selected} setSelected={setSelected} busy={busy}
          onPreview={preview} onCompare={compare} onChanged={() => load()} />}
    </div>
  </section>;
}

function Overview({ inventory }: { inventory: StorageInventory }) {
  const s = inventory.summary, a = inventory.authority;
  const tiles: [string, string][] = [
    ["Host free / total", `${formatStorageBytes(s.host_free_bytes)} / ${formatStorageBytes(s.host_total_bytes)}`],
    [`PostgreSQL (${String(s.database_count)} databases)`, formatStorageBytes(s.postgres_bytes)],
    ["Authoritative database", formatStorageBytes(s.authoritative_bytes)],
    ["Other databases", formatStorageBytes(s.other_database_bytes)],
    ["Worktrees", formatStorageBytes(s.worktree_bytes)],
    ["Managed files", formatStorageBytes(s.managed_file_bytes)],
    ["Quarantined", formatStorageBytes(s.quarantined_bytes)],
    ["Eligible now (unique estimate)", formatStorageBytes(s.estimated_reclaimable_bytes)],
    ["Verified reclaimed", formatStorageBytes(s.verified_reclaimed_bytes)],
  ];
  return <div className="space-y-3">
    <p className={`${panel} ${a.verified ? "" : "border-[var(--error)]"}`}>
      {a.verified
        ? <>Authoritative operating database: <strong>{a.database}</strong> (OID {a.oid}, cluster {a.system_identifier}). <Badge value="PROTECTED" /> Deletion is permanently disabled.</>
        : <>Authoritative database identity is unverified. Database deletion is disabled. {a.problem}</>}
    </p>
    <dl className="grid gap-3 sm:grid-cols-3">
      {tiles.map(([label, value]) => <div key={label} className={panel}><dt className="text-xs uppercase">{label}</dt><dd className="text-lg font-semibold">{value}</dd></div>)}
    </dl>
    <p className="text-sm">{s.note} Counts: {Object.entries(s.count_by_classification).map(([k, v]) => `${classificationLabel[k as keyof typeof classificationLabel] ?? k} ${String(v)}`).join(" · ")}.</p>
    {inventory.warnings.length > 0 && <ul className="list-disc pl-5 text-sm">{inventory.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
  </div>;
}

function Badge({ value }: { value: string }) {
  return <span className={`inline-block rounded-sm border px-2 py-0.5 text-xs font-bold ${badgeTone[value] ?? ""}`}>{classificationLabel[value as keyof typeof classificationLabel] ?? value}</span>;
}

type Sort = "size" | "name" | "class";
function ResourceExplorer({ resources, databases, comparisons, selected, setSelected, busy, onPreview, onCompare, onChanged }: {
  resources: ManagedResource[]; databases: boolean; comparisons: CompareStatus[]; selected: Set<string>; setSelected: (s: Set<string>) => void;
  busy: boolean; onPreview: (a: StorageActionName, ids: string[]) => void; onCompare: (ids: string[]) => void; onChanged: () => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [backend, setBackend] = useState("all");
  const [klass, setKlass] = useState("all");
  const [sort, setSort] = useState<Sort>("size");
  const [open, setOpen] = useState<string | null>(null);
  const filtered = useMemo(() => resources
    .filter((r) => (backend === "all" || r.backend === backend) && (klass === "all" || r.classification === klass)
      && `${r.name} ${r.location} ${r.purpose}`.toLowerCase().includes(query.toLowerCase()))
    .sort((x, y) => sort === "name" ? x.name.localeCompare(y.name) : sort === "class" ? x.classification.localeCompare(y.classification)
      : (y.allocated_bytes ?? 0) - (x.allocated_bytes ?? 0)), [resources, backend, klass, query, sort]);
  const selectable = filtered.filter((r) => r.actions.length > 0);
  const chosen = resources.filter((r) => selected.has(r.resource_id));
  const toggle = (id: string) => { const next = new Set(selected); if (next.has(id)) next.delete(id); else next.add(id); setSelected(next); };
  const ids = chosen.map((r) => r.resource_id);
  const comparing = new Map(comparisons.map((c) => [c.resource_id, c]));
  const comparable = resources.filter((r) => r.backend === "postgres" && r.role !== "AUTHORITATIVE_OPERATING_DATABASE" && r.name !== "postgres" && !r.quarantine && r.active_consumers === 0);
  return <div className="space-y-3">
    <div className="grid gap-3 sm:grid-cols-4">
      <label className="text-sm">Search<input className={field} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Name or path" /></label>
      {!databases && <label className="text-sm">Type<select className={field} value={backend} onChange={(e) => setBackend(e.target.value)}>
        <option value="all">All types</option><option value="postgres">Databases</option><option value="git">Worktrees</option><option value="filesystem">Files</option></select></label>}
      <label className="text-sm">Protection<select className={field} value={klass} onChange={(e) => setKlass(e.target.value)}>
        <option value="all">All</option><option value="PROTECTED">Protected</option><option value="REVIEW_REQUIRED">Review required</option><option value="ELIGIBLE">Eligible</option></select></label>
      <label className="text-sm">Sort<select className={field} value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
        <option value="size">Largest first</option><option value="name">Name</option><option value="class">Protection</option></select></label>
    </div>
    <div className="flex flex-wrap items-center gap-2" aria-label="Bulk actions" role="group">
      <span className="text-sm">{chosen.length} selected of {selectable.length} actionable in this view ({filtered.length} shown)</span>
      <button type="button" className={button} disabled={!selectable.length} onClick={() => setSelected(new Set([...selected, ...selectable.map((r) => r.resource_id)]))}>Select all actionable</button>
      <button type="button" className={button} disabled={!chosen.length} onClick={() => setSelected(new Set())}>Clear</button>
      {databases && <button type="button" className={button} disabled={busy || !comparable.length} onClick={() => onCompare(comparable.slice(0, 50).map((r) => r.resource_id))}>Compare all unchecked ({Math.min(comparable.length, 50)})</button>}
      <button type="button" className={button} disabled={busy || !chosen.length} onClick={() => onPreview("QUARANTINE", ids)}>Quarantine selected</button>
      <button type="button" className={button} disabled={busy || !chosen.length} onClick={() => onPreview("RESTORE", ids)}>Restore selected</button>
      <button type="button" className={danger} disabled={busy || !chosen.length} onClick={() => onPreview(chosen.some((r) => r.quarantine) ? "PURGE" : "DELETE", ids)}>Delete selected…</button>
    </div>
    <TableScroll label={databases ? "Databases" : "Managed resources"}><table>
      <caption className="sr-only">{databases ? "Databases in the operating cluster" : "Managed storage resources"}</caption>
      <thead><tr><th scope="col"><span className="sr-only">Select</span></th><th scope="col">Resource</th><th scope="col">Size</th><th scope="col">Protection</th>
        <th scope="col">Recovery</th><th scope="col">{databases ? "Unique rows" : "Type"}</th><th scope="col">Consumers</th><th scope="col"><span className="sr-only">Details</span></th></tr></thead>
      <tbody>{filtered.map((r) => <ResourceRow key={r.resource_id} r={r} databases={databases} checked={selected.has(r.resource_id)} onToggle={() => toggle(r.resource_id)}
        open={open === r.resource_id} onOpen={() => setOpen(open === r.resource_id ? null : r.resource_id)} compare={comparing.get(r.resource_id)}
        busy={busy} onPreview={onPreview} onCompare={onCompare} onChanged={onChanged} />)}</tbody>
    </table></TableScroll>
  </div>;
}

function ResourceRow({ r, databases, checked, onToggle, open, onOpen, compare, busy, onPreview, onCompare, onChanged }: {
  r: ManagedResource; databases: boolean; checked: boolean; onToggle: () => void; open: boolean; onOpen: () => void; compare?: CompareStatus;
  busy: boolean; onPreview: (a: StorageActionName, ids: string[]) => void; onCompare: (ids: string[]) => void; onChanged: () => Promise<void>;
}) {
  const unique = r.evidence ? (r.evidence.unique_identity_rows ?? "—") : "Not compared";
  return <>
    <tr>
      <td><input type="checkbox" className="h-5 w-5" checked={checked} disabled={!r.actions.length} onChange={onToggle}
        aria-label={r.actions.length ? `Select ${r.name}` : `${r.name} cannot be selected: ${classificationLabel[r.classification]}`} /></td>
      <th scope="row" className="max-w-[22rem] whitespace-normal [overflow-wrap:anywhere]">{r.name}{r.role === "AUTHORITATIVE_OPERATING_DATABASE" && " (operating)"}{r.quarantine && " (quarantined)"}<br /><small>{r.purpose}</small></th>
      <td>{!r.measurement_complete && "≥ "}{formatStorageBytes(r.allocated_bytes)}</td>
      <td><Badge value={r.classification} /></td>
      <td className="whitespace-normal">{recoveryLabel[r.recovery] ?? r.recovery}</td>
      <td>{databases ? (compare && compare.state !== "SUCCEEDED" ? `Compare ${compare.state.toLowerCase()}` : String(unique)) : r.backend}</td>
      <td>{r.active_consumers}</td>
      <td><button type="button" className={button} aria-expanded={open} onClick={onOpen}>{open ? "Hide" : "Details"}<span className="sr-only"> for {r.name}</span></button></td>
    </tr>
    {open && <tr><td colSpan={8} className="whitespace-normal bg-[var(--low)]"><ResourceDetails r={r} busy={busy} onPreview={onPreview} onCompare={onCompare} onChanged={onChanged} /></td></tr>}
  </>;
}

function ResourceDetails({ r, busy, onPreview, onCompare, onChanged }: {
  r: ManagedResource; busy: boolean; onPreview: (a: StorageActionName, ids: string[]) => void; onCompare: (ids: string[]) => void; onChanged: () => Promise<void>;
}) {
  const protectedResource = r.classification === "PROTECTED";
  const canCompare = r.backend === "postgres" && r.role !== "AUTHORITATIVE_OPERATING_DATABASE" && r.name !== "postgres" && !r.quarantine;
  const uniqueTables = r.evidence ? Object.entries(r.evidence.tables).filter(([, t]) => (t.absent_from_authoritative ?? 0) > 0 || t.schema) : [];
  return <div className="space-y-3 p-2 text-sm">
    <p className="[overflow-wrap:anywhere]">{r.location}</p>
    <div><h3 className="font-semibold">{protectedResource ? "Why deletion is unavailable" : "Assessment"}</h3>
      <ul className="list-disc pl-5">{r.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul></div>
    {r.remediation.length > 0 && <div><h3 className="font-semibold">Required remediation</h3><ul className="list-disc pl-5">{r.remediation.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
    {r.evidence && <div><h3 className="font-semibold">Comparison with the authoritative database</h3>
      <p>{r.evidence.finding.replaceAll("_", " ").toLowerCase()} · {formatStorageTime(r.evidence.observed_at)}{!r.evidence.current && ` · stale: ${r.evidence.stale_reason ?? ""}`}</p>
      {uniqueTables.length > 0 && <ul className="list-disc pl-5">{uniqueTables.map(([table, t]) => <li key={table} className="[overflow-wrap:anywhere]">
        {table}: {t.schema ?? `${String(t.absent_from_authoritative)} of ${String(t.rows)} rows absent`}{t.absent_samples?.length ? ` (e.g. ${t.absent_samples.slice(0, 3).join(", ")})` : ""}</li>)}</ul>}
    </div>}
    {r.disposition && <p>Owner disposition: {r.disposition.disposition} — {r.disposition.rationale}</p>}
    {r.quarantine && <p>Quarantined {formatStorageTime(r.quarantine.quarantined_at)} from {r.quarantine.original_location}. Retained until {formatStorageTime(r.quarantine.retain_until)}.</p>}
    <div className="flex flex-wrap gap-2">
      {canCompare && <button type="button" className={button} disabled={busy || r.active_consumers > 0} onClick={() => onCompare([r.resource_id])}>Compare with operating database</button>}
      {(["QUARANTINE", "RESTORE"] as StorageActionName[]).filter((a) => r.actions.includes(a)).map((a) =>
        <button key={a} type="button" className={button} disabled={busy} onClick={() => onPreview(a, [r.resource_id])}>{actionLabel[a]}</button>)}
      <button type="button" className={danger} disabled={busy || !(r.actions.includes("DELETE") || r.actions.includes("PURGE"))}
        title={protectedResource ? "Protected: deletion disabled" : undefined}
        onClick={() => onPreview(r.actions.includes("PURGE") ? "PURGE" : "DELETE", [r.resource_id])}>{r.actions.includes("PURGE") ? "Permanently delete…" : "Delete…"}</button>
    </div>
    {protectedResource && <p><Badge value="PROTECTED" /> {r.role === "AUTHORITATIVE_OPERATING_DATABASE" ? "This is MatchForge's authoritative operating database. Deletion is permanently disabled through Storage Management." : "Deletion disabled."}</p>}
    <OwnerDecision r={r} onChanged={onChanged} />
  </div>;
}

function OwnerDecision({ r, onChanged }: { r: ManagedResource; onChanged: () => Promise<void> }) {
  const [text, setText] = useState(""), [token, setToken] = useState(""), [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  const canDispose = r.classification === "REVIEW_REQUIRED" && r.evidence_sha256 !== "" && r.remediation.some((x) => x.includes("record that"));
  const canProtect = r.classification !== "PROTECTED";
  if (!canDispose && !canProtect) return null;
  async function act(kind: "dispose" | "preserve" | "protect") {
    setBusy(true); setMessage("");
    try {
      if (kind === "protect") await storageManagement.protect(r, text, token);
      else await storageManagement.dispose(r, kind === "dispose" ? "UNIQUE_DATA_NOT_REQUIRED" : "PRESERVE", text, token);
      setText(""); setToken(""); setMessage("Recorded."); await onChanged();
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : "Not recorded."); }
    finally { setBusy(false); }
  }
  return <details className={panel}>
    <summary className="cursor-pointer">Record an owner decision</summary>
    <div className="mt-3 grid gap-3 sm:grid-cols-2">
      <label>Reason (at least 20 characters for a disposition)<textarea className={`${field} min-h-20 py-2`} value={text} onChange={(e) => setText(e.target.value)} /></label>
      <label>Owner credential<input type="password" autoComplete="off" className={field} value={token} onChange={(e) => setToken(e.target.value)} /></label>
    </div>
    <div className="mt-3 flex flex-wrap gap-2">
      {canDispose && <button type="button" className={button} disabled={busy || text.trim().length < 20 || !token} onClick={() => void act("dispose")}>Unique content is not required</button>}
      {canDispose && <button type="button" className={button} disabled={busy || text.trim().length < 20 || !token} onClick={() => void act("preserve")}>Preserve this resource</button>}
      {canProtect && <button type="button" className={button} disabled={busy || text.trim().length < 5 || !token} onClick={() => void act("protect")}>Protect permanently</button>}
    </div>
    <p role="status">{message}</p>
  </details>;
}

function PlanPanel({ plan, onClose, onDone }: { plan: StoragePlan; onClose: () => void; onDone: (message: string) => Promise<void> }) {
  const [typed, setTyped] = useState(""), [token, setToken] = useState(""), [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  const ready = plan.items.length > 0 && understood && token !== "" && (!plan.typed_confirmation || typed === plan.typed_confirmation);
  async function execute() {
    setBusy(true); setError("");
    try {
      const batch = await storageManagement.execute(plan, typed, token);
      await onDone(`${actionLabel[plan.action]} started for ${String(batch.operations)} resource(s). Progress is shown under Operations.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Not executed."); setBusy(false); }
  }
  return <section aria-labelledby="plan-heading" className={`${panel} space-y-3 ${plan.irreversible ? "border-[var(--error)]" : ""}`}>
    <h3 id="plan-heading" ref={heading} tabIndex={-1} className="text-xl font-semibold">{actionLabel[plan.action]}: review {plan.items.length} resource(s)</h3>
    {plan.items.length > 0 && <ul className="list-disc pl-5 text-sm">{plan.items.map((i) => <li key={i.resource_id} className="[overflow-wrap:anywhere]">
      {i.name || i.location} — {formatStorageBytes(i.expected_bytes)}{i.overlaps && ` (inside ${i.overlaps}; counted once)`}</li>)}</ul>}
    {plan.blocked.length > 0 && <div><p className="font-semibold">{plan.blocked.length} blocked and excluded (independent items still proceed):</p>
      <ul className="list-disc pl-5 text-sm">{plan.blocked.map((i) => <li key={i.resource_id} className="[overflow-wrap:anywhere]">{i.name || i.resource_id}: {i.reasons.join("; ")}</li>)}</ul></div>}
    {plan.irreversible && <p>Expected unique physical savings: <strong>{formatStorageBytes(plan.expected_unique_bytes)}</strong>. Actual savings are measured after deletion.</p>}
    <ul className="list-disc pl-5 text-sm">{plan.consequences.map((c) => <li key={c}>{c}</li>)}</ul>
    {plan.blocked.length > 0 && plan.items.length > 0 && <p className="text-sm">To proceed, the server re-checks only the eligible items above.</p>}
    {plan.items.length > 0 && <div className="grid gap-3 sm:grid-cols-2">
      {plan.typed_confirmation && <label>Type <code>{plan.typed_confirmation}</code> to confirm<input className={field} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" /></label>}
      <label>Owner credential<input type="password" autoComplete="off" className={field} value={token} onChange={(e) => setToken(e.target.value)} /></label>
      <label className="flex items-center gap-2 sm:col-span-2"><input type="checkbox" className="h-5 w-5" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} />
        I approve exactly these resources{plan.irreversible ? " and understand this cannot be undone" : ""}.</label>
    </div>}
    {error && <p role="alert" className="text-[var(--error)]">{error}</p>}
    <div className="flex flex-wrap gap-2">
      {plan.items.length > 0 && <button type="button" className={plan.irreversible ? danger : button} disabled={busy || !ready} onClick={() => void execute()}>
        {actionLabel[plan.action]} {plan.items.length} resource(s)</button>}
      <button type="button" className={button} onClick={onClose}>Close</button>
    </div>
  </section>;
}

function OperationsTable({ operations, onCancel }: { operations: StorageOperation[]; onCancel: (batch: string) => void }) {
  if (!operations.length) return <p>No storage operations yet.</p>;
  const pendingBatches = new Set(operations.filter((o) => o.state === "PENDING").map((o) => o.batch_id));
  return <div className="space-y-2">
    {[...pendingBatches].map((b) => <button key={b} type="button" className={button} onClick={() => onCancel(b)}>Cancel pending items in batch {b.slice(0, 8)}</button>)}
    <TableScroll label="Storage operations"><table>
      <caption className="sr-only">Storage operation history</caption>
      <thead><tr><th scope="col">Requested</th><th scope="col">Action</th><th scope="col">Resource</th><th scope="col">State</th><th scope="col">Expected</th><th scope="col">Verified reclaimed</th><th scope="col">Detail</th></tr></thead>
      <tbody>{operations.map((o) => <tr key={o.operation_id}>
        <th scope="row">{formatStorageTime(o.created_at)}</th><td>{actionLabel[o.action]}</td>
        <td className="max-w-[20rem] whitespace-normal [overflow-wrap:anywhere]">{o.location}</td><td>{o.state}</td>
        <td>{formatStorageBytes(o.expected_bytes)}</td><td>{o.state === "SUCCEEDED" ? formatStorageBytes(o.reclaimed_bytes) : "—"}</td>
        <td className="whitespace-normal">{o.error ?? (typeof o.measurement.method === "string" ? o.measurement.method : "")}</td>
      </tr>)}</tbody>
    </table></TableScroll>
  </div>;
}
