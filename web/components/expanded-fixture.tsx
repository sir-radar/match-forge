"use client";

import { useCallback, useEffect, useState, useId, useRef, type KeyboardEvent, type CSSProperties, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { Competition, Fixture, Forecast, LiveMatch, MatchContext, ScoreCell } from "@/lib/contracts";
import { useResource } from "@/hooks/use-resource";
import { EmptyState, ResourceError, ResourceLoading } from "@/components/resource-state";
import { percent, ProbabilityBar } from "@/components/probability-bar";
import { ForecastHistory } from "@/components/forecast-history";
import { Icon } from "@/components/icon";

const tabs = ["Live Match", "Overview", "Markets", "Score matrix", "H2H context", "Team statistics", "Simulation evidence", "Diagnostics", "Forecast history"] as const;
type Tab = (typeof tabs)[number];

export function ExpandedFixture({ fixture, competition }: { fixture: Fixture; competition: Competition }) {
  const resources = useMatchAnalysisResources(fixture);

  return <div className="expanded-panel">
    <div className="match-identity">
      <div><small>{competition.name} · {fixture.round ?? "Current round"}</small><h3>{fixture.home.name} <span>vs</span> {fixture.away.name}</h3><p>{fixture.venue ?? "Venue unavailable"} · {formatDateTime(fixture.kickoff_at)}</p>{fixture.provider && <p className="provider-observation">{fixture.provider} · {fixture.stale ? "stale" : "fresh"}{fixture.last_successful_update ? ` · updated ${formatDateTime(fixture.last_successful_update)}` : ""}</p>}</div>
      <span className={`status-badge ${fixture.forecast ? "ok" : "muted"}`}>{fixture.forecast ? "Pre-match forecast" : availabilityCopy(fixture.forecast_availability)}</span>
    </div>
    {fixture.forecast && <section className="forecast-hero" aria-label="MatchForge forecast">
      <div className="outcome-cards"><Metric label={`${fixture.home.name} win`} value={percent(fixture.forecast.probabilities.home)} tone="home" /><Metric label="Draw" value={percent(fixture.forecast.probabilities.draw)} /><Metric label={`${fixture.away.name} win`} value={percent(fixture.forecast.probabilities.away)} tone="away" /></div>
      <ProbabilityBar values={fixture.forecast.probabilities} />
      <div className="expected-goals"><span><small>{fixture.home.name} expected goals</small><b>{fixture.forecast.expected_home_goals.toFixed(2)}</b></span><span><small>{fixture.away.name} expected goals</small><b>{fixture.forecast.expected_away_goals.toFixed(2)}</b></span></div>
    </section>}
    <MatchAnalysisTabs fixture={fixture} resources={resources} />
    <div className="integrity-note"><Icon name="verified" /><b>Model boundary</b><span>H2H, form, standings, and external selections are context only. They do not change this stored forecast.</span></div>
  </div>;
}

type Resource<T> = { data: T | null; loading: boolean; error: string | null; retry: () => void };
type AnalysisResources = {
  context: Resource<MatchContext>;
  forecast: Resource<Forecast>;
  live: Resource<LiveMatch>;
};

function useMatchAnalysisResources(fixture: Fixture): AnalysisResources {
  const contextLoad = useCallback((signal: AbortSignal) => api.context(fixture.id, signal), [fixture.id]);
  const context = useResource(`context-${fixture.id}`, contextLoad);
  const forecastId = fixture.forecast?.id ?? null;
  const forecastLoad = useCallback((signal: AbortSignal) => forecastId ? api.forecast(fixture.id, forecastId, signal) : Promise.reject(new Error("Forecast unavailable")), [fixture.id, forecastId]);
  const forecast = useResource(`forecast-${fixture.id}-${forecastId ?? "none"}`, forecastLoad);
  const liveLoad = useCallback((signal: AbortSignal) => api.live(fixture.id, signal), [fixture.id]);
  const live = useResource(`live-${fixture.id}`, liveLoad);
  const retryLive = live.retry;
  useEffect(() => {
    if (!["SCHEDULED", "LIVE", "HALF_TIME", "INTERRUPTED", "SUSPENDED"].includes(fixture.status)) return;
    let timer = 0;
    const schedule = () => { timer = window.setTimeout(() => { retryLive(); schedule(); }, document.hidden ? 120_000 : 45_000); };
    const visible = () => { window.clearTimeout(timer); if (!document.hidden) retryLive(); schedule(); };
    schedule();
    document.addEventListener("visibilitychange", visible);
    return () => { window.clearTimeout(timer); document.removeEventListener("visibilitychange", visible); };
  }, [fixture.status, retryLive]);
  return { context, forecast, live };

}

function MatchAnalysisTabs({ fixture, resources }: { fixture: Fixture; resources: AnalysisResources }) {
  const [tab, setTab] = useState<Tab>(["LIVE", "HALF_TIME", "INTERRUPTED", "SUSPENDED"].includes(fixture.status) ? "Live Match" : "Overview");
  const tabsId = useId();
  const tabButtons = useRef<(HTMLButtonElement | null)[]>([]);
  const navigateTabs = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const target = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : null;
    if (target === null) return; event.preventDefault(); setTab(tabs[target]); tabButtons.current[target]?.focus();
  };
  const { context, forecast, live } = resources;
  return <>
    <div className="tab-list" role="tablist" aria-label="Match analysis">
      {tabs.map((name, index) => <button key={name} ref={(node) => { tabButtons.current[index] = node; }} id={`${tabsId}-tab-${index}`} role="tab" tabIndex={tab === name ? 0 : -1} aria-selected={tab === name} aria-controls={`${tabsId}-panel-${index}`} onKeyDown={(event) => navigateTabs(event, index)} onClick={() => setTab(name)}>{name}</button>)}
    </div>
    {tabs.map((name, index) => <div key={name} id={`${tabsId}-panel-${index}`} role="tabpanel" aria-labelledby={`${tabsId}-tab-${index}`} tabIndex={0} hidden={tab !== name} className="tab-panel">
      {tab === name && <>
      <TabContent tab={tab} fixture={fixture} resources={resources} />
      {tab === "Live Match" && live.error && <ResourceError message={live.error} retry={live.retry} />}
      <AnalysisStatus tab={tab} hasForecast={fixture.forecast !== null} context={context} forecast={forecast} />
      </>}
    </div>)}
  </>;
}

