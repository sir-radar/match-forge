"use client";

import { useCallback, useState, type CSSProperties } from "react";
import { api } from "@/lib/api";
import type { Competition, ExternalPrediction, Fixture, Forecast, MatchContext } from "@/lib/contracts";
import { useResource } from "@/hooks/use-resource";
import { EmptyState, ResourceError, ResourceLoading } from "@/components/resource-state";
import { percent, ProbabilityBar } from "@/components/probability-bar";

const tabs = ["Overview", "Markets", "Score matrix", "H2H", "Team statistics", "Standings", "External predictions"] as const;
type Tab = (typeof tabs)[number];

export function ExpandedFixture({ fixture, competition }: { fixture: Fixture; competition: Competition }) {
  const [tab, setTab] = useState<Tab>("Overview");
  const contextLoad = useCallback((signal: AbortSignal) => api.context(fixture.id, signal), [fixture.id]);
  const context = useResource(`context-${fixture.id}`, contextLoad);
  const forecastLoad = useCallback((signal: AbortSignal) => fixture.forecast ? api.forecast(fixture.id, fixture.forecast.id, signal) : Promise.reject(new Error("Forecast unavailable")), [fixture.id, fixture.forecast]);
  const forecast = useResource(`forecast-${fixture.forecast?.id ?? "none"}`, forecastLoad);
  const predictionsLoad = useCallback((signal: AbortSignal) => api.predictions(new URLSearchParams({ fixture_id: fixture.id }), signal), [fixture.id]);
  const predictions = useResource(`predictions-${fixture.id}`, predictionsLoad);
  const resources = { context, forecast, predictions };

  return <div className="expanded-panel">
    <div className="match-identity">
      <div><small>{competition.name} · {fixture.round ?? "Current round"}</small><h3>{fixture.home.name} <span>vs</span> {fixture.away.name}</h3><p>{fixture.venue ?? "Venue unavailable"} · {formatDateTime(fixture.kickoff_at)}</p></div>
      <span className={`status-badge ${fixture.forecast ? "ok" : "muted"}`}>{fixture.forecast ? "Forecast available" : availabilityCopy(fixture.forecast_availability)}</span>
    </div>
    {fixture.forecast && <section className="forecast-hero" aria-label="MatchForge forecast">
      <div className="outcome-cards"><Metric label={`${fixture.home.name} win`} value={percent(fixture.forecast.probabilities.home)} tone="home" /><Metric label="Draw" value={percent(fixture.forecast.probabilities.draw)} /><Metric label={`${fixture.away.name} win`} value={percent(fixture.forecast.probabilities.away)} tone="away" /></div>
      <ProbabilityBar values={fixture.forecast.probabilities} />
      <div className="expected-goals"><span><small>{fixture.home.name} expected goals</small><b>{fixture.forecast.expected_home_goals.toFixed(2)}</b></span><span><small>{fixture.away.name} expected goals</small><b>{fixture.forecast.expected_away_goals.toFixed(2)}</b></span></div>
    </section>}
    <div className="tab-list" role="tablist" aria-label="Match analysis">
      {tabs.map((name) => <button key={name} role="tab" aria-selected={tab === name} aria-controls={`panel-${fixture.id}`} onClick={() => setTab(name)}>{name}</button>)}
    </div>
    <div id={`panel-${fixture.id}`} role="tabpanel" className="tab-panel">
      <TabContent tab={tab} fixture={fixture} resources={resources} />
      <AnalysisStatus tab={tab} hasForecast={fixture.forecast !== null} context={context} forecast={forecast} />
    </div>
    <div className="integrity-note"><b>Model boundary</b><span>H2H, form, standings, and external selections are context only. They do not change this stored forecast.</span></div>
  </div>;
}

type Resource<T> = { data: T | null; loading: boolean; error: string | null; retry: () => void };
type AnalysisResources = {
  context: Resource<MatchContext>;
  forecast: Resource<Forecast>;
  predictions: Resource<ExternalPrediction[]>;
};

