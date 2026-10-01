"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { HistoricalCoverage, SyncRun, SyncType } from "@/lib/contracts";

type Filters = { date: string; season: string; competition: string; country: string };
type Action = {
  type: SyncType; title: string; kind: string; description: string; button: string;
  start: (body: Record<string, string>) => Promise<SyncRun>; prominent?: boolean;
};

const ACTIONS: Action[] = [
  { type: "MVP_SYNC", title: "MVP Provider Sync", kind: "Live provider catalog", description: "API-Football discovery and football-data.org fallback.", button: "Run MVP Sync", start: api.startMvpSync },
  { type: "OPENFOOTBALL", title: "OpenFootball", kind: "Historical bulk JSON", description: "Discover every usable season and competition in the football.json repository.", button: "Sync OpenFootball", start: api.startOpenFootballSync },
  { type: "FOOTBALL_DATA_UK", title: "Football-Data.co.uk", kind: "Historical CSV/ZIP archive", description: "Discover and import completed results from published download archives.", button: "Sync Football-Data.co.uk", start: api.startFootballDataUKSync },
  { type: "HISTORY_BACKFILL", title: "Historical Backfill", kind: "Both bulk sources", description: "Run OpenFootball, then Football-Data.co.uk, across all discoverable history.", button: "Run Both Historical Sources", start: api.startHistoryBackfill },
  { type: "FORECAST_REFRESH", title: "Forecast Refresh", kind: "Stored data only", description: "Generate missing MatchForge forecasts from currently stored historical data.", button: "Refresh Forecasts", start: api.startForecastRefresh },
  { type: "EXTERNAL_PREDICTIONS", title: "External Predictions", kind: "Public source collection", description: "Run the existing private-local external prediction collection.", button: "Sync External Predictions", start: api.startExternalPredictionsSync },
  { type: "ALL_DATA", title: "Full Data Sync", kind: "Complete owner workflow", description: "MVP providers → both historical sources → forecast refresh → external predictions.", button: "Run Full Sync", start: api.startAllDataSync, prominent: true },
];

export function DataSyncAdmin() {
  const [filters, setFilters] = useState<Filters>(() => ({ date: localDate(), season: "", competition: "", country: "" }));
  const [runs, setRuns] = useState<SyncRun[]>([]);
  const [coverage, setCoverage] = useState<HistoricalCoverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState<SyncType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [clock, setClock] = useState(0);
  const active = runs.find((run) => run.status === "QUEUED" || run.status === "RUNNING") ?? null;

  const reload = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await api.syncRuns(signal);
      setRuns(response.runs); setCoverage(response.coverage); setError(null);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(errorMessage(cause));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { const controller = new AbortController(); queueMicrotask(() => void reload(controller.signal)); return () => controller.abort(); }, [reload]);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    const poll = window.setInterval(async () => {
      try {
        const updated = await api.syncRun(active.run_id);
        setRuns((current) => current.map((run) => run.run_id === updated.run_id ? updated : run));
        if (updated.status === "SUCCEEDED" || updated.status === "FAILED") await reload();
      } catch (cause) { setError(errorMessage(cause)); }
    }, 2500);
    return () => { window.clearInterval(timer); window.clearInterval(poll); };
  }, [active, reload]);

  const latest = useMemo(() => new Map(ACTIONS.map((action) => [action.type, runs.find((run) => run.sync_type === action.type && run.status === "SUCCEEDED")])), [runs]);
  const start = async (action: Action) => {
    if (active || submitting) return;
    setSubmitting(action.type); setError(null);
    try {
      const body = Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
      const run = await action.start(body);
      setClock(new Date(run.requested_at).getTime());
      setRuns((current) => [run, ...current]);
    } catch (cause) {
      setError(errorMessage(cause));
      if (cause instanceof ApiError && cause.status === 409) await reload();
    } finally { setSubmitting(null); }
  };

  return <div className="page sync-admin">
    <header className="page-heading"><div><small>Local operations</small><h1>Data Sync</h1><p>Manual control of MatchForge provider ingestion and forecast refresh.</p></div></header>
    <section className="sync-controls" aria-labelledby="sync-controls-title">
      <h2 id="sync-controls-title" className="sr-only">Sync controls</h2>
      <label>Date<input type="date" value={filters.date} onChange={(event) => setFilters({ ...filters, date: event.target.value })} /></label>
      <details><summary>Advanced filters</summary><div>
        <label>Season<input value={filters.season} onChange={(event) => setFilters({ ...filters, season: event.target.value })} placeholder="All seasons" /></label>
        <label>Competition<input value={filters.competition} onChange={(event) => setFilters({ ...filters, competition: event.target.value })} placeholder="All competitions" /></label>
        <label>Country<input value={filters.country} onChange={(event) => setFilters({ ...filters, country: event.target.value })} placeholder="All countries" /></label>
      </div></details>
    </section>
    <div className="sync-status" role="status" aria-live="polite">
      {active ? <><strong>{active.status === "QUEUED" ? "Queued" : "Running"}</strong><span>{label(active.sync_type)}</span><span>{elapsed(active.started_at ?? active.requested_at, clock)}</span><span>{stringMetric(active.summary, "current_phase") ?? "Preparing provider operation"}</span></> : <><strong>Ready</strong><span>No data synchronization is running.</span></>}
    </div>
    {error && <div className="sync-error" role="alert"><strong>Sync request failed</strong><span>{error}</span><button onClick={() => void reload()}>Retry status</button></div>}
    <section className="sync-actions" aria-label="Data synchronization actions">
      {ACTIONS.map((action) => <SyncAction key={action.type} action={action} latest={latest.get(action.type)} disabled={Boolean(active || submitting)} busy={submitting === action.type} onStart={() => void start(action)} />)}
    </section>
    <CoveragePanel coverage={coverage} loading={loading} />
    <RunHistory runs={runs} loading={loading} clock={clock} />
  </div>;
}

