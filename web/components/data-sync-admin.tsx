"use client";

import { useMemo, type Dispatch, type SetStateAction } from "react";
import { api } from "@/lib/api";
import type { HistoricalCoverage, ProviderConfiguration, SyncRun, SyncType } from "@/lib/contracts";
import { syncLane, useSyncAdminState, type SyncFilters as Filters } from "@/hooks/use-sync-admin";

type Action = {
  type: SyncType; title: string; kind: string; description: string; button: string;
  start: (body: Record<string, string>) => Promise<SyncRun>; prominent?: boolean;
};

const ACTIONS: Action[] = [
  { type: "MVP_SYNC", title: "MVP Provider Sync", kind: "Live fixture backfill", description: "Backfill the selected fixture range, update scores, then refresh history and standings. Uses football-data.org when API-Football has no fixtures.", button: "Run MVP Sync", start: api.startMvpSync },
  { type: "OPENFOOTBALL", title: "OpenFootball", kind: "Historical bulk JSON", description: "Discover every usable season and competition in the football.json repository.", button: "Sync OpenFootball", start: api.startOpenFootballSync },
  { type: "FOOTBALL_DATA_UK", title: "Football-Data.co.uk", kind: "Historical CSV/ZIP archive", description: "Discover and import completed results from published download archives.", button: "Sync Football-Data.co.uk", start: api.startFootballDataUKSync },
  { type: "HISTORY_BACKFILL", title: "Historical Backfill", kind: "All configured sources", description: "Run bulk archives and resumable provider league/season jobs; reconcile stored observations without changing live polling.", button: "Run Both Historical Sources", start: api.startHistoryBackfill },
  { type: "FORECAST_REFRESH", title: "Forecast Refresh", kind: "Stored data only", description: "Generate missing MatchForge forecasts from currently stored historical data.", button: "Refresh Forecasts", start: api.startForecastRefresh },
  { type: "EXTERNAL_PREDICTIONS", title: "External Predictions", kind: "Public source collection", description: "Run the existing private-local external prediction collection.", button: "Sync External Predictions", start: api.startExternalPredictionsSync },
  { type: "FOTMOB_SYNC", title: "FotMob", kind: "Development-only operational feed", description: "Sync enabled FotMob fixtures, live states, results, and bounded match details without changing frozen forecasts.", button: "Sync FotMob", start: api.startFotMobSync },
  { type: "PITCHAPI_SYNC", title: "PitchAPI", kind: "Operational provider feed", description: "Sync fixtures with status=all plus bounded match resources, separate from research snapshots.", button: "Sync PitchAPI", start: api.startPitchAPISync },
  { type: "ALL_DATA", title: "Full Data Sync", kind: "Complete owner workflow", description: "Fixture range and scores → configured operational providers → historical sources → forecast refresh → external predictions.", button: "Run Full Sync", start: api.startAllDataSync, prominent: true },
];

