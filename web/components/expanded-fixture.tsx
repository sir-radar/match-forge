"use client";

import { useCallback, useState, type CSSProperties } from "react";
import { api } from "@/lib/api";
import type { Competition, Fixture, Forecast, MatchContext } from "@/lib/contracts";
import { useResource } from "@/hooks/use-resource";
import { EmptyState, ResourceError, ResourceLoading } from "@/components/resource-state";
import { percent, ProbabilityBar } from "@/components/probability-bar";
import { Icon } from "@/components/icon";

const tabs = ["Overview", "Markets", "Score matrix", "H2H context", "Team statistics", "Simulation evidence", "Diagnostics", "Forecast history"] as const;
type Tab = (typeof tabs)[number];

export function ExpandedFixture({ fixture, competition }: { fixture: Fixture; competition: Competition }) {
  const [tab, setTab] = useState<Tab>("Overview");
  const contextLoad = useCallback((signal: AbortSignal) => api.context(fixture.id, signal), [fixture.id]);
  const context = useResource(`context-${fixture.id}`, contextLoad);
  const forecastLoad = useCallback((signal: AbortSignal) => fixture.forecast ? api.forecast(fixture.id, fixture.forecast.id, signal) : Promise.reject(new Error("Forecast unavailable")), [fixture.id, fixture.forecast]);
  const forecast = useResource(`forecast-${fixture.forecast?.id ?? "none"}`, forecastLoad);
  const resources = { context, forecast };

  return <div className="expanded-panel">
    <div className="match-identity">
      <div><small>{competition.name} · {fixture.round ?? "Current round"}</small><h3>{fixture.home.name} <span>vs</span> {fixture.away.name}</h3><p>{fixture.venue ?? "Venue unavailable"} · {formatDateTime(fixture.kickoff_at)}</p></div>
      <span className={`status-badge ${fixture.forecast ? "ok" : "muted"}`}>{fixture.forecast ? "Pre-match forecast" : availabilityCopy(fixture.forecast_availability)}</span>
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
    <div className="integrity-note"><Icon name="verified" /><b>Model boundary</b><span>H2H, form, standings, and external selections are context only. They do not change this stored forecast.</span></div>
  </div>;
}

type Resource<T> = { data: T | null; loading: boolean; error: string | null; retry: () => void };
type AnalysisResources = {
  context: Resource<MatchContext>;
  forecast: Resource<Forecast>;
};

function TabContent({ tab, fixture, resources }: { tab: Tab; fixture: Fixture; resources: AnalysisResources }) {
  switch (tab) {
    case "Overview": return <Overview fixture={fixture} forecast={resources.forecast.data} context={resources.context.data} />;
    case "Markets": return <Markets forecast={resources.forecast.data} />;
    case "Score matrix": return <ScoreMatrix forecast={resources.forecast.data} />;
    case "H2H context": return <H2H fixture={fixture} context={resources.context.data} />;
    case "Team statistics": return <TeamStatistics fixture={fixture} context={resources.context.data} />;
    case "Simulation evidence": return <UnavailablePanel title="Simulation validation unavailable" detail="The public MVP forecast API does not expose a linked simulation-validation artifact. No validation result is inferred from forecast availability." />;
    case "Diagnostics": return <UnavailablePanel title="Research diagnostics restricted" detail="Diagnostics remain research-only and are not exposed by the public MVP API." />;
    case "Forecast history": return <UnavailablePanel title="Forecast history unavailable" detail="The public MVP API exposes the selected immutable forecast, but does not expose its prior published revisions." />;
  }
}

function AnalysisStatus({ tab, hasForecast, context, forecast }: { tab: Tab; hasForecast: boolean; context: Resource<MatchContext>; forecast: Resource<Forecast> }) {
  if (["Simulation evidence", "Diagnostics", "Forecast history"].includes(tab)) return null;
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
    <MatchInterpretation fixture={fixture} forecast={forecast} />
    <section className="panel"><header><h4>Top scoreline densities</h4><small>Exact probabilities</small></header><div className="score-cards">{likely.map((cell, index) => <div key={`${cell.home_goals}-${cell.away_goals}`} className={index === 0 ? "modal" : ""}><b>{cell.home_goals}–{cell.away_goals}</b><strong>{percent(cell.probability)}</strong><small>{index === 0 ? "Modal score" : "Supporting outcome"}</small></div>)}</div></section>
    <section className="panel"><header><h4>Recent form</h4><small>Qualified completed matches</small></header><TeamForm name={fixture.home.name} values={context?.home_form ?? []} /><TeamForm name={fixture.away.name} values={context?.away_form ?? []} /></section>
    <section className="panel provenance"><header><h4>Forecast record</h4><small>Immutable pre-match snapshot</small></header><dl><div><dt>Model</dt><dd>MatchForge Forecast</dd></div><div><dt>Algorithm</dt><dd>{forecast.model_algorithm_version}</dd></div><div><dt>Knowledge cutoff</dt><dd>{formatDateTime(forecast.knowledge_cutoff)}</dd></div><div><dt>Publication</dt><dd>Owner-authorized MVP</dd></div></dl></section>
  </div>;
}