function TabContent({ tab, fixture, resources }: { tab: Tab; fixture: Fixture; resources: AnalysisResources }) {
  const content: Record<Tab, ReactNode> = {
    "Live Match": resources.live.error && resources.live.data === null ? null : <LiveMatchPanel fixture={fixture} live={resources.live.data} />,
    "Overview": <Overview fixture={fixture} forecast={resources.forecast.data} context={resources.context.data} />,
    "Markets": <Markets forecast={resources.forecast.data} />,
    "Score matrix": <ScoreMatrix forecast={resources.forecast.data} />,
    "H2H context": <H2H fixture={fixture} context={resources.context.data} />,
    "Team statistics": <TeamStatistics fixture={fixture} context={resources.context.data} />,
    "Simulation evidence": <UnavailablePanel title="Simulation validation unavailable" detail="The public MVP forecast API does not expose a linked simulation-validation artifact. No validation result is inferred from forecast availability." />,
    "Diagnostics": <UnavailablePanel title="Research diagnostics restricted" detail="Diagnostics remain research-only and are not exposed by the public MVP API." />,
    "Forecast history": <ForecastHistory key={fixture.id} fixtureId={fixture.id} currentId={fixture.forecast?.id ?? null} />,
  };
  return content[tab];
}

function AnalysisStatus({ tab, hasForecast, context, forecast }: { tab: Tab; hasForecast: boolean; context: Resource<MatchContext>; forecast: Resource<Forecast> }) {
  if (tab === "Live Match") return null;
  if (["Simulation evidence", "Diagnostics", "Forecast history"].includes(tab)) return null;
  return <>
    {(context.loading || (hasForecast && forecast.loading)) && <ResourceLoading label="Loading match analysis" />}
    {context.error && <ResourceError message={context.error} retry={context.retry} />}
    {hasForecast && forecast.error && <ResourceError message={forecast.error} retry={forecast.retry} />}
  </>;
}

