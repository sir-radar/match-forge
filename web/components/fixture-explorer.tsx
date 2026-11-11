"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Competition, Fixture, FixtureGroup } from "@/lib/contracts";
import { useResource } from "@/hooks/use-resource";
import { EmptyState, ResourceError, ResourceLoading } from "@/components/resource-state";
import { ProbabilityBar } from "@/components/probability-bar";
import { ExpandedFixture } from "@/components/expanded-fixture";
import { DISPLAY_TIME_ZONE, dayLabel, validDay } from "@/lib/display-date";
import { Icon } from "@/components/icon";
import { DEFAULT_FIXTURE_FILTERS, filterFixtureGroups } from "@/lib/fixture-filters";
import { FixtureFilters } from "@/components/fixture-filters";

export function FixtureExplorer({ initialDate }: { initialDate: string }) {
  const [date, setDate] = useState(initialDate);
  const [dateError, setDateError] = useState<string | null>(null);
  const selectDate = (value: string) => { if (!validDay(value)) { setDateError("Choose a valid fixture date."); return; } setDateError(null); setDate(value); setExpanded(null); };
  const [filters, setFilters] = useState(DEFAULT_FIXTURE_FILTERS);
  const [expanded, setExpanded] = useState<string | null>(null);
  const competitionLoad = useCallback((signal: AbortSignal) => api.competitions(new URLSearchParams(), signal), []);
  const competitions = useResource("competitions", competitionLoad);
  const fixtureLoad = useCallback((signal: AbortSignal) => api.fixtures(new URLSearchParams({ date, timezone: DISPLAY_TIME_ZONE }), signal), [date]);
  const fixtures = useResource(date, fixtureLoad);
  useLiveRefresh(fixtures.data, fixtures.retry);
  const groups = useMemo(() => filterFixtureGroups(fixtures.data ?? [], filters), [fixtures.data, filters]);
  const statusGroups = useMemo(() => filterFixtureGroups(fixtures.data ?? [], { ...filters, status: "ALL" }), [fixtures.data, filters]);
  const reset = () => { setFilters(DEFAULT_FIXTURE_FILTERS); selectDate(initialDate); };

  const moveDate = (days: number) => {
    const next = new Date(`${date}T12:00:00Z`);
    next.setUTCDate(next.getUTCDate() + days);
    selectDate(next.toISOString().slice(0, 10));
  };

  return (
    <div className="workspace">
      <h1 className="sr-only">MatchForge fixtures</h1>
      <section className="fixture-workbench" aria-label="Football fixtures">
        <div className="environment-strip"><span>Environment: <b>Production pre-match</b></span><i /> <span>Forecasts: immutable published records</span></div>
        <FixtureToolbar date={date} count={fixtures.data === null ? "—" : fixtureCount(groups)} moveDate={moveDate} setDate={selectDate} />
        {dateError && <p role="alert">{dateError}</p>}
        <StatusFilters groups={statusGroups} value={filters.status} onChange={(status) => setFilters({ ...filters, status })} />
        <FixtureFilters filters={filters} setFilters={setFilters} competitions={competitions.data ?? []} reset={reset} />
        {competitions.error && <ResourceError message={`Competition filters unavailable: ${competitions.error}`} retry={competitions.retry} />}
        <FixtureCount groups={groups} state={fixtures} />
        <div className="engine-strip"><Icon name="monitoring" /><b>Probability engine</b><i>Real published MatchForge forecast data · no bookmaker odds</i></div>
        <FixtureResults state={fixtures} expanded={expanded} setExpanded={setExpanded} groups={groups} />
      </section>
    </div>
  );
}

function FixtureCount({ groups, state }: { groups: FixtureGroup[]; state: ReturnType<typeof useResource<FixtureGroup[]>> }) {
  const count = fixtureCount(groups);
  const label = state.data === null ? "Loading fixture count…" : `${count} matching ${count === 1 ? "fixture" : "fixtures"} of ${fixtureCount(state.data)}`;
  return <p className="fixture-count" role="status">{label}{state.refreshing && " · Refreshing…"}</p>;
}