export function DataSyncAdmin({ initialDate }: { initialDate: string }) {
  const state = useSyncAdminState(initialDate);
  const { active, clock, coverage, error, filters, laneErrors, laneBusy, loading, providerConfiguration, retry, runs, setFilters, start, stop, submitting, reload } = state;
  const latest = useMemo(() => new Map(ACTIONS.map((action) => [action.type, runs.find((run) => run.sync_type === action.type && run.status === "SUCCEEDED")])), [runs]);

  return <div className="page sync-admin">
    <header className="page-heading"><div><small>Local operations</small><h1>Data Sync</h1><p>Manual control of MatchForge provider ingestion and forecast refresh.</p></div></header>
    <SyncControls filters={filters} setFilters={setFilters} />
    {active.length ? active.map((run) => <SyncStatus key={run.run_id} active={run} clock={clock} disabled={submitting[syncLane(run.sync_type)] !== undefined} stopping={submitting[syncLane(run.sync_type)] === `STOP:${run.run_id}`} stopLabel={active.length > 1 ? `Stop ${label(run.sync_type)}` : "Stop sync"} onStop={() => void stop(run)} />) : <SyncStatus active={null} clock={clock} disabled={false} stopping={false} stopLabel="Stop sync" onStop={() => {}} />}
    {Object.entries(laneErrors).filter(([, message]) => message).map(([lane, message]) => <div key={lane} className="sync-error" role="alert"><strong>{lane === "LIVE_FOTMOB" ? "FotMob" : lane === "LIVE_PITCHAPI" ? "PitchAPI" : "Bulk"} sync failed</strong><span>{message}</span></div>)}
    {error && <div className="sync-error" role="alert"><strong>Sync request failed</strong><span>{error}</span><button onClick={() => void reload()}>Retry status</button></div>}
    <section className="sync-actions" aria-label="Data synchronization actions">
      {ACTIONS.map((action) => <SyncAction key={action.type} action={action} latest={latest.get(action.type)} providerConfiguration={providerConfiguration} disabled={loading || laneBusy(action.type)} busy={submitting[syncLane(action.type)] === action.type} onStart={() => void start(action.type, action.start)} />)}
    </section>
    <CoveragePanel coverage={coverage} loading={loading} />
    <HistoryAcquisitionPanel coverage={coverage} configuration={providerConfiguration} loading={loading} />
    <RunHistory runs={runs} loading={loading} clock={clock} canRetry={(run) => !loading && !laneBusy(run.sync_type)} onRetry={(run) => void retry(run)} />
  </div>;
}

function SyncControls({ filters, setFilters }: { filters: Filters; setFilters: Dispatch<SetStateAction<Filters>> }) {
  return <section className="sync-controls" aria-labelledby="sync-controls-title">
    <h2 id="sync-controls-title" className="sr-only">Sync controls</h2>
    <label>Through date<input type="date" value={filters.date} onChange={(event) => setFilters({ ...filters, date: event.target.value })} /></label>
    <label htmlFor="fixture-from-date">Backfill fixtures from</label><div><input id="fixture-from-date" type="date" max={filters.date} value={filters.from_date} onChange={(event) => setFilters({ ...filters, from_date: event.target.value })} /><small>Optional for MVP and Full Sync. Blank refreshes the through date and previous day.</small></div>
    <details><summary>Advanced filters</summary><div>
      <label>Season<input value={filters.season} onChange={(event) => setFilters({ ...filters, season: event.target.value })} placeholder="All seasons" /></label>
      <label>Competition<input value={filters.competition} onChange={(event) => setFilters({ ...filters, competition: event.target.value })} placeholder="All competitions" /></label>
      <label>Country<input value={filters.country} onChange={(event) => setFilters({ ...filters, country: event.target.value })} placeholder="All countries" /></label>
    </div></details>
  </section>;
}

function SyncStatus({ active, clock, disabled, stopping, stopLabel, onStop }: { active: SyncRun | null; clock: number; disabled: boolean; stopping: boolean; stopLabel: string; onStop: () => void }) {
  return <div className="sync-status" role="status" aria-live="polite">
    {active ? <><strong>{active.status === "QUEUED" ? "Queued" : "Running"}</strong><span>{label(active.sync_type)}</span><span aria-hidden="true">{elapsed(active.started_at ?? active.requested_at, clock)}</span><span>{stringMetric(active.summary, "current_phase") ?? "Preparing provider operation"}</span>{active.history_queue && <span>{queueProgress(active)}</span>}<button type="button" aria-label={stopLabel} onClick={onStop} disabled={disabled}>{stopping ? "Stopping…" : "Stop sync"}</button></> : <><strong>Ready</strong><span>No data synchronization is running.</span></>}
  </div>;
}

function SyncAction({ action, latest, providerConfiguration, disabled, busy, onStart }: { action: Action; latest?: SyncRun; providerConfiguration: ProviderConfiguration; disabled: boolean; busy: boolean; onStart: () => void }) {
  return <article className={`sync-action${action.prominent ? " prominent" : ""}`}>
    <div><small>{action.kind}</small><h2>{action.title}</h2><p>{action.description}</p></div>
    <dl>
      <Metric term="Last successful sync" value={latest ? formatTime(latest.finished_at) : "Never"} />
      <ProviderConfigurationMetric action={action} configuration={providerConfiguration} />
      <ActionMetrics action={action} latest={latest} />
    </dl>
    <button type="button" onClick={onStart} disabled={disabled} aria-busy={busy}>{busy ? "Starting…" : action.button}</button>
  </article>;
}