function Markets({ forecast }: { forecast: Forecast | null }) {
  if (!forecast) return <EmptyState title="Markets unavailable" detail="No published MatchForge forecast exists for this fixture." />;
  const values = forecast.probabilities;
  return <div className="markets-grid">
    <section className="panel market-primary"><header><h4>Full-time result (1X2) — probabilistic forecast</h4><small>{forecast.model_algorithm_version}</small></header>{[["Home win", values.home, "home"], ["Draw", values.draw, "draw"], ["Away win", values.away, "away"]].map(([label, value, tone]) => <MarketBar key={String(label)} label={String(label)} value={Number(value)} tone={String(tone)} />)}</section>
    <section className="panel"><header><h4>Expected goals</h4><small>Poisson λ targets</small></header><div className="stat-pair"><Metric label="Home λ" value={forecast.expected_home_goals.toFixed(2)} tone="home" /><Metric label="Away λ" value={forecast.expected_away_goals.toFixed(2)} tone="away" /></div></section>
    <section className="panel"><header><h4>Total goals over / under</h4><small>2.5 benchmark</small></header><MarketBar label="Over 2.5" value={values.total_over_2_5} tone="home" /><MarketBar label="Under 2.5" value={values.total_under_2_5} tone="away" /></section>
    <section className="panel"><header><h4>Both teams to score</h4><small>Derived jointly</small></header><MarketBar label="BTTS Yes" value={values.btts_yes} tone="home" /><MarketBar label="BTTS No" value={Number.isFinite(values.btts_yes) ? 1 - values.btts_yes : undefined} tone="draw" /></section>
    <section className="panel"><header><h4>Clean sheets</h4><small>Zero conceded</small></header><div className="stat-pair"><Metric label="Home clean sheet" value={percent(values.home_clean_sheet)} tone="home" /><Metric label="Away clean sheet" value={percent(values.away_clean_sheet)} tone="away" /></div></section>
    <section className="panel unavailable-registry"><header><h4>Unsupported / pending</h4><small>Public contract boundary</small></header><p>Corners, cards, half-time results, and other absent markets are not fabricated.</p></section>
  </div>;
}

function ScoreMatrix({ forecast }: { forecast: Forecast | null }) {
  if (!forecast) return <EmptyState title="Score matrix unavailable" detail="No published score distribution exists for this fixture." />;
  const cells = forecast.score_matrix.filter((cell) => cell.home_goals <= 3 && cell.away_goals <= 3);
  if (!cells.length) return <EmptyState title="Score matrix unavailable" detail="The published forecast contains no displayable 0–3 exact-score cells." />;
  const labels = [0, 1, 2, 3];
  const likely = [...forecast.score_matrix].sort((a, b) => b.probability - a.probability).slice(0, 5);
  return <div className="matrix-layout"><section className="panel matrix-panel"><header><h4>Exact-score full-time joint probability matrix</h4><small>0–3 goals · fixed intensity scale: 0–20%</small></header><div className="matrix" role="table" aria-label="Exact score probabilities"><div /><div className="matrix-axis" style={{ gridColumn: "2 / span 4" }}>Away goals</div><div className="matrix-axis vertical">Home goals</div>{labels.map((away) => <div key={`head-${away}`} className="matrix-head">{away} {away === 1 ? "goal" : "goals"}</div>)}{labels.map((home) => <div key={`row-${home}`} className="matrix-row"><span className="matrix-head">{home}</span>{labels.map((away) => { const cell = cells.find((item) => item.home_goals === home && item.away_goals === away); return <div key={`${home}-${away}`} className="matrix-cell" style={{ "--heat": cell ? Math.min(cell.probability / 0.2, 1) : 0 } as CSSProperties}><small>{home}–{away}</small><b>{percent(cell?.probability)}</b></div>; })}</div>)}</div></section><section className="panel density-list"><header><h4>Top 5 probability densities</h4><small>Exact scores</small></header>{likely.map((cell, index) => <div key={`${cell.home_goals}-${cell.away_goals}`}><span>{index + 1}</span><b>{cell.home_goals}–{cell.away_goals}</b><strong>{percent(cell.probability)}</strong></div>)}</section></div>;
}