function FixtureToolbar({ date, count, moveDate, setDate }: { date: string; count: number | string; moveDate: (days: number) => void; setDate: (value: string) => void }) {
  return <div className="fixture-toolbar">
    <div className="fixture-title"><Icon name="calendar" /><div><h2>Football Fixtures</h2><small>{count} matching fixtures · {dayLabel(date)}</small></div></div>
    <div className="date-bar">
      <button aria-label="Previous day" onClick={() => moveDate(-1)}><Icon name="chevron-left" /><span>Prev Day</span></button>
      <label><span>Selected date</span><input type="date" value={date} onChange={(event) => setDate(event.target.value)} /></label>
      <button aria-label="Next day" onClick={() => moveDate(1)}><span>Next Day</span><Icon name="chevron-right" /></button>
    </div>
  </div>;
}

function StatusFilters({ groups, value, onChange }: { groups: FixtureGroup[]; value: string; onChange: (value: string) => void }) {
  const fixtures = groups.flatMap((group) => group.fixtures);
  const active = (status: string) => ["LIVE", "HALF_TIME"].includes(status);
  const items = [["ALL", "All", fixtures.length], ["UPCOMING", "Upcoming", fixtures.filter((item) => ["SCHEDULED", "TIMED", "UPCOMING"].includes(item.status)).length], ["LIVE", "Live", fixtures.filter((item) => active(item.status)).length], ["FINISHED", "Finished", fixtures.filter((item) => item.status === "FINISHED").length]] as const;
  return <div className="status-filters" aria-label="Fixture status">{items.map(([key, label, count]) => <button key={key} aria-pressed={value === key} onClick={() => onChange(key)}>{label} <b>{count}</b></button>)}</div>;
}

function FixtureResults({ state, expanded, setExpanded, groups }: { state: ReturnType<typeof useResource<FixtureGroup[]>>; expanded: string | null; setExpanded: (id: string | null) => void; groups: FixtureGroup[] }) {
  if (state.loading) return <ResourceLoading label="Loading fixtures" />;
  if (state.error && state.data === null) return <ResourceError message={state.error} retry={state.retry} />;
  const refreshError = state.error && <ResourceError message={`Showing previously loaded fixtures. Refresh failed: ${state.error}`} retry={state.retry} />;
  if (!groups.length) return <>{refreshError}<EmptyState title="No fixtures found" detail="No fixtures match the selected date and filters. Lower the minimum probability, change the result or use Reset Filters." /></>;
  return <>
    {refreshError}
    {groups.map((group) => <FixtureGroupView key={group.competition.id} group={group} expanded={expanded} setExpanded={setExpanded} />)}
  </>;
}

function FixtureGroupView({ group, expanded, setExpanded }: { group: FixtureGroup; expanded: string | null; setExpanded: (id: string | null) => void }) {
  return <section className="fixture-group" aria-labelledby={`competition-${group.competition.id}`}>
    <header><div><span className="competition-mark" aria-hidden="true" /><h2 id={`competition-${group.competition.id}`}>{metadataLabel(group.competition.country, "Country")} — {group.competition.name}</h2><small>{group.competition.season}</small></div><span>{group.fixtures.length} {group.fixtures.length === 1 ? "match" : "matches"}</span></header>
    <div className="fixture-columns" aria-hidden="true"><span>Status / time</span><span>Fixture identity</span><span>Score</span><span>Probabilistic 3-way</span><span>Poisson model xG</span><span>Inspect</span></div>
    {group.fixtures.map((fixture) => <FixtureRow key={fixture.id} fixture={fixture} competition={group.competition} expanded={expanded === fixture.id} toggle={() => setExpanded(expanded === fixture.id ? null : fixture.id)} />)}
  </section>;
}

function FixtureRow({ fixture, competition, expanded, toggle }: { fixture: Fixture; competition: Competition; expanded: boolean; toggle: () => void }) {
  const forecast = fixture.forecast;
  const active = isActive(fixture);
  return <article className={`fixture ${expanded ? "expanded" : ""}`}>
    <button className="fixture-summary" aria-expanded={expanded} aria-controls={`fixture-panel-${fixture.id}`} onClick={toggle}>
      <span className="kickoff"><b>{active ? <span className="live-indicator">LIVE</span> : timeLabel(fixture.kickoff_at)}</b><small>{fixtureStateLabel(fixture)}</small>{!fixture.stale && fixture.freshness !== "FRESH" && <small>Freshness unknown</small>}</span>
      <span className="teams"><strong>{fixture.home.name}<Scorers fixture={fixture} side="HOME" /></strong><i>vs</i><strong>{fixture.away.name}<Scorers fixture={fixture} side="AWAY" /></strong></span>
      <span className="score">{fixtureScore(fixture)}</span>
      <span className="forecast-cell">{forecast ? <ProbabilityBar values={forecast.probabilities} /> : <span className="availability">{availabilityLabel(fixture.forecast_availability)}</span>}</span>
      <span className="xg">{forecast ? `λ ${forecast.expected_home_goals.toFixed(2)} · ${forecast.expected_away_goals.toFixed(2)}` : "—"}</span>
      <Icon name={expanded ? "chevron-up" : "chevron-down"} className="chevron" />
    </button>
    {expanded && <div id={`fixture-panel-${fixture.id}`}><ExpandedFixture fixture={fixture} competition={competition} /></div>}
  </article>;
}