function TabContent({ tab, fixture, resources }: { tab: Tab; fixture: Fixture; resources: AnalysisResources }) {
  switch (tab) {
    case "Overview": return <Overview fixture={fixture} forecast={resources.forecast.data} context={resources.context.data} />;
    case "Markets": return <Markets forecast={resources.forecast.data} />;
    case "Score matrix": return <ScoreMatrix forecast={resources.forecast.data} />;
    case "H2H": return <H2H fixture={fixture} context={resources.context.data} />;
    case "Team statistics": return <TeamStatistics fixture={fixture} context={resources.context.data} />;
    case "Standings": return <Standings context={resources.context.data} />;
    case "External predictions": return <ExternalPredictions state={resources.predictions} />;
  }
}

function AnalysisStatus({ tab, hasForecast, context, forecast }: { tab: Tab; hasForecast: boolean; context: Resource<MatchContext>; forecast: Resource<Forecast> }) {
  if (tab === "External predictions") return null;
  return <>
    {(context.loading || (hasForecast && forecast.loading)) && <ResourceLoading label="Loading match analysis" />}
    {context.error && <ResourceError message={context.error} retry={context.retry} />}
    {hasForecast && forecast.error && <ResourceError message={forecast.error} retry={forecast.retry} />}
  </>;
}

function Overview({ fixture, forecast, context }: { fixture: Fixture; forecast: Forecast | null; context: MatchContext | null }) {
  if (!fixture.forecast) return <EmptyState title={availabilityCopy(fixture.forecast_availability)} detail="Fixture remains visible. MatchForge does not fabricate probabilities when history or source data is insufficient." />;
  if (!forecast) return null;
  const likely = [...forecast.score_matrix].sort((a, b) => b.probability - a.probability).slice(0, 3);
  return <div className="overview-grid">
    <section className="panel"><header><h4>Top scoreline probabilities</h4><small>Exact joint distribution</small></header><div className="score-cards">{likely.map((cell, index) => <div key={`${cell.home_goals}-${cell.away_goals}`} className={index === 0 ? "modal" : ""}><b>{cell.home_goals}–{cell.away_goals}</b><strong>{percent(cell.probability)}</strong><small>{index === 0 ? "Most likely" : "Supporting outcome"}</small></div>)}</div></section>
    <section className="panel"><header><h4>Recent form</h4><small>Last five completed matches</small></header><TeamForm name={fixture.home.name} values={context?.home_form ?? []} /><TeamForm name={fixture.away.name} values={context?.away_form ?? []} /></section>
    <section className="panel provenance"><header><h4>Forecast record</h4><small>Immutable pre-match snapshot</small></header><dl><div><dt>Model</dt><dd>MatchForge Forecast</dd></div><div><dt>Algorithm</dt><dd>{forecast.model_algorithm_version}</dd></div><div><dt>Knowledge cutoff</dt><dd>{formatDateTime(forecast.knowledge_cutoff)}</dd></div><div><dt>Publication</dt><dd>Owner-authorized MVP</dd></div></dl></section>
  </div>;
}

function Markets({ forecast }: { forecast: Forecast | null }) {
  if (!forecast) return <EmptyState title="Markets unavailable" detail="No published MatchForge forecast exists for this fixture." />;
  const values = forecast.probabilities;
  return <div className="markets-grid">
    <section className="panel"><header><h4>Full-time result (1X2)</h4><small>MatchForge Forecast</small></header>{[["Home win", values.home, "home"], ["Draw", values.draw, "draw"], ["Away win", values.away, "away"]].map(([label, value, tone]) => <MarketBar key={String(label)} label={String(label)} value={Number(value)} tone={String(tone)} />)}</section>
    <section className="panel"><header><h4>Total goals</h4><small>2.5 line</small></header><MarketBar label="Over 2.5" value={values.total_over_2_5} tone="home" /><MarketBar label="Under 2.5" value={values.total_under_2_5} tone="away" /></section>
    <section className="panel"><header><h4>Both teams to score</h4><small>Derived jointly</small></header><MarketBar label="BTTS Yes" value={values.btts_yes} tone="home" /><MarketBar label="BTTS No" value={1 - values.btts_yes} tone="draw" /></section>
    <section className="panel"><header><h4>Clean sheets</h4><small>Zero conceded</small></header><Metric label="Home clean sheet" value={percent(values.home_clean_sheet)} tone="home" /><Metric label="Away clean sheet" value={percent(values.away_clean_sheet)} tone="away" /></section>
  </div>;
}