function ProviderConfigurationMetric({ action, configuration }: { action: Action; configuration: ProviderConfiguration }) {
  if (action.type === "FOTMOB_SYNC") return <Metric term="Configuration" value={configuration.fotmob_enabled ? "Enabled" : "Disabled"} />;
  if (action.type === "PITCHAPI_SYNC") return <Metric term="Configuration" value={configuration.pitchapi_enabled ? "Enabled" : "Disabled"} />;
  if (action.type === "ALL_DATA") return <Metric term="Operational schedule" value={configuration.operational_sync_interval === "0s" ? "Disabled" : configuration.operational_sync_interval} />;
  return null;
}

function ActionMetrics({ action, latest }: { action: Action; latest?: SyncRun }) {
  if (action.type === "OPENFOOTBALL") return <><Metric term="Latest source revision" value={shortMetric(latest, "source_revision")} /><Metric term="Resources cached" value={shortMetric(latest, "resources_cached")} /><Metric term="Matches stored" value={shortMetric(latest, "matches_inserted")} /><Metric term="Competitions mapped" value={shortMetric(latest, "competition_mappings_created")} /></>;
  if (action.type === "FOOTBALL_DATA_UK") return <><Metric term="Files cached" value={shortMetric(latest, "resources_cached")} /><Metric term="Matches stored" value={shortMetric(latest, "matches_inserted")} /><Metric term="Competitions mapped" value={shortMetric(latest, "competition_mappings_created")} /></>;
  if ((action.type === "MVP_SYNC" || action.type === "ALL_DATA") && latest?.history_queue) return <><Metric term="History queue total" value={latest.history_queue.total.toLocaleString()} /><Metric term="History queue succeeded" value={latest.history_queue.succeeded.toLocaleString()} /><Metric term="History queue pending" value={latest.history_queue.pending.toLocaleString()} /><Metric term="History queue failed" value={latest.history_queue.failed.toLocaleString()} /></>;
  if (action.type === "FOTMOB_SYNC" || action.type === "PITCHAPI_SYNC") return <><Metric term="Requests attempted / successful" value={`${shortMetric(latest, "attempted_requests")} / ${shortMetric(latest, "successful_requests")}`} /><Metric term="Fixtures fetched / matched" value={`${shortMetric(latest, "fetched")} / ${shortMetric(latest, "matched")}`} /><Metric term="Resources fetched" value={shortMetric(latest, "resources")} /><Metric term="Inserted / skipped" value={`${shortMetric(latest, "inserted")} / ${shortMetric(latest, "skipped")}`} /><Metric term="Canonical fixtures updated" value={shortMetric(latest, "updated")} /><Metric term="Unmatched fixtures" value={shortMetric(latest, "unmatched")} /><Metric term="Latest observation" value={shortMetric(latest, "latest_observed_at")} /><Metric term="Provider failures" value={shortMetric(latest, "failed")} /></>;
  return null;
}

