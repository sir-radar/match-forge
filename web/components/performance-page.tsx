"use client";

import { useCallback, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Competition, Performance, PerformancePage as PerformancePageData } from "@/lib/contracts";
import { useResource } from "@/hooks/use-resource";
import { EmptyState, ResourceError, ResourceLoading } from "@/components/resource-state";

type Filters = { continent: string; country: string; competition: string; rating: string; minimum_forecasts: string };

export function PerformancePage() {
  const [filters, setFilters] = useState<Filters>({ continent: "", country: "", competition: "", rating: "", minimum_forecasts: "0" });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<20 | 50 | 100>(20);
  const competitionLoad = useCallback((signal: AbortSignal) => api.competitions(new URLSearchParams(), signal), []);
  const competitions = useResource("performance-competitions", competitionLoad);
  const query = useMemo(() => filterQuery(filters, page, pageSize), [filters, page, pageSize]);
  const performanceLoad = useCallback(async (signal: AbortSignal) => {
    const data = await api.performanceList(query, signal);
    if (!signal.aborted && data.pagination.page !== page) setPage(data.pagination.page);
    return data;
  }, [query, page]);
  const performance = useResource(`performance-${query}`, performanceLoad);
  const updateFilters = (value: Filters) => { setPage(1); setFilters(value); };
  const updatePageSize = (value: 20 | 50 | 100) => { setPage(1); setPageSize(value); };

  return <div className="page">
    <header className="page-heading"><div><small>Model monitoring</small><h1>League-level performance</h1><p>Chronological results from settled, immutable pre-kickoff MatchForge Forecast records. A minimum of 50 settled forecasts is required for a rating.</p></div></header>
    <PerformanceFilters filters={filters} setFilters={updateFilters} competitions={competitions.data ?? []} />
    {competitions.error && <ResourceError message={competitions.error} retry={competitions.retry} />}
    {performance.loading && <ResourceLoading label="Calculating league performance" />}
    {performance.error && <ResourceError message={performance.error} retry={performance.retry} />}
    {performance.data?.performance.length === 0 && <EmptyState title="No leagues match these filters" detail="Performance appears only after an immutable pre-kickoff forecast has a stored completed result." />}
    {performance.data?.performance.length ? <PerformanceTable
      data={performance.data}
      pageSize={pageSize}
      refreshing={performance.refreshing}
      setPage={setPage}
      setPageSize={updatePageSize}
    /> : null}
    <section className="panel performance-note"><header><h2>Rating contract</h2></header><p>UNRATED means fewer than 50 settled forecasts. WATCH, GOOD, and STRONG use the frozen league-comparison rule. Ratings describe forecast performance, not betting advice.</p></section>
  </div>;
}

function PerformanceFilters({ filters, setFilters, competitions }: { filters: Filters; setFilters: (value: Filters) => void; competitions: Competition[] }) {
  const update = (name: keyof Filters, value: string) => setFilters({ ...filters, [name]: value });
  const continents = [...new Set(competitions.map((item) => item.continent))].sort();
  const countries = [...new Set(competitions.filter((item) => !filters.continent || item.continent === filters.continent).map((item) => item.country))].sort();
  const leagues = competitions.filter((item) => (!filters.continent || item.continent === filters.continent) && (!filters.country || item.country === filters.country));
  return <div className="filter-strip">
    <label>Continent<select value={filters.continent} onChange={(event) => setFilters({ ...filters, continent: event.target.value, country: "", competition: "" })}><option value="">All</option>{continents.map((item) => <option key={item}>{item}</option>)}</select></label>
    <label>Country<select value={filters.country} onChange={(event) => setFilters({ ...filters, country: event.target.value, competition: "" })}><option value="">All</option>{countries.map((item) => <option key={item}>{item}</option>)}</select></label>
    <label>League<select value={filters.competition} onChange={(event) => update("competition", event.target.value)}><option value="">All</option>{leagues.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <label>Rating<select value={filters.rating} onChange={(event) => update("rating", event.target.value)}><option value="">All</option>{["UNRATED", "WATCH", "GOOD", "STRONG"].map((item) => <option key={item}>{item}</option>)}</select></label>
    <label>Minimum forecasts<input type="number" min="0" value={filters.minimum_forecasts} onChange={(event) => update("minimum_forecasts", event.target.value)} /></label>
  </div>;
}

type PerformanceTableProps = {
  data: PerformancePageData;
  pageSize: 20 | 50 | 100;
  refreshing: boolean;
  setPage: (page: number) => void;
  setPageSize: (pageSize: 20 | 50 | 100) => void;
};

function PerformanceTable({ data, pageSize, refreshing, setPage, setPageSize }: PerformanceTableProps) {
  const { page, total_items: totalItems, total_pages: totalPages } = data.pagination;
  const firstItem = (page - 1) * data.pagination.page_size + 1;
  const lastItem = firstItem + data.performance.length - 1;
  return <section className="panel" aria-busy={refreshing}>
    <div className="table-scroll" tabIndex={0}><table><caption className="sr-only">League performance results</caption><thead><tr><th>League</th><th>Rating</th><th>Forecasts</th><th>1X2</th><th>Top-3 Score</th><th>Top-5 Score</th><th>Brier</th><th>Log Loss</th><th>Recent</th></tr></thead><tbody>{data.performance.map((item: Performance) => <tr key={item.competition_id}><th scope="row"><small>{item.continent} · {item.country}</small><br />{item.league}</th><td><span className={`rating ${item.rating.toLowerCase()}`}>{item.rating}</span></td><td>{item.forecasts}</td><td>{metric(item.outcome_hit_rate, true)}</td><td>{metric(item.top_three_score_rate, true)}</td><td>{metric(item.top_five_score_rate, true)}</td><td>{metric(item.brier)}</td><td>{metric(item.log_loss)}</td><td>{metric(item.latest_fifty_brier)}</td></tr>)}</tbody></table></div>
    <nav className="table-pagination" aria-label="Performance table pagination">
      <label>Rows per page<select disabled={refreshing} value={pageSize} onChange={(event) => setPageSize(Number(event.target.value) as 20 | 50 | 100)}><option value="20">20</option><option value="50">50</option><option value="100">100</option></select></label>
      <p aria-live="polite">Showing {firstItem}–{lastItem} of {totalItems} · Page {page} of {totalPages}</p>
      <div><button type="button" disabled={refreshing || page <= 1} onClick={() => setPage(page - 1)}>Previous</button><button type="button" disabled={refreshing || page >= totalPages} onClick={() => setPage(page + 1)}>Next</button></div>
    </nav>
  </section>;
}

function metric(value: number | null, percentage = false) { return value === null ? "—" : percentage ? `${(value * 100).toFixed(1)}%` : value.toFixed(3); }
function filterQuery(filters: Filters, page: number, pageSize: number) { const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) }); Object.entries(filters).forEach(([key, value]) => { if (value && !(key === "minimum_forecasts" && value === "0")) query.set(key, value); }); return query; }