function ScoreMatrix({ forecast }: { forecast: Forecast | null }) {
  if (!forecast) return <EmptyState title="Score matrix unavailable" detail="No published score distribution exists for this fixture." />;
  const cells = forecast.score_matrix.filter((cell) => cell.home_goals <= 4 && cell.away_goals <= 4);
  const labels = [0, 1, 2, 3, 4];
  const top = Math.max(...cells.map((cell) => cell.probability));
  return <section className="panel matrix-panel"><header><h4>Exact-score joint probability matrix</h4><small>0–4 goals · higher intensity means greater probability</small></header><div className="matrix" role="table" aria-label="Exact score probabilities"><div /><div className="matrix-axis" style={{ gridColumn: "2 / span 5" }}>Away goals</div><div className="matrix-axis vertical">Home goals</div>{labels.map((away) => <div key={`head-${away}`} className="matrix-head">{away}</div>)}{labels.map((home) => <div key={`row-${home}`} className="matrix-row"><span className="matrix-head">{home}</span>{labels.map((away) => { const cell = cells.find((item) => item.home_goals === home && item.away_goals === away); return <div key={`${home}-${away}`} className="matrix-cell" style={{ "--heat": cell ? cell.probability / top : 0 } as CSSProperties}><small>{home}–{away}</small><b>{percent(cell?.probability)}</b></div>; })}</div>)}</div></section>;
}

function H2H({ fixture, context }: { fixture: Fixture; context: MatchContext | null }) {
  if (!context) return null;
  const summary = context.h2h_summary;
  return <section className="panel"><header><h4>Head-to-head context</h4><span className="status-badge muted">Display only · 0% model weight</span></header>{context.h2h.length === 0 ? <EmptyState title="Limited H2H history" detail="No matched meetings are available from the current qualified history." /> : <><div className="summary-grid metric-grid"><Metric label="Meetings" value={String(summary.meetings)} /><Metric label="Home-side wins" value={String(summary.home_wins)} tone="home" /><Metric label="Draws" value={String(summary.draws)} /><Metric label="Away-side wins" value={String(summary.away_wins)} tone="away" /><Metric label="Aggregate goals" value={`${summary.home_goals}–${summary.away_goals}`} /></div><div className="table-scroll"><table><thead><tr><th>Date</th><th>Home</th><th>Score</th><th>Away</th><th>xG</th></tr></thead><tbody>{context.h2h.map((match) => <tr key={`${match.kickoff_at}-${match.home_team}`}><td>{dateLabel(match.kickoff_at)}</td><td>{match.home_team}</td><td>{match.home_goals}–{match.away_goals}</td><td>{match.away_team}</td><td>{match.home_xg === null || match.away_xg === null ? "—" : `${match.home_xg.toFixed(2)}–${match.away_xg.toFixed(2)}`}</td></tr>)}</tbody></table></div></>}<p className="context-copy"><b>H2H is context only and does not alter MatchForge probabilities.</b> Previous meetings support human review only for {fixture.home.name} vs {fixture.away.name}.</p></section>;
}

function TeamStatistics({ fixture, context }: { fixture: Fixture; context: MatchContext | null }) {
  if (!context) return null;
  return <div className="team-stats-grid"><TeamStatCard name={fixture.home.name} form={context.home_form} stats={context.home_team_statistics} /><TeamStatCard name={fixture.away.name} form={context.away_form} stats={context.away_team_statistics} /></div>;
}

