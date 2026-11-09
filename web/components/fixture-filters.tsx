"use client";

import type { Competition } from "@/lib/contracts";
import type { FixtureFilters as Filters, MatchResult, PredictedOutcome } from "@/lib/fixture-filters";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";

export function FixtureFilters({ filters, setFilters, competitions, reset }: {
  filters: Filters; setFilters: (filters: Filters) => void; competitions: Competition[]; reset: () => void;
}) {
  const continents = [...new Set(competitions.map((item) => item.continent))].sort();
  const countries = [...new Set(competitions.filter((item) => !filters.continent || item.continent === filters.continent).map((item) => item.country))].sort();
  const leagues = competitions.filter((item) => (!filters.country || item.country === filters.country) && (!filters.continent || item.continent === filters.continent));
  return <section className="fixture-filter-toolbar" aria-label="Fixture filters">
    <div className="filters">
      <label>Continent<select value={filters.continent} onChange={(event) => setFilters({ ...filters, continent: event.target.value, country: "", competition: "" })}><option value="">All</option>{continents.map((value) => <option key={value} value={value}>{metadataLabel(value, "Continent")}</option>)}</select></label>
      <label>Country<select value={filters.country} onChange={(event) => setFilters({ ...filters, country: event.target.value, competition: "" })}><option value="">All</option>{countries.map((value) => <option key={value} value={value}>{metadataLabel(value, "Country")}</option>)}</select></label>
      <label>Competition<select value={filters.competition} onChange={(event) => setFilters({ ...filters, competition: event.target.value })}><option value="">All competitions</option>{leagues.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <label>Forecast<select value={filters.forecast} onChange={(event) => setFilters({ ...filters, forecast: event.target.value })}><option value="">All fixtures</option><option value="FORECAST_AVAILABLE">Available</option><option value="NOT_ENOUGH_HISTORY">Not enough history</option><option value="SOURCE_DATA_INCOMPLETE">Source incomplete</option></select></label>
      <label>Team<Input type="search" value={filters.team} onChange={(event) => setFilters({ ...filters, team: event.target.value })} placeholder="Filter clubs…" /></label>
      <label>Predicted outcome<select value={filters.outcome} onChange={(event) => setFilters({ ...filters, outcome: event.target.value as PredictedOutcome })}><option value="either">Either Team</option><option value="home">Home Win</option><option value="draw">Draw</option><option value="away">Away Win</option></select></label>
      <label>Actual match result<select value={filters.result} aria-describedby="result-basis-note" onChange={(event) => setFilters({ ...filters, result: event.target.value as MatchResult })}><option value="ALL">All Results</option><option value="HOME_WON">Home Won</option><option value="AWAY_WON">Away Won</option><option value="DRAW">Draw</option></select></label>
    </div>
    <div className="probability-filters">
      <ProbabilityFilter value={filters.minimumProbability} onChange={(minimumProbability) => setFilters({ ...filters, minimumProbability })} />
      <button type="button" className="reset-filters" onClick={reset}>Reset Filters</button>
    </div>
    <p className="filter-note" id="result-basis-note">Actual results use confirmed 90-minute scores. Forecast probabilities describe chances, not guaranteed outcomes.</p>
  </section>;
}

function ProbabilityFilter({ value, onChange }: { value: number | null; onChange: (value: number | null) => void }) {
  return <fieldset className="probability-filter">
    <legend>Minimum predicted probability <span>{value === null ? "Unrestricted" : `≥ ${value}%`}</span></legend>
    <div className="probability-controls">
      <div className="probability-presets" role="group" aria-label="Probability presets">
        {[null, 10, 25, 50, 55, 75, 100].map((preset) => <button type="button" key={String(preset)} aria-pressed={value === preset} onClick={() => onChange(preset)}>{preset === null ? "Any" : `${preset}%`}</button>)}
      </div>
      <Slider aria-label="Minimum predicted probability slider" aria-valuetext={value === null ? "0%, unrestricted" : `At least ${value}%`} min={0} max={100} step={1} value={[value ?? 0]} onValueChange={([percent]) => onChange(percent)} />
      <div className="probability-input"><label className="sr-only" htmlFor="fixture-min-probability">Minimum predicted probability (%)</label><Input id="fixture-min-probability" type="number" min={0} max={100} step="any" inputMode="decimal" value={value ?? ""} placeholder="Any" onChange={(event) => onChange(event.target.value === "" ? null : Math.min(100, Math.max(0, Number(event.target.value))))} /><span aria-hidden="true">%</span></div>
    </div>
  </fieldset>;
}

function metadataLabel(value: string, kind: string) { return value.trim().toUpperCase() === "UNKNOWN" ? `${kind} unavailable` : value; }