function MatchInterpretation({ fixture, forecast }: { fixture: Fixture; forecast: Forecast }) {
  const outcomes = [
    { label: `${fixture.home.name} win`, probability: forecast.probabilities.home },
    { label: "Draw", probability: forecast.probabilities.draw },
    { label: `${fixture.away.name} win`, probability: forecast.probabilities.away },
  ].sort((left, right) => right.probability - left.probability);
  const favorite = outcomes[0];
  const runnerUp = outcomes[1];
  const lead = favorite.probability - runnerUp.probability;
  const edge = edgeLabel(lead);
  const totalExpectedGoals = forecast.expected_home_goals + forecast.expected_away_goals;
  const over = forecast.probabilities.total_over_2_5;
  const btts = forecast.probabilities.btts_yes;
  const modalScore = [...forecast.score_matrix].sort((left, right) => right.probability - left.probability)[0];
  const goalReading = goalTotalReading(over);
  return <section className="panel interpretation-panel">
    <header><h4>MatchForge interpretation</h4><small>Plain-language model reading</small></header>
    <div className="interpretation-copy">
      <p><b>{favorite.label} is the single most likely result at {percent(favorite.probability)}.</b> It leads {runnerUp.label.toLowerCase()} by {(lead * 100).toFixed(1)} percentage points, a {edge} edge rather than a certain result.</p>
      <p>Combined expected goals are <b>{totalExpectedGoals.toFixed(2)}</b>. {goalReading}{Number.isFinite(btts) ? ` Both teams scoring is ${btts >= 0.5 ? "more" : "less"} likely than not at ${percent(btts)}.` : ""}</p>
      {modalScore && <p>Most likely exact score is <b>{modalScore.home_goals}–{modalScore.away_goals}</b> at {percent(modalScore.probability)}. Exact scores remain low-probability outcomes even when ranked first.</p>}
    </div>
    <dl className="stat-glossary">
      <div><dt>Win %</dt><dd>Share of the model distribution assigned to each full-time result.</dd></div>
      <div><dt>Expected goals (λ)</dt><dd>Average goals implied by repeated model simulations, not a predicted final score.</dd></div>
      <div><dt>Score matrix</dt><dd>Probability of each exact home–away score combination; all cells form one distribution.</dd></div>
    </dl>
  </section>;
}

function edgeLabel(lead: number) {
  if (lead < 0.05) return "very narrow";
  if (lead < 0.1) return "narrow";
  if (lead < 0.2) return "moderate";
  return "clear";
}

function goalTotalReading(over: number) {
  if (!Number.isFinite(over)) return "The published forecast does not include an over/under split.";
  if (over >= 0.6) return `Over 2.5 goals is favored at ${percent(over)}, pointing to a higher-scoring game.`;
  if (over <= 0.4) return `Under 2.5 goals is favored at ${percent(1 - over)}, pointing to a lower-scoring game.`;
  return `Over 2.5 goals is ${percent(over)}, so there is no strong high- or low-scoring lean.`;
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

function UnavailablePanel({ title, detail }: { title: string; detail: string }) {
  return <section className="panel unavailable-panel"><header><h4>{title}</h4><span className="status-badge muted">Unavailable</span></header><p>{detail}</p></section>;
}

function Metric({ label, value, tone = "draw" }: { label: string; value: string; tone?: string }) { return <div className={`metric ${tone}`}><small>{label}</small><b>{value}</b></div>; }
function MarketBar({ label, value, tone }: { label: string; value: number | undefined; tone: string }) { const valid = value !== undefined && Number.isFinite(value) && value >= 0 && value <= 1; return <div className="market-bar"><div><span>{label}</span><b>{valid ? percent(value) : "Unavailable"}</b></div><i><span className={tone} style={{ width: valid ? `${value * 100}%` : "0%" }} /></i></div>; }
function TeamForm({ name, values }: { name: string; values: MatchContext["home_form"] }) { return <div className="team-form"><span>{name}</span><div>{values.length ? values.map((match, index) => <b key={formMatchKey(match, index)} className={match.result}>{match.result}</b>) : <small>No form data</small>}</div></div>; }
function formMatchKey(match: MatchContext["home_form"][number], index: number) { return [match.kickoff_at, match.opponent, match.venue, match.goals_for, match.goals_against, match.result, index].join("|"); }
function TeamStatCard({ name, form, stats }: { name: string; form: MatchContext["home_form"]; stats: MatchContext["home_team_statistics"] }) { return <section className="panel team-stat"><header><h4>{name}</h4><TeamForm name="Recent form" values={form} /></header>{stats ? <div className="stat-pair"><Metric label={`Goals scored (${stats.recent_matches})`} value={String(stats.goals_for)} tone="home" /><Metric label={`Goals conceded (${stats.recent_matches})`} value={String(stats.goals_against)} tone="away" /><Metric label="Average goals scored" value={stats.average_goals_for.toFixed(2)} tone="home" /><Metric label="Average goals conceded" value={stats.average_goals_against.toFixed(2)} tone="away" /></div> : <EmptyState title="Team statistics unavailable" detail="No qualified completed-match sample is stored for this team." />}<div className="unavailable-block"><b>Advanced team metrics unavailable</b><span>xG, field tilt, lineup, and player availability are shown only when a qualified source provides them.</span></div></section>; }
function dateLabel(value: string) { return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(value)); }
function formatDateTime(value: string) { return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(value)); }
function availabilityCopy(value: string) { return value === "NOT_ENOUGH_HISTORY" ? "Not enough qualified match history" : value === "SOURCE_DATA_INCOMPLETE" ? "Source data incomplete" : value === "TEMPORARILY_UNAVAILABLE" ? "Forecast temporarily unavailable" : "Forecast unavailable"; }
