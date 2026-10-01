"use client";

import { useCallback, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { ExternalPrediction, ExternalSource } from "@/lib/contracts";
import { useResource } from "@/hooks/use-resource";
import { EmptyState, ResourceError, ResourceLoading } from "@/components/resource-state";

export function PredictionsPage() {
  const [filters, setFilters] = useState({ date: "", date_from: "", date_to: "", source: "", continent: "", country: "", competition: "", market: "", agreement: "" });
  const sourceQuery = useMemo(() => predictionQuery(filters), [filters]);
  const sourceLoad = useCallback((signal: AbortSignal) => api.sources(sourceQuery, signal), [sourceQuery]);
  const sources = useResource(`external-sources-${sourceQuery}`, sourceLoad);
  const key = Object.values(filters).join("|");
  const predictionLoad = useCallback((signal: AbortSignal) => api.predictions(predictionQuery(filters), signal), [filters]);
  const predictions = useResource(`external-predictions-${key}`, predictionLoad);
  const totals = useMemo(() => sourceTotals(sources.data), [sources.data]);
  const sourceItems = listOrEmpty(sources.data);
  const predictionItems = listOrEmpty(predictions.data);
  const consensus = useMemo(() => consensusRows(listOrEmpty(predictions.data)), [predictions.data]);

  return <div className="page">
    <header className="page-heading"><div><small>Independent comparison</small><h1>External predictions</h1><p>Public selections are stored as source evidence. They never feed, calibrate, or overwrite MatchForge forecasts.</p></div></header>
    <div className="summary-grid"><Metric label="Sources reviewed" value={String(totals.reviewed)} /><Metric label="Approved adapters" value={String(totals.approved)} /><Metric label="Stored selections" value={String(predictionItems.length)} /><Metric label="Model influence" value="0%" /></div>
    <PredictionFilters filters={filters} setFilters={setFilters} sources={sourceItems} />
    <SourceStatus error={sources.error} retry={sources.retry} />
    <PredictionResults predictions={predictionItems} loading={predictions.loading} error={predictions.error} retry={predictions.retry} consensus={consensus} />
    <SourceAudit sources={sourceItems} />
  </div>;
}

type Filters = { date: string; date_from: string; date_to: string; source: string; continent: string; country: string; competition: string; market: string; agreement: string };

function SourceStatus({ error, retry }: { error: string | null; retry: () => void }) {
  return error ? <ResourceError message={error} retry={retry} /> : null;
}

function PredictionFilters({ filters, setFilters, sources }: { filters: Filters; setFilters: (value: Filters) => void; sources: ExternalSource[] }) {
  const update = (name: keyof Filters, value: string) => setFilters({ ...filters, [name]: value });
  return <div className="filter-strip"><label>Date<input type="date" value={filters.date} onChange={(event) => update("date", event.target.value)} /></label><label>From<input type="date" value={filters.date_from} onChange={(event) => update("date_from", event.target.value)} /></label><label>To<input type="date" value={filters.date_to} onChange={(event) => update("date_to", event.target.value)} /></label><label>Source<select value={filters.source} onChange={(event) => update("source", event.target.value)}><option value="">All</option>{sources.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label><label>Continent<input value={filters.continent} onChange={(event) => update("continent", event.target.value)} placeholder="All" /></label><label>Country<input value={filters.country} onChange={(event) => update("country", event.target.value)} placeholder="All" /></label><label>Competition<input value={filters.competition} onChange={(event) => update("competition", event.target.value)} placeholder="All" /></label><label>Market<select value={filters.market} onChange={(event) => update("market", event.target.value)}><option value="">All</option><option value="RESULT_1X2">1X2</option><option value="DOUBLE_CHANCE">Double chance</option><option value="TOTAL_GOALS">Totals</option><option value="BTTS">BTTS</option></select></label><label>Agreement<select value={filters.agreement} onChange={(event) => update("agreement", event.target.value)}><option value="">All</option><option>AGREES</option><option>WEAK_SUPPORT</option><option>DISAGREES</option><option>UNABLE_TO_EVALUATE</option></select></label></div>;
}

function PredictionResults({ predictions, loading, error, retry, consensus }: { predictions: ExternalPrediction[]; loading: boolean; error: string | null; retry: () => void; consensus: ReturnType<typeof consensusRows> }) {
  if (loading) return <ResourceLoading label="Loading external selections" />;
  if (error) return <ResourceError message={error} retry={retry} />;
  if (predictions.length === 0) return <EmptyState title="No approved external selections" detail="The collection framework is ready, but all reviewed sources remain disabled until automated reuse is explicitly allowed. MatchForge does not bypass access controls or terms." />;
  return <><Consensus rows={consensus} /><section className="panel"><div className="table-scroll" tabIndex={0}><table><thead><tr><th>Prediction date</th><th>Source</th><th>League</th><th>Match</th><th>Kickoff</th><th>Market</th><th>External selection</th><th>MatchForge probability</th><th>Agreement</th></tr></thead><tbody>{predictions.map((item) => <tr key={item.id}><td>{item.prediction_date}</td><td><a href={item.source_page} rel="noreferrer" target="_blank">{item.source}</a></td><td>{item.competition}</td><td>{item.home_team} vs {item.away_team}</td><td>{item.kickoff_at ? new Date(item.kickoff_at).toLocaleString() : "—"}</td><td>{item.market}</td><td>{item.selection}</td><td>{item.matchforge_probability === null ? "—" : `${(item.matchforge_probability * 100).toFixed(1)}%`}</td><td><span className={`agreement ${item.agreement.toLowerCase()}`}>{item.agreement.replaceAll("_", " ")}</span></td></tr>)}</tbody></table></div></section></>;
}

function Consensus({ rows }: { rows: ReturnType<typeof consensusRows> }) {
  if (rows.length === 0) return null;
  return <section className="panel"><header><h2>External consensus</h2><small>Informational only · source count never changes MatchForge probabilities</small></header><div className="summary-grid metric-grid">{rows.map((row) => <div className="metric" key={row.fixture}><small>{row.fixture}</small><b>{row.count} of {row.total} · {row.selection}</b><span className={`agreement ${row.agreement.toLowerCase()}`}>{row.agreement.replaceAll("_", " ")}</span></div>)}</div></section>;
}

function SourceAudit({ sources }: { sources: ExternalSource[] }) {
  if (sources.length === 0) return null;
  return <section className="panel source-audit"><header><h2>Source access and performance audit</h2><small>Uses active source, league, market, and date-range filters</small></header><div className="table-scroll" tabIndex={0}><table><thead><tr><th>Source</th><th>Access</th><th>Adapter</th><th>Tracked</th><th>Settled</th><th>Correct</th><th>Hit rate</th><th>MatchForge agreement</th><th>Known issue</th></tr></thead><tbody>{sources.map((item) => <tr key={item.code}><td><a href={item.url} rel="noreferrer" target="_blank">{item.name}</a></td><td>{item.automated_access_status}</td><td>{item.adapter_status}</td><td>{item.tracked_selections}</td><td>{item.settled_selections}</td><td>{item.correct_selections}</td><td>{item.settled_hit_rate === null ? "—" : `${(item.settled_hit_rate * 100).toFixed(1)}%`}</td><td>{item.matchforge_agreement_rate === null ? "—" : `${(item.matchforge_agreement_rate * 100).toFixed(1)}%`}</td><td>{item.known_issues}</td></tr>)}</tbody></table></div></section>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><small>{label}</small><b>{value}</b></div>; }
function sourceTotals(sources: ExternalSource[] | null) { return { approved: sources?.filter((item) => item.adapter_status === "ENABLED").length ?? 0, reviewed: sources?.length ?? 0 }; }
function predictionQuery(filters: Filters) {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([name, value]) => { if (value) query.set(name, value); });
  return query;
}
function listOrEmpty<T>(items: T[] | null) { return items ?? []; }

function consensusRows(items: Awaited<ReturnType<typeof api.predictions>>) {
  const groups = new Map<string, typeof items>();
  for (const item of items) {
    const key = item.fixture_id ?? `${item.prediction_date}|${item.home_team}|${item.away_team}`;
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return [...groups.values()].map((group) => {
    const counts = new Map<string, number>();
    group.forEach((item) => counts.set(item.selection, (counts.get(item.selection) ?? 0) + 1));
    const [selection, count] = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0];
    const representative = group.find((item) => item.selection === selection) ?? group[0];
    return { fixture: `${representative.home_team} vs ${representative.away_team}`, selection, count, total: group.length, agreement: representative.agreement };
  });
}