function LiveMatchPanel({ fixture, live }: { fixture: Fixture; live: LiveMatch | null }) {
  if (!live) return <ResourceLoading label="Loading live match" />;
  const score = live.home_score === null || live.away_score === null ? "Score unavailable" : `${live.home_score}–${live.away_score}`;
  const clock = live.status === "HALF_TIME" ? "HT" : live.status === "FINISHED" ? "FT" : live.match_minute === null ? live.status : `${live.match_minute}${live.added_time ? `+${live.added_time}` : ""}′`;
  const homeGoals = live.events.filter((event) => event.type === "GOAL" && !event.disallowed && event.team_side === "HOME");
  const awayGoals = live.events.filter((event) => event.type === "GOAL" && !event.disallowed && event.team_side === "AWAY");
  const fullMatch = live.statistics.filter((stat) => stat.period === "FULL_MATCH");
  return <div className="live-match-grid">
    <section className="panel live-score-panel"><header><h4>Live score</h4><span className={`status-badge ${live.status === "LIVE" ? "live" : "muted"}`}>{clock}</span></header><div className="live-score"><span>{live.home.name}</span><b>{score}</b><span>{live.away.name}</span></div><div className="live-scorers"><GoalList name={live.home.name} goals={homeGoals} /><GoalList name={live.away.name} goals={awayGoals} /></div></section>
    <section className="panel"><header><h4>Match incidents</h4><small>Chronological provider events</small></header>{live.events.length ? <ol className="incident-list">{[...live.events].sort(eventOrder).map((event) => <li key={event.id}><time>{event.minute === null ? "—" : `${event.minute}${event.added_time ? `+${event.added_time}` : ""}′`}</time><b>{eventLabel(event.type)}</b><span>{event.player_name ?? "Player unavailable"}{event.penalty ? " · penalty" : ""}{event.own_goal ? " · own goal" : ""}{event.disallowed ? " · disallowed" : ""}</span></li>)}</ol> : <EmptyState title="Incidents unavailable" detail="The provider has not supplied a verified incident feed for this match." />}</section>
    <section className="panel live-stats"><header><h4>Current match statistics</h4><small>Provider-reported · not model λ</small></header>{fullMatch.length ? fullMatch.map((stat) => <LiveStat key={`${stat.period}-${stat.metric}`} label={stat.label} home={stat.home} away={stat.away} unit={stat.unit} />) : <EmptyState title="Statistics unavailable" detail="No current match-statistics resource is available. Missing values are not treated as zero." />}</section>
    <section className="panel provenance"><header><h4>Live data provenance</h4><small>{live.partial ? "Partial coverage" : "Complete available coverage"}</small></header><dl><div><dt>Score</dt><dd>{sourceLabel(live.score_source)}</dd></div><div><dt>Events</dt><dd>{sourceLabel(live.event_source)}</dd></div><div><dt>Statistics</dt><dd>{sourceLabel(live.statistics_source)}</dd></div><div><dt>Fixture</dt><dd>{fixture.id}</dd></div></dl></section>
  </div>;
}

function GoalList({ name, goals }: { name: string; goals: LiveMatch["events"] }) {
  return <div><b>{name}</b>{goals.length ? goals.map((event) => <span key={event.id}>{event.player_name ?? "Scorer unavailable"} {event.minute === null ? "" : `${event.minute}${event.added_time ? `+${event.added_time}` : ""}′`}{event.penalty ? " (pen)" : ""}{event.own_goal ? " (OG)" : ""}</span>) : <small>No verified scorers</small>}</div>;
}

function LiveStat({ label, home, away, unit }: { label: string; home: number | null; away: number | null; unit: string }) {
  const total = Math.max((home ?? 0) + (away ?? 0), 1);
  const suffix = unit === "percent" ? "%" : "";
  return <div className="live-stat"><div><b>{home === null ? "—" : `${home}${suffix}`}</b><span>{label}</span><b>{away === null ? "—" : `${away}${suffix}`}</b></div><i><span style={{ width: `${home === null ? 0 : home / total * 100}%` }} /><span style={{ width: `${away === null ? 0 : away / total * 100}%` }} /></i></div>;
}

