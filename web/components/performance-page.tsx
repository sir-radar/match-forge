"use client";

import { useCallback, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Competition, Performance } from "@/lib/contracts";
import { useResource } from "@/hooks/use-resource";
import { EmptyState, ResourceError, ResourceLoading } from "@/components/resource-state";

export function PerformancePage() {
  const competitionLoad = useCallback((signal: AbortSignal) => api.competitions(new URLSearchParams({ forecast_available: "true" }), signal), []);
  const competitions = useResource("performance-competitions", competitionLoad);
  const [competitionID, setCompetitionID] = useState("");
  const selectedID = activeCompetitionID(competitionID, competitions.data);
  const performanceLoad = useCallback((signal: AbortSignal) => loadPerformance(selectedID, signal), [selectedID]);
  const performance = useResource(`performance-${selectedID || "none"}`, performanceLoad);
  const selected = competitions.data?.find((item) => item.id === selectedID);

  return <div className="page">
    <header className="page-heading"><div><small>Model monitoring</small><h1>League-level performance</h1><p>Chronological results from stored pre-kickoff MVP_FORECAST records. A minimum of 50 settled forecasts is required for a rating.</p></div></header>
    <PerformanceResources competitions={competitions} performance={performance} selectedID={selectedID} selected={selected} setCompetitionID={setCompetitionID} />
  </div>;
}

function PerformanceResources({ competitions, performance, selectedID, selected, setCompetitionID }: {
  competitions: ReturnType<typeof useResource<Competition[]>>;
  performance: ReturnType<typeof useResource<Performance>>;
  selectedID: string;
  selected?: Competition;
  setCompetitionID: (value: string) => void;
}) {
  return <>
    <CompetitionStatus state={competitions} />
    <CompetitionPicker competitions={competitions.data ?? []} selectedID={selectedID} setCompetitionID={setCompetitionID} />
    <PerformanceStatus state={performance} selected={Boolean(selectedID)} />
    <PerformanceData item={performance.data} competition={selected} />
    <EmptyCompetitionState competitions={competitions.data} />
  </>;
}

function PerformanceData({ item, competition }: { item: Performance | null; competition?: Competition }) {
  return item ? <PerformanceReport item={item} competition={competition} /> : null;
}

function EmptyCompetitionState({ competitions }: { competitions: Competition[] | null }) {
  return competitions?.length === 0 ? <EmptyState title="No published forecasts" detail="Performance begins only after immutable pre-kickoff forecasts have settled results." /> : null;
}

function CompetitionStatus({ state }: { state: ReturnType<typeof useResource<Competition[]>> }) {
  if (state.loading) return <ResourceLoading label="Loading rated competitions" />;
  if (state.error) return <ResourceError message={state.error} retry={state.retry} />;
  return null;
}

function PerformanceStatus({ state, selected }: { state: ReturnType<typeof useResource<Performance>>; selected: boolean }) {
  if (state.loading) return <ResourceLoading label="Calculating performance" />;
  if (state.error && selected) return <ResourceError message={state.error} retry={state.retry} />;
  return null;
}

function CompetitionPicker({ competitions, selectedID, setCompetitionID }: { competitions: Competition[]; selectedID: string; setCompetitionID: (value: string) => void }) {
  if (competitions.length === 0) return null;
  return <div className="filter-strip"><label>Competition<select value={selectedID} onChange={(event) => setCompetitionID(event.target.value)}>{competitions.map((item) => <option value={item.id} key={item.id}>{item.country} · {item.name}</option>)}</select></label></div>;
}

function PerformanceReport({ item, competition }: { item: Performance; competition?: Competition }) {
  const metrics = useMemo(() => [
    ["Outcome hit rate", item.outcome_hit_rate, true], ["Brier score", item.brier, false], ["Log loss", item.log_loss, false],
    ["Exact-score hit", item.exact_score_rate, true], ["Top-three score hit", item.top_three_score_rate, true], ["Top-five score hit", item.top_five_score_rate, true],
    ["Over/under 2.5 hit", item.total_goals_hit_rate, true], ["BTTS hit", item.btts_hit_rate, true],
  ] as const, [item]);
  return <>
    <div className="summary-grid"><Metric label="Rating" value={item.rating} rating={item.rating} /><Metric label="Settled forecasts" value={String(item.forecasts)} /><Metric label="Competition" value={competition?.name ?? item.competition_id} /><Metric label="Minimum sample" value="50" /></div>
    {item.rating === "UNRATED" && <div className="integrity-note"><b>UNRATED</b><span>{Math.max(0, 50 - item.forecasts)} more settled forecasts are required. The UI does not promote small-sample results.</span></div>}
    <section className="panel"><header><h4>All available chronological forecasts</h4><small>No post-result tuning</small></header><div className="summary-grid metric-grid">{metrics.map(([label, value, percentage]) => <Metric key={label} label={label} value={formatMetric(value, percentage)} />)}</div></section>
    <section className="panel"><header><h4>League baseline comparison</h4><small>Lower is better · prior-results baseline</small></header><div className="summary-grid metric-grid"><Metric label="MatchForge Brier" value={formatMetric(item.brier, false)} /><Metric label="Baseline Brier" value={formatMetric(item.baseline_brier, false)} /><Metric label="MatchForge log loss" value={formatMetric(item.log_loss, false)} /><Metric label="Baseline log loss" value={formatMetric(item.baseline_log_loss, false)} /></div></section>
    <section className="panel performance-note"><header><h4>Rating contract</h4></header><p>UNRATED means fewer than 50 settled forecasts. WATCH, GOOD, and STRONG are assigned only from the frozen league-comparison rule. These labels describe measured forecast performance, not betting advice.</p></section>
  </>;
}

function Metric({ label, value, rating }: { label: string; value: string; rating?: string }) { return <div className="metric"><small>{label}</small>{rating ? <span className={`rating ${rating.toLowerCase()}`}>{value}</span> : <b>{value}</b>}</div>; }
function formatMetric(value: number | null, percentage: boolean) { return value === null ? "—" : percentage ? `${(value * 100).toFixed(1)}%` : value.toFixed(3); }
function loadPerformance(competitionID: string, signal: AbortSignal) { return competitionID ? api.performance(competitionID, signal) : Promise.reject(new Error("Select a competition")); }
function activeCompetitionID(selected: string, competitions: Competition[] | null) { return selected || competitions?.[0]?.id || ""; }