function CoveragePanel({ coverage, loading }: { coverage: HistoricalCoverage | null; loading: boolean }) {
  const metrics = coverage ? [
    ["Historical matches", coverage.historical_matches], ["Competitions with history", coverage.competitions_with_history],
    ["Teams with ≥10 matches", coverage.teams_with_10_matches], ["Teams below 10", coverage.teams_below_10_matches],
    ["Scheduled fixtures", coverage.scheduled_fixtures], ["Forecast available", coverage.forecast_available],
    ["Not enough history", coverage.not_enough_history], ["Mapping failures", coverage.mapping_failures], ["Source conflicts", coverage.source_conflicts],
    ...(coverage.forecast_refresh_pending === undefined ? [] : [["Forecast refresh pending", coverage.forecast_refresh_pending]]),
    ...(coverage.forecast_refresh_complete === undefined ? [] : [["Forecast refresh complete", coverage.forecast_refresh_complete]]),
    ["Eligible / excluded history", `${coverage.eligible_history.toLocaleString()} / ${coverage.excluded_history.toLocaleString()}`],
    ["Verified provider matches", coverage.verified_provider_matches],
    ["Provisional fixtures", coverage.provisional_fixtures],
    ["Quarantined identity rows", coverage.identity_conflicts],
    ["Missing live scores", coverage.missing_live_scores], ["FotMob linked / unmatched observations", `${coverage.fotmob_mapped.toLocaleString()} / ${coverage.fotmob_unmapped.toLocaleString()}`],
    ["PitchAPI linked / unmatched observations", `${coverage.pitchapi_mapped.toLocaleString()} / ${coverage.pitchapi_unmapped.toLocaleString()}`],
    ["FotMob / PitchAPI history", `${coverage.fotmob_history.toLocaleString()} / ${coverage.pitchapi_history.toLocaleString()}`],
    ["API-Football quota", coverage.api_football_exhausted ? "Exhausted — requests suppressed" : coverage.api_football_remaining < 0 ? `${coverage.api_football_requests_used.toLocaleString()} requests; remaining unknown` : `${coverage.api_football_remaining.toLocaleString()} remaining`],
  ] : [];
  return <section className="coverage-panel" aria-labelledby="coverage-title"><header><div><small>Canonical store</small><h2 id="coverage-title">Historical Coverage</h2></div><span>{loading ? "Loading…" : "Current"}</span></header><p>Linked observations are not necessarily verified identities. Provisional, duplicate, quarantined, and not-yet-known history does not satisfy the ten-match forecast requirement.</p><dl>{metrics.map(([term, value]) => <Metric key={term} term={String(term)} value={typeof value === "number" ? value.toLocaleString() : value} />)}</dl>{!loading && !coverage && <p>Coverage is unavailable.</p>}</section>;
}

function HistoryAcquisitionPanel({ coverage, configuration, loading }: { coverage: HistoricalCoverage | null; configuration: ProviderConfiguration; loading: boolean }) {
  const schedule = configuration.history_sync_enabled === undefined ? "Unavailable" : configuration.history_sync_enabled ? `Enabled; every ${configuration.history_sync_interval ?? "unknown interval"}` : "Disabled";
  return <section className="coverage-panel" aria-labelledby="history-acquisition-title">
    <header><div><small>Background acquisition</small><h2 id="history-acquisition-title">Provider history queue</h2></div></header>
    <dl><Metric term="Automatic history schedule" value={schedule} /></dl>
    <p>Requests defer for live synchronization and provider limits. Oldest pending time records when this policy first observed the scope. Drain estimates use observed completions and remain unavailable until a full scheduling interval is measured.</p>
    {loading ? <p>Loading history acquisition…</p> : !coverage?.provider_history ? <p>History queue diagnostics are unavailable.</p> : coverage.provider_history.map((item) => <div key={item.provider}>
      <h3>{item.provider === "fotmob" ? "FotMob" : "PitchAPI"}</h3>
      <dl>
        <Metric term="Pending / running / completed" value={`${item.pending} / ${item.running} / ${item.completed}`} />
        <Metric term="Failed / deferred" value={`${item.failed} / ${item.deferred}`} />
        <Metric term="Requests today / historical" value={`${item.requests_used} / ${item.historical_requests_used}`} />
        <Metric term="Quota remaining" value={item.exhausted ? "Exhausted" : item.remaining_requests === null ? "Unknown" : String(item.remaining_requests)} />
        <Metric term="Deferred until" value={formatTime(item.deferred_until)} />
        <Metric term="Oldest pending observed" value={formatTime(item.oldest_pending_observed_at)} />
        <Metric term="Completions per hour" value={item.completions_per_hour === null ? "Unavailable" : item.completions_per_hour.toFixed(2)} />
        <Metric term="Estimated drain" value={item.estimated_drain_hours === null ? "Unavailable" : `About ${item.estimated_drain_hours.toFixed(1)} hours`} />
      </dl>
    </div>)}
  </section>;
}

