"use client";

import { useCallback, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Competition, Fixture, FixtureGroup } from "@/lib/contracts";
import { useResource } from "@/hooks/use-resource";
import { EmptyState, ResourceError, ResourceLoading } from "@/components/resource-state";
import { ProbabilityBar } from "@/components/probability-bar";
import { ExpandedFixture } from "@/components/expanded-fixture";

type Filters = { continent: string; country: string; competition: string; forecast: string };
type CoverageOptions = ReturnType<typeof coverageOptions>;

export function FixtureExplorer({ initialDate }: { initialDate: string }) {
  const [date, setDate] = useState(initialDate);
  const [filters, setFilters] = useState<Filters>({ continent: "", country: "", competition: "", forecast: "" });
  const [teamQuery, setTeamQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [expanded, setExpanded] = useState<string | null>(null);
  const competitionLoad = useCallback((signal: AbortSignal) => api.competitions(new URLSearchParams(), signal), []);
  const competitions = useResource("competitions", competitionLoad);
  const fixtureKey = `${date}|${Object.values(filters).join("|")}`;
  const fixtureLoad = useCallback((signal: AbortSignal) => {
    const query = new URLSearchParams({ date });
    if (filters.continent) query.set("continent", filters.continent);
    if (filters.country) query.set("country", filters.country);
    if (filters.competition) query.set("competition", filters.competition);
    if (filters.forecast) query.set("forecast_availability", filters.forecast);
    return api.fixtures(query, signal);
  }, [date, filters]);
  const fixtures = useResource(fixtureKey, fixtureLoad);
  const options = useMemo(() => coverageOptions(competitions.data ?? []), [competitions.data]);

  const moveDate = (days: number) => {
    const next = new Date(`${date}T12:00:00Z`);
    next.setUTCDate(next.getUTCDate() + days);
    setDate(next.toISOString().slice(0, 10));
    setExpanded(null);
  };

  return (
    <div className="workspace">
      <h1 className="sr-only">MatchForge fixtures</h1>
      <aside className="competition-rail" aria-label="Competition coverage">
        <div className="rail-heading"><span>Competitions</span><b>{competitions.data?.[0]?.season ?? "—"}</b></div>
        {competitions.error && <ResourceError message={competitions.error} retry={competitions.retry} />}
        <small className="rail-section">Available leagues</small>
        {(competitions.data ?? []).slice(0, 18).map((item) => (
          <button key={item.id} className={filters.competition === item.id ? "active" : ""} onClick={() => setFilters((old) => ({ ...old, competition: old.competition === item.id ? "" : item.id }))}>
            <span>{item.country} – {item.name}</span><small>{item.division ? `D${item.division}` : item.type}</small>
          </button>
        ))}
        <div className="rail-engine"><span aria-hidden="true" />MatchForge Forecast</div>
      </aside>
      <section className="fixture-workbench" aria-label="Football fixtures">
        <div className="environment-strip"><span>Environment: <b>Production pre-match</b></span><i /> <span>Forecasts: immutable published records</span></div>
        <div className="fixture-toolbar">
          <div className="fixture-title"><span className="material-symbol" aria-hidden="true">calendar_view_day</span><div><h2>Football Fixtures</h2><small>{fixtureCount(fixtures.data)} matches scoped · {longDate(date)}</small></div></div>
          <div className="date-bar">
            <button aria-label="Previous day" onClick={() => moveDate(-1)}><span className="material-symbol" aria-hidden="true">chevron_left</span><span>Prev Day</span></button>
            <label><span>Selected date</span><input type="date" value={date} onChange={(event) => { setDate(event.target.value); setExpanded(null); }} /></label>
            <button aria-label="Next day" onClick={() => moveDate(1)}><span>Next Day</span><span className="material-symbol" aria-hidden="true">chevron_right</span></button>
          </div>
        </div>
        <StatusFilters groups={fixtures.data ?? []} value={statusFilter} onChange={setStatusFilter} />
        <FixtureFilters filters={filters} setFilters={setFilters} competitions={competitions.data ?? []} options={options} refreshing={fixtures.refreshing} teamQuery={teamQuery} setTeamQuery={setTeamQuery} />
        <div className="engine-strip"><span className="material-symbol" aria-hidden="true">monitoring</span><b>Probability engine</b><i>Real published MatchForge forecast data · no bookmaker odds</i></div>
        <FixtureResults state={fixtures} expanded={expanded} setExpanded={setExpanded} teamQuery={teamQuery} statusFilter={statusFilter} />
      </section>
    </div>
  );
}

function StatusFilters({ groups, value, onChange }: { groups: FixtureGroup[]; value: string; onChange: (value: string) => void }) {
  const fixtures = groups.flatMap((group) => group.fixtures);
  const items = [["ALL", "All", fixtures.length], ["UPCOMING", "Upcoming", fixtures.filter((item) => ["SCHEDULED", "TIMED", "UPCOMING"].includes(item.status)).length], ["LIVE", "Live", fixtures.filter((item) => item.status === "LIVE").length], ["FINISHED", "Finished", fixtures.filter((item) => item.status === "FINISHED").length]] as const;
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
    const matchesStatus = statusFilter === "ALL" || (statusFilter === "UPCOMING" ? ["SCHEDULED", "TIMED", "UPCOMING"].includes(fixture.status) : fixture.status === statusFilter);
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
  return <article className={`fixture ${expanded ? "expanded" : ""}`}>
    <button className="fixture-summary" aria-expanded={expanded} aria-controls={`fixture-panel-${fixture.id}`} onClick={toggle}>
      <span className="kickoff"><b>{timeLabel(fixture.kickoff_at)}</b><small>{fixture.status}</small></span>
      <span className="teams"><strong>{fixture.home.name}</strong><i>vs</i><strong>{fixture.away.name}</strong></span>
      <span className="score">{fixture.status === "FINISHED" ? `${fixture.home_score}–${fixture.away_score}` : ""}</span>
      <span className="forecast-cell">{forecast ? <ProbabilityBar values={forecast.probabilities} /> : <span className="availability">{availabilityLabel(fixture.forecast_availability)}</span>}</span>
      <span className="xg">{forecast ? `λ ${forecast.expected_home_goals.toFixed(2)} · ${forecast.expected_away_goals.toFixed(2)}` : "—"}</span>
      <span className="chevron material-symbol" aria-hidden="true">{expanded ? "expand_less" : "expand_more"}</span>
    </button>
    {expanded && <div id={`fixture-panel-${fixture.id}`}><ExpandedFixture fixture={fixture} competition={competition} /></div>}
  </article>;
}

function coverageOptions(competitions: Competition[]) {
  return {
    continents: [...new Set(competitions.map((item) => item.continent))].sort(),
    countries: [...new Map(competitions.map((item) => [item.country, { country: item.country, continent: item.continent }])).values()].sort((a, b) => a.country.localeCompare(b.country)),
  };
}

function timeLabel(value: string) { return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" }).format(new Date(value)); }
function availabilityLabel(value: string) { return value === "NOT_ENOUGH_HISTORY" ? "Not enough history" : value === "SOURCE_DATA_INCOMPLETE" ? "Source incomplete" : value === "TEMPORARILY_UNAVAILABLE" ? "Temporarily unavailable" : "Forecast unavailable"; }
function fixtureCount(groups: FixtureGroup[] | null) { return groups?.reduce((total, group) => total + group.fixtures.length, 0) ?? "—"; }
function longDate(value: string) { return new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "2-digit", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T12:00:00Z`)); }
