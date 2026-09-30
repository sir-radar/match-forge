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
        <div className="rail-heading"><span>Competitions</span><b>{competitions.data?.length ?? "—"}</b></div>
        {competitions.error && <ResourceError message={competitions.error} retry={competitions.retry} />}
        {(competitions.data ?? []).slice(0, 18).map((item) => (
          <button key={item.id} className={filters.competition === item.id ? "active" : ""} onClick={() => setFilters((old) => ({ ...old, competition: old.competition === item.id ? "" : item.id }))}>
            <span>{item.country} · {item.name}</span><small>{item.division ? `D${item.division}` : item.type}</small>
          </button>
        ))}
      </aside>
      <section className="fixture-workbench" aria-label="Football fixtures">
        <div className="date-bar">
          <button aria-label="Previous day" onClick={() => moveDate(-1)}>‹</button>
          <span>Yesterday</span>
          <label><span>Selected date</span><input type="date" value={date} onChange={(event) => { setDate(event.target.value); setExpanded(null); }} /></label>
          <span>Tomorrow</span>
          <button aria-label="Next day" onClick={() => moveDate(1)}>›</button>
        </div>
        <FixtureFilters filters={filters} setFilters={setFilters} competitions={competitions.data ?? []} options={options} refreshing={fixtures.refreshing} />
        <div className="engine-strip"><span>Current model</span><b>MatchForge Forecast</b><i>10-match rolling goals · immutable pre-kickoff forecasts</i></div>
        <FixtureResults state={fixtures} expanded={expanded} setExpanded={setExpanded} />
      </section>
    </div>
  );
}

function FixtureFilters({ filters, setFilters, competitions, options, refreshing }: { filters: Filters; setFilters: (value: Filters) => void; competitions: Competition[]; options: CoverageOptions; refreshing: boolean }) {
  const countries = options.countries.filter((item) => !filters.continent || item.continent === filters.continent);
  const leagues = competitions.filter((item) => (!filters.country || item.country === filters.country) && (!filters.continent || item.continent === filters.continent));
  return <div className="filters" aria-label="Fixture filters">
    <label>Continent<select value={filters.continent} onChange={(event) => setFilters({ ...filters, continent: event.target.value, country: "", competition: "" })}><option value="">All</option>{options.continents.map((value) => <option key={value}>{value}</option>)}</select></label>
    <label>Country<select value={filters.country} onChange={(event) => setFilters({ ...filters, country: event.target.value, competition: "" })}><option value="">All</option>{countries.map((item) => <option key={item.country}>{item.country}</option>)}</select></label>
    <label>League<select value={filters.competition} onChange={(event) => setFilters({ ...filters, competition: event.target.value })}><option value="">All</option>{leagues.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <label>Forecast<select value={filters.forecast} onChange={(event) => setFilters({ ...filters, forecast: event.target.value })}><option value="">All fixtures</option><option value="FORECAST_AVAILABLE">Available</option><option value="NOT_ENOUGH_HISTORY">Not enough history</option><option value="SOURCE_DATA_INCOMPLETE">Source incomplete</option></select></label>
    {refreshing && <span className="refreshing" role="status">Refreshing…</span>}
  </div>;
}

function FixtureResults({ state, expanded, setExpanded }: { state: ReturnType<typeof useResource<FixtureGroup[]>>; expanded: string | null; setExpanded: (id: string | null) => void }) {
  if (state.loading) return <ResourceLoading label="Loading fixtures" />;
  if (state.error) return <ResourceError message={state.error} retry={state.retry} />;
  if (state.data?.length === 0) return <EmptyState title="No fixtures found" detail="The fixture can still be absent when a provider has no match for this date or the active filters exclude it." />;
  return state.data?.map((group) => <FixtureGroupView key={group.competition.id} group={group} expanded={expanded} setExpanded={setExpanded} />);
}

function FixtureGroupView({ group, expanded, setExpanded }: { group: FixtureGroup; expanded: string | null; setExpanded: (id: string | null) => void }) {
  return <section className="fixture-group" aria-labelledby={`competition-${group.competition.id}`}>
    <header><div><span className="competition-mark" aria-hidden="true" /><h2 id={`competition-${group.competition.id}`}>{group.competition.country} — {group.competition.name}</h2><small>{group.competition.season}</small></div><span>{group.fixtures.length} {group.fixtures.length === 1 ? "match" : "matches"}</span></header>
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
      <span className="xg">{forecast ? `${forecast.expected_home_goals.toFixed(2)} · ${forecast.expected_away_goals.toFixed(2)} xG` : "—"}</span>
      <span className="chevron" aria-hidden="true">{expanded ? "⌃" : "⌄"}</span>
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