function RunHistory({ runs, loading, clock, canRetry, onRetry }: { runs: SyncRun[]; loading: boolean; clock: number; canRetry: (run: SyncRun) => boolean; onRetry: (run: SyncRun) => void }) {
  return <section className="run-history" aria-labelledby="run-history-title"><header><small>Audit log</small><h2 id="run-history-title">Recent sync runs</h2></header>
    {loading ? <p>Loading sync history…</p> : runs.length === 0 ? <p>No manual sync runs yet.</p> : <div className="table-scroll" tabIndex={0} role="region" aria-label="Recent sync runs table"><table><caption className="sr-only">Recent data synchronization runs</caption><thead><tr><th>Started</th><th>Type</th><th>Status</th><th>Duration</th><th>Matches added</th><th>Forecasts created</th><th>Conflicts</th><th>Details</th><th>Actions</th></tr></thead><tbody>{runs.map((run) => <tr key={run.run_id}><td>{formatTime(run.started_at ?? run.requested_at)}</td><th scope="row">{label(run.sync_type)}</th><td><span className={`run-status ${run.status.toLowerCase()}`}>{run.status}</span></td><td>{duration(run, clock)}</td><td>{shortMetric(run, "matches_inserted")}</td><td>{shortMetric(run, "forecasts_created")}</td><td>{shortMetric(run, "result_conflicts")}</td><td><details><summary>View</summary><pre>{JSON.stringify(run.summary, null, 2)}</pre>{run.error_message && <p>{run.error_message}</p>}</details></td><td>{(run.status === "FAILED" || run.status === "CANCELLED") && <button type="button" onClick={() => onRetry(run)} disabled={!canRetry(run)}>Retry</button>}</td></tr>)}</tbody></table></div>}
  </section>;
}

function Metric({ term, value }: { term: string; value: string }) { return <div><dt>{term}</dt><dd>{value}</dd></div>; }
function shortMetric(run: SyncRun | undefined, key: string) { const value = run ? deepMetric(run.summary, key) : undefined; return typeof value === "number" ? value.toLocaleString() : typeof value === "string" ? value : "—"; }
function stringMetric(value: Record<string, unknown>, key: string) { const found = deepMetric(value, key); return typeof found === "string" ? found : null; }
function deepMetric(value: unknown, key: string): unknown { if (!value || typeof value !== "object") return undefined; const record = value as Record<string, unknown>; if (key in record) return record[key]; for (const child of Object.values(record)) { const found = deepMetric(child, key); if (found !== undefined) return found; } return undefined; }
function label(type: SyncType) { const labels: Record<SyncType, string> = { MVP_SYNC: "MVP Sync", OPENFOOTBALL: "OpenFootball", FOOTBALL_DATA_UK: "Football-Data.co.uk", HISTORY_BACKFILL: "Historical Backfill", FORECAST_REFRESH: "Forecast Refresh", CONTEXT_REPORTS: "Context Reports", EXTERNAL_PREDICTIONS: "External Predictions", ALL_DATA: "Full Data Sync", FOTMOB_SYNC: "FotMob", PITCHAPI_SYNC: "PitchAPI" }; return labels[type]; }
function formatTime(value: string | null) { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—"; }
function elapsed(value: string, now: number) { return `${Math.max(0, Math.floor((now - new Date(value).getTime()) / 1000))}s elapsed`; }
function duration(run: SyncRun, clock: number) { if (!run.started_at) return "—"; const end = run.finished_at ? new Date(run.finished_at).getTime() : clock; return `${Math.max(0, Math.round((end - new Date(run.started_at).getTime()) / 1000))}s`; }
function queueProgress(run: SyncRun) { const queue = run.history_queue; return queue ? `History queue: ${queue.succeeded}/${queue.total} succeeded, ${queue.running} running, ${queue.pending} pending, ${queue.failed} failed` : ""; }