function Standings({ context }: { context: MatchContext | null }) {
  if (!context) return null;
  if (!context.standings.length) return <EmptyState title="Standings unavailable" detail="Fixture and forecast remain available; only the standings panel is affected." />;
  return <div className="table-scroll"><table><thead><tr><th>Pos</th><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th></tr></thead><tbody>{context.standings.map((row) => <tr key={row.team_id}><td>{row.position}</td><th scope="row">{row.team}</th><td>{row.played}</td><td>{row.won}</td><td>{row.drawn}</td><td>{row.lost}</td><td>{row.goals_for}</td><td>{row.goals_against}</td><td>{row.goal_difference}</td><td><b>{row.points}</b></td></tr>)}</tbody></table></div>;
}

function ExternalPredictions({ state }: { state: { data: ExternalPrediction[] | null; loading: boolean; error: string | null; retry: () => void } }) {
  if (state.loading) return <ResourceLoading label="Loading external predictions" />;
  if (state.error) return <ResourceError message={state.error} retry={state.retry} />;
  if (!state.data?.length) return <EmptyState title="No approved external selections" detail="Unapproved, paid, login-only, terms-restricted, or anti-bot sources are not collected." />;
  return <div className="table-scroll"><table><thead><tr><th>Source</th><th>Selection</th><th>Date</th><th>MatchForge</th></tr></thead><tbody>{state.data.map((item) => <tr key={item.id}><td>{item.source}</td><td>{item.selection}</td><td>{item.prediction_date}</td><td><Agreement value={item.agreement} /></td></tr>)}</tbody></table></div>;
}

function Agreement({ value }: { value: string }) { return <span className={`agreement ${value.toLowerCase()}`}>{value === "AGREES" ? "✓ MatchForge agrees" : value === "WEAK_SUPPORT" ? "~ Weak support" : value === "DISAGREES" ? "MatchForge disagrees" : "Unable to evaluate"}</span>; }
function Metric({ label, value, tone = "draw" }: { label: string; value: string; tone?: string }) { return <div className={`metric ${tone}`}><small>{label}</small><b>{value}</b></div>; }
function MarketBar({ label, value, tone }: { label: string; value: number; tone: string }) { return <div className="market-bar"><div><span>{label}</span><b>{percent(value)}</b></div><i><span className={tone} style={{ width: `${value * 100}%` }} /></i></div>; }
function TeamForm({ name, values }: { name: string; values: MatchContext["home_form"] }) { return <div className="team-form"><span>{name}</span><div>{values.length ? values.map((match) => <b key={`${match.kickoff_at}-${match.opponent}`} className={match.result}>{match.result}</b>) : <small>No form data</small>}</div></div>; }
function TeamStatCard({ name, form, stats }: { name: string; form: MatchContext["home_form"]; stats: MatchContext["home_team_statistics"] }) { return <section className="panel team-stat"><header><h4>{name}</h4><TeamForm name="Recent form" values={form} /></header>{stats ? <div className="stat-pair"><Metric label={`Goals scored (${stats.recent_matches})`} value={String(stats.goals_for)} tone="home" /><Metric label={`Goals conceded (${stats.recent_matches})`} value={String(stats.goals_against)} tone="away" /><Metric label="Average goals scored" value={stats.average_goals_for.toFixed(2)} tone="home" /><Metric label="Average goals conceded" value={stats.average_goals_against.toFixed(2)} tone="away" /></div> : <EmptyState title="Team statistics unavailable" detail="No qualified completed-match sample is stored for this team." />}<div className="unavailable-block"><b>Advanced team metrics unavailable</b><span>xG, field tilt, lineup, and player availability are shown only when a qualified source provides them.</span></div></section>; }
function dateLabel(value: string) { return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(value)); }
function formatDateTime(value: string) { return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(value)); }
function availabilityCopy(value: string) { return value === "NOT_ENOUGH_HISTORY" ? "Not enough qualified match history" : value === "SOURCE_DATA_INCOMPLETE" ? "Source data incomplete" : value === "TEMPORARILY_UNAVAILABLE" ? "Forecast temporarily unavailable" : "Forecast unavailable"; }