function SyncAction({ action, latest, disabled, busy, onStart }: { action: Action; latest?: SyncRun; disabled: boolean; busy: boolean; onStart: () => void }) {
  return <article className={`sync-action${action.prominent ? " prominent" : ""}`}>
    <div><small>{action.kind}</small><h2>{action.title}</h2><p>{action.description}</p></div>
    <dl>
      <Metric term="Last successful sync" value={latest ? formatTime(latest.finished_at) : "Never"} />
      {action.type === "OPENFOOTBALL" && <><Metric term="Latest source revision" value={shortMetric(latest, "source_revision")} /><Metric term="Resources cached" value={shortMetric(latest, "resources_cached")} /><Metric term="Matches stored" value={shortMetric(latest, "matches_inserted")} /><Metric term="Competitions mapped" value={shortMetric(latest, "competition_mappings_created")} /></>}
      {action.type === "FOOTBALL_DATA_UK" && <><Metric term="Files cached" value={shortMetric(latest, "resources_cached")} /><Metric term="Matches stored" value={shortMetric(latest, "matches_inserted")} /><Metric term="Competitions mapped" value={shortMetric(latest, "competition_mappings_created")} /></>}
    </dl>
    <button type="button" onClick={onStart} disabled={disabled} aria-busy={busy}>{busy ? "Starting…" : action.button}</button>
  </article>;
}

function CoveragePanel({ coverage, loading }: { coverage: HistoricalCoverage | null; loading: boolean }) {
  const metrics = coverage ? [
    ["Historical matches", coverage.historical_matches], ["Competitions with history", coverage.competitions_with_history],
    ["Teams with ≥10 matches", coverage.teams_with_10_matches], ["Teams below 10", coverage.teams_below_10_matches],
    ["Scheduled fixtures", coverage.scheduled_fixtures], ["Forecast available", coverage.forecast_available],
    ["Not enough history", coverage.not_enough_history], ["Mapping failures", coverage.mapping_failures], ["Source conflicts", coverage.source_conflicts],
  ] : [];
  return <section className="coverage-panel" aria-labelledby="coverage-title"><header><div><small>Canonical store</small><h2 id="coverage-title">Historical Coverage</h2></div><span>{loading ? "Loading…" : "Current"}</span></header><dl>{metrics.map(([term, value]) => <Metric key={term} term={String(term)} value={Number(value).toLocaleString()} />)}</dl>{!loading && !coverage && <p>Coverage is unavailable.</p>}</section>;
}

function RunHistory({ runs, loading, clock }: { runs: SyncRun[]; loading: boolean; clock: number }) {
  return <section className="run-history" aria-labelledby="run-history-title"><header><small>Audit log</small><h2 id="run-history-title">Recent sync runs</h2></header>
    {loading ? <p>Loading sync history…</p> : runs.length === 0 ? <p>No manual sync runs yet.</p> : <div className="table-scroll"><table><caption className="sr-only">Recent data synchronization runs</caption><thead><tr><th>Started</th><th>Type</th><th>Status</th><th>Duration</th><th>Matches added</th><th>Forecasts created</th><th>Conflicts</th><th>Details</th></tr></thead><tbody>{runs.map((run) => <tr key={run.run_id}><td>{formatTime(run.started_at ?? run.requested_at)}</td><th scope="row">{label(run.sync_type)}</th><td><span className={`run-status ${run.status.toLowerCase()}`}>{run.status}</span></td><td>{duration(run, clock)}</td><td>{shortMetric(run, "matches_inserted")}</td><td>{shortMetric(run, "forecasts_created")}</td><td>{shortMetric(run, "result_conflicts")}</td><td><details><summary>View</summary><pre>{JSON.stringify(run.summary, null, 2)}</pre>{run.error_message && <p>{run.error_message}</p>}</details></td></tr>)}</tbody></table></div>}
  </section>;
}

function Metric({ term, value }: { term: string; value: string }) { return <div><dt>{term}</dt><dd>{value}</dd></div>; }
function shortMetric(run: SyncRun | undefined, key: string) { const value = run ? deepMetric(run.summary, key) : undefined; return typeof value === "number" ? value.toLocaleString() : typeof value === "string" ? value : "—"; }
function stringMetric(value: Record<string, unknown>, key: string) { const found = deepMetric(value, key); return typeof found === "string" ? found : null; }
function deepMetric(value: unknown, key: string): unknown { if (!value || typeof value !== "object") return undefined; const record = value as Record<string, unknown>; if (key in record) return record[key]; for (const child of Object.values(record)) { const found = deepMetric(child, key); if (found !== undefined) return found; } return undefined; }
function label(type: SyncType) { return type.split("_").map((part) => part[0] + part.slice(1).toLowerCase()).join(" "); }
function formatTime(value: string | null) { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—"; }
function elapsed(value: string, now: number) { return `${Math.max(0, Math.floor((now - new Date(value).getTime()) / 1000))}s elapsed`; }
function duration(run: SyncRun, clock: number) { if (!run.started_at) return "—"; const end = run.finished_at ? new Date(run.finished_at).getTime() : clock; return `${Math.max(0, Math.round((end - new Date(run.started_at).getTime()) / 1000))}s`; }
function localDate() { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`; }
function errorMessage(cause: unknown) { if (cause instanceof ApiError) { if (cause.status === 409) return "A data synchronization is already running. Status has been refreshed."; if (cause.status >= 500) return `The API could not start or read the sync. ${cause.message}`; return cause.message; } if (cause instanceof Error) return `Network or response error: ${cause.message}`; return "Unknown synchronization error."; }