function eventOrder(left: LiveMatch["events"][number], right: LiveMatch["events"][number]) { return (left.minute ?? 999) - (right.minute ?? 999) || (left.added_time ?? 0) - (right.added_time ?? 0); }
function eventLabel(value: string) { return value.replaceAll("_", " ").toLocaleLowerCase(); }
function sourceLabel(source: LiveMatch["score_source"]) { return source ? `${source.provider} · ${source.stale ? "stale" : "fresh"} · fetched ${formatDateTime(source.last_fetched_at)}` : "Unavailable"; }

function Overview({ fixture, forecast, context }: { fixture: Fixture; forecast: Forecast | null; context: MatchContext | null }) {
  if (!fixture.forecast) return <EmptyState title={availabilityCopy(fixture.forecast_availability)} detail="Fixture remains visible. MatchForge does not fabricate probabilities when history or source data is insufficient." />;
  if (!forecast) return null;
  const likely = [...forecast.score_matrix].sort((a, b) => b.probability - a.probability).slice(0, 3);
  return <div className="overview-grid">
    <MatchInterpretation fixture={fixture} forecast={forecast} />
    <section className="panel"><header><h4>Top scoreline densities</h4><small>Exact scores and aggregate categories</small></header><div className="score-cards">{likely.map((cell, index) => <div key={scoreLabel(cell)} className={index === 0 ? "modal" : ""}><b>{scoreLabel(cell)}</b><strong>{percent(cell.probability)}</strong><small>{isExactScore(cell) ? index === 0 ? "Modal score" : "Supporting outcome" : "Aggregate score category"}</small></div>)}</div></section>
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
  const cells = forecast.score_matrix.filter((cell) => isExactScore(cell) && cell.home_goals <= 3 && cell.away_goals <= 3);
  if (!cells.length) return <EmptyState title="Score matrix unavailable" detail="The published forecast contains no displayable 0–3 exact-score cells." />;
  const labels = [0, 1, 2, 3];
  const likely = [...forecast.score_matrix].sort((a, b) => b.probability - a.probability).slice(0, 5);
  return <div className="matrix-layout"><section className="panel matrix-panel"><header><h4>Exact-score full-time joint probability matrix</h4><small>0–3 goals · fixed intensity scale: 0–20%</small></header><div className="matrix" role="table" aria-label="Exact score probabilities"><div /><div className="matrix-axis" style={{ gridColumn: "2 / span 4" }}>Away goals</div><div className="matrix-axis vertical">Home goals</div>{labels.map((away) => <div key={`head-${away}`} className="matrix-head">{away} {away === 1 ? "goal" : "goals"}</div>)}{labels.map((home) => <div key={`row-${home}`} className="matrix-row"><span className="matrix-head">{home}</span>{labels.map((away) => { const cell = cells.find((item) => item.home_goals === home && item.away_goals === away); return <div key={`${home}-${away}`} className="matrix-cell" style={{ "--heat": cell ? Math.min(cell.probability / 0.2, 1) : 0 } as CSSProperties}><small>{home}–{away}</small><b>{percent(cell?.probability)}</b></div>; })}</div>)}</div></section><section className="panel density-list"><header><h4>Top 5 probability densities</h4><small>Exact scores and aggregate categories</small></header>{likely.map((cell, index) => <div key={scoreLabel(cell)}><span>{index + 1}</span><b>{scoreLabel(cell)}</b><strong>{percent(cell.probability)}</strong></div>)}</section></div>;
}

function isExactScore(cell: ScoreCell): boolean {
  return cell.home_bucket_kind === "EXACT" && cell.away_bucket_kind === "EXACT";
}

function scoreLabel(cell: ScoreCell): string {
  return `${cell.home_label}–${cell.away_label}`;
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
      {modalScore && <p>Most likely {isExactScore(modalScore) ? "exact score" : "score category"} is <b>{scoreLabel(modalScore)}</b> at {percent(modalScore.probability)}. {isExactScore(modalScore) ? "Exact scores remain low-probability outcomes even when ranked first." : "A category with + combines several possible final scores."}</p>}
    </div>
    <dl className="stat-glossary">
      <div><dt>Win %</dt><dd>Share of the model distribution assigned to each full-time result.</dd></div>
      <div><dt>Expected goals (λ)</dt><dd>Average goals under this fitted model, not a predicted final score.</dd></div>
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
