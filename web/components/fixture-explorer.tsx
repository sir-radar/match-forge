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

type Filters = { continent: string; country: string; competition: string; forecast: string };
type CoverageOptions = ReturnType<typeof coverageOptions>;

export function FixtureExplorer({ initialDate }: { initialDate: string }) {
  const [date, setDate] = useState(initialDate);
  const [dateError, setDateError] = useState<string | null>(null);
  const selectDate = (value: string) => { if (!validDay(value)) { setDateError("Choose a valid fixture date."); return; } setDateError(null); setDate(value); setExpanded(null); };
  const [filters, setFilters] = useState<Filters>({ continent: "", country: "", competition: "", forecast: "" });
  const [teamQuery, setTeamQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [expanded, setExpanded] = useState<string | null>(null);
  const competitionLoad = useCallback((signal: AbortSignal) => api.competitions(new URLSearchParams(), signal), []);
  const competitions = useResource("competitions", competitionLoad);
  const fixtureKey = `${date}|${Object.values(filters).join("|")}`;
  const fixtureLoad = useCallback((signal: AbortSignal) => {
    const query = new URLSearchParams({ date, timezone: DISPLAY_TIME_ZONE });
    if (filters.continent) query.set("continent", filters.continent);
    if (filters.country) query.set("country", filters.country);
    if (filters.competition) query.set("competition", filters.competition);
    if (filters.forecast) query.set("forecast_availability", filters.forecast);
    return api.fixtures(query, signal);
  }, [date, filters]);
  const fixtures = useResource(fixtureKey, fixtureLoad);
  useLiveRefresh(fixtures.data, fixtures.retry);
  const options = useMemo(() => coverageOptions(competitions.data ?? []), [competitions.data]);

  const moveDate = (days: number) => {
    const next = new Date(`${date}T12:00:00Z`);
    next.setUTCDate(next.getUTCDate() + days);
    selectDate(next.toISOString().slice(0, 10));
  };

  return (
    <div className="workspace">
      <h1 className="sr-only">MatchForge fixtures</h1>
      <CompetitionRail state={competitions} filters={filters} setFilters={setFilters} />
      <section className="fixture-workbench" aria-label="Football fixtures">
        <div className="environment-strip"><span>Environment: <b>Production pre-match</b></span><i /> <span>Forecasts: immutable published records</span></div>
        <FixtureToolbar date={date} count={fixtureCount(fixtures.data)} moveDate={moveDate} setDate={selectDate} />
        {dateError && <p role="alert">{dateError}</p>}
        <StatusFilters groups={fixtures.data ?? []} value={statusFilter} onChange={setStatusFilter} />
        <FixtureFilters filters={filters} setFilters={setFilters} competitions={competitions.data ?? []} options={options} refreshing={fixtures.refreshing} teamQuery={teamQuery} setTeamQuery={setTeamQuery} />
        <div className="engine-strip"><Icon name="monitoring" /><b>Probability engine</b><i>Real published MatchForge forecast data · no bookmaker odds</i></div>
        <FixtureResults state={fixtures} expanded={expanded} setExpanded={setExpanded} teamQuery={teamQuery} statusFilter={statusFilter} />
      </section>
    </div>
  );
}

function CompetitionRail({ state, filters, setFilters }: { state: ReturnType<typeof useResource<Competition[]>>; filters: Filters; setFilters: (update: (old: Filters) => Filters) => void }) {
  return <aside className="competition-rail" aria-label="Competition coverage">
    <div className="rail-heading"><span>Competitions</span><b>{state.data?.[0]?.season ?? "—"}</b></div>
    {state.error && <ResourceError message={state.error} retry={state.retry} />}
    <small className="rail-section">Available leagues</small>
    {(state.data ?? []).slice(0, 18).map((item) => (
      <button key={item.id} className={filters.competition === item.id ? "active" : ""} onClick={() => setFilters((old) => ({ ...old, competition: old.competition === item.id ? "" : item.id }))}>
        <span>{item.country} – {item.name}</span><small>{item.division ? `D${item.division}` : item.type}</small>
      </button>
    ))}
    <div className="rail-engine"><span aria-hidden="true" />MatchForge Forecast</div>
  </aside>;
}

function FixtureToolbar({ date, count, moveDate, setDate }: { date: string; count: number | string; moveDate: (days: number) => void; setDate: (value: string) => void }) {
  return <div className="fixture-toolbar">
    <div className="fixture-title"><Icon name="calendar" /><div><h2>Football Fixtures</h2><small>{count} matches scoped · {dayLabel(date)}</small></div></div>
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

function FixtureFilters({ filters, setFilters, competitions, options, refreshing, teamQuery, setTeamQuery }: { filters: Filters; setFilters: (value: Filters) => void; competitions: Competition[]; options: CoverageOptions; refreshing: boolean; teamQuery: string; setTeamQuery: (value: string) => void }) {
  const countries = options.countries.filter((item) => !filters.continent || item.continent === filters.continent);
  const leagues = competitions.filter((item) => (!filters.country || item.country === filters.country) && (!filters.continent || item.continent === filters.continent));
  return <div className="filters" aria-label="Fixture filters">
    <label>Continent<select value={filters.continent} onChange={(event) => setFilters({ ...filters, continent: event.target.value, country: "", competition: "" })}><option value="">All</option>{options.continents.map((value) => <option key={value}>{value}</option>)}</select></label>
    <label>Country<select value={filters.country} onChange={(event) => setFilters({ ...filters, country: event.target.value, competition: "" })}><option value="">All</option>{countries.map((item) => <option key={item.country}>{item.country}</option>)}</select></label>
    <label>League<select value={filters.competition} onChange={(event) => setFilters({ ...filters, competition: event.target.value })}><option value="">All</option>{leagues.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <label>Forecast<select value={filters.forecast} onChange={(event) => setFilters({ ...filters, forecast: event.target.value })}><option value="">All fixtures</option><option value="FORECAST_AVAILABLE">Available</option><option value="NOT_ENOUGH_HISTORY">Not enough history</option><option value="SOURCE_DATA_INCOMPLETE">Source incomplete</option></select></label>
    <label>Team<input type="search" value={teamQuery} onChange={(event) => setTeamQuery(event.target.value)} placeholder="Filter clubs…" /></label>
    {refreshing && <span className="refreshing" role="status">Refreshing…</span>}
  </div>;
}

function FixtureResults({ state, expanded, setExpanded, teamQuery, statusFilter }: { state: ReturnType<typeof useResource<FixtureGroup[]>>; expanded: string | null; setExpanded: (id: string | null) => void; teamQuery: string; statusFilter: string }) {
  if (state.loading) return <ResourceLoading label="Loading fixtures" />;
  if (state.error) return <ResourceError message={state.error} retry={state.retry} />;
  if (state.data?.length === 0) return <EmptyState title="No fixtures found" detail="The fixture can still be absent when a provider has no match for this date or the active filters exclude it." />;
  const query = teamQuery.trim().toLocaleLowerCase();
  const groups = (state.data ?? []).map((group) => ({ ...group, fixtures: group.fixtures.filter((fixture) => {
    const matchesTeam = !query || fixture.home.name.toLocaleLowerCase().includes(query) || fixture.away.name.toLocaleLowerCase().includes(query);
    const matchesStatus = statusFilter === "ALL" || (statusFilter === "UPCOMING" ? ["SCHEDULED", "TIMED", "UPCOMING"].includes(fixture.status) : statusFilter === "LIVE" ? ["LIVE", "HALF_TIME"].includes(fixture.status) : fixture.status === statusFilter);
    return matchesTeam && matchesStatus;
  }) })).filter((group) => group.fixtures.length);
  if (!groups.length) return <EmptyState title="No fixtures found" detail="No team in the selected fixture set matches this filter." />;
  return groups.map((group) => <FixtureGroupView key={group.competition.id} group={group} expanded={expanded} setExpanded={setExpanded} />);
}

function FixtureGroupView({ group, expanded, setExpanded }: { group: FixtureGroup; expanded: string | null; setExpanded: (id: string | null) => void }) {
  return <section className="fixture-group" aria-labelledby={`competition-${group.competition.id}`}>
    <header><div><span className="competition-mark" aria-hidden="true" /><h2 id={`competition-${group.competition.id}`}>{group.competition.country} — {group.competition.name}</h2><small>{group.competition.season}</small></div><span>{group.fixtures.length} {group.fixtures.length === 1 ? "match" : "matches"}</span></header>
    <div className="fixture-columns" aria-hidden="true"><span>Status / time</span><span>Fixture identity</span><span>Score</span><span>Probabilistic 3-way</span><span>Poisson model xG</span><span>Inspect</span></div>
    {group.fixtures.map((fixture) => <FixtureRow key={fixture.id} fixture={fixture} competition={group.competition} expanded={expanded === fixture.id} toggle={() => setExpanded(expanded === fixture.id ? null : fixture.id)} />)}
  </section>;
}

function FixtureRow({ fixture, competition, expanded, toggle }: { fixture: Fixture; competition: Competition; expanded: boolean; toggle: () => void }) {
  const forecast = fixture.forecast;
  const active = isActive(fixture);
  return <article className={`fixture ${expanded ? "expanded" : ""}`}>
    <button className="fixture-summary" aria-expanded={expanded} aria-controls={`fixture-panel-${fixture.id}`} onClick={toggle}>
      <span className="kickoff"><b>{active ? <span className="live-indicator">LIVE</span> : timeLabel(fixture.kickoff_at)}</b><small>{fixtureStateLabel(fixture)}</small></span>
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
  let label = fixture.status;
  if (fixture.status === "HALF_TIME") label = "HT";
  else if (fixture.status === "FINISHED") label = "FT";
  else if (fixture.match_minute !== null) {
    label = `${fixture.match_minute}${fixture.added_time ? `+${fixture.added_time}` : ""}′`;
  }
  return `${label}${fixture.stale ? " · stale" : ""}`;
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

function coverageOptions(competitions: Competition[]) {
  return {
    continents: [...new Set(competitions.map((item) => item.continent))].sort(),
    countries: [...new Map(competitions.map((item) => [item.country, { country: item.country, continent: item.continent }])).values()].sort((a, b) => a.country.localeCompare(b.country)),
  };
}

function timeLabel(value: string) { return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: DISPLAY_TIME_ZONE }).format(new Date(value)); }
function availabilityLabel(value: string) { return value === "NOT_ENOUGH_HISTORY" ? "Not enough history" : value === "SOURCE_DATA_INCOMPLETE" ? "Source incomplete" : value === "TEMPORARILY_UNAVAILABLE" ? "Temporarily unavailable" : "Forecast unavailable"; }
function fixtureCount(groups: FixtureGroup[] | null) { return groups?.reduce((total, group) => total + group.fixtures.length, 0) ?? "—"; }