function useLiveRefresh(groups: FixtureGroup[] | null, retry: () => void) {
  const shouldPoll = Boolean(groups?.some((group) => group.fixtures.some((fixture) =>
    ["SCHEDULED", "LIVE", "HALF_TIME", "INTERRUPTED", "SUSPENDED"].includes(fixture.status)
  )));
  useEffect(() => {
    if (!shouldPoll) return;
    let timer = 0;
    const schedule = () => { timer = window.setTimeout(() => { retry(); schedule(); }, document.hidden ? 120_000 : 45_000); };
    const visible = () => { window.clearTimeout(timer); if (!document.hidden) retry(); schedule(); };
    schedule();
    document.addEventListener("visibilitychange", visible);
    return () => { window.clearTimeout(timer); document.removeEventListener("visibilitychange", visible); };
  }, [shouldPoll, retry]);
}

function isActive(fixture: Fixture) {
  return ["LIVE", "HALF_TIME"].includes(fixture.status);
}

function fixtureStateLabel(fixture: Fixture) {
  let label: string = fixture.status;
  if (fixture.status === "HALF_TIME") label = "HT";
  else if (fixture.status === "FINISHED") label = "FT";
  else if (fixture.match_minute !== null) {
    label = `${fixture.match_minute}${fixture.added_time ? `+${fixture.added_time}` : ""}′`;
  }
  if (fixture.lifecycle_state === "RESULT_OVERDUE") label = `${label} · result overdue`;
  return `${label}${fixture.stale || fixture.freshness === "STALE" ? " · stale" : ""}`;
}

function fixtureScore(fixture: Fixture) {
  if ((!isActive(fixture) && !["FINISHED", "SUSPENDED", "INTERRUPTED"].includes(fixture.status)) || fixture.home_score === null || fixture.away_score === null) {
    return isActive(fixture) ? "Score unavailable" : "";
  }
  return `${fixture.home_score}–${fixture.away_score}`;
}

function Scorers({ fixture, side }: { fixture: Fixture; side: "HOME" | "AWAY" }) {
  const grouped = new Map<string, string[]>();
  for (const event of fixture.goal_scorers.filter((item) => item.team_side === side && item.player_name)) {
    const minute = event.minute === null ? "" : `${event.minute}${event.added_time ? `+${event.added_time}` : ""}′`;
    const label = `${minute}${event.penalty ? " pen" : ""}${event.own_goal ? " OG" : ""}`.trim();
    const values = grouped.get(event.player_name!) ?? [];
    if (label && !values.includes(label)) values.push(label);
    grouped.set(event.player_name!, values);
  }
  if (!grouped.size) return null;
  return <small className="goal-scorers">{[...grouped].map(([name, minutes]) => `${name} ${minutes.join(", ")}`).join(" · ")}</small>;
}

function metadataLabel(value: string, kind: string) { return value.trim().toUpperCase() === "UNKNOWN" ? `${kind} unavailable` : value; }
function timeLabel(value: string) { return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: DISPLAY_TIME_ZONE }).format(new Date(value)); }
function availabilityLabel(value: string) { return value === "NOT_ENOUGH_HISTORY" ? "Not enough history" : value === "SOURCE_DATA_INCOMPLETE" ? "Source incomplete" : value === "TEMPORARILY_UNAVAILABLE" ? "Temporarily unavailable" : "Forecast unavailable"; }
function fixtureCount(groups: FixtureGroup[] | null) { return groups?.reduce((total, group) => total + group.fixtures.length, 0) ?? "—"; }
