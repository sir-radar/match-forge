"use client";

import Link from "next/link";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Icon } from "@/components/icon";
import { Logo } from "@/components/logo";
import { useResource } from "@/hooks/use-resource";
import { api } from "@/lib/api";
import type { ExternalPrediction, ExternalSource } from "@/lib/contracts";

type FacetFilters = {
  source: string;
  continent: string;
  country: string;
  competition: string;
  market: string;
  agreement: string;
};

type ViewMode = "live" | "empty" | "loading";

const EMPTY_FILTERS: FacetFilters = {
  source: "",
  continent: "",
  country: "",
  competition: "",
  market: "",
  agreement: "",
};

const FILTER_LABELS: Record<keyof FacetFilters, string> = {
  source: "Source",
  continent: "Continent",
  country: "Country",
  competition: "Comp",
  market: "Market",
  agreement: "Status",
};

const mono = "font-mono tabular-nums";
const control = "h-8 w-full min-w-0 rounded-sm border border-[#262a34] bg-[#1c1f29] px-2 text-[10px] text-[#dfe2ef] outline-none focus:border-[#7bd0ff]";

export function PredictionsPage({ initialDate }: { initialDate?: string }) {
  const initialDay = initialDate ?? utcToday();
  const [day, setDay] = useState(initialDay);
  const [filters, setFilters] = useState<FacetFilters>(EMPTY_FILTERS);
  const [viewMode, setViewMode] = useState<ViewMode>("live");

  const predictionQuery = useMemo(() => buildPredictionQuery(day, filters), [day, filters]);
  const sourceQuery = useMemo(() => buildSourceQuery(day, filters), [day, filters]);
  const loadSources = useCallback(
    (signal: AbortSignal) => api.sources(new URLSearchParams(sourceQuery), signal),
    [sourceQuery],
  );
  const loadPredictions = useCallback(
    (signal: AbortSignal) => api.predictions(new URLSearchParams(predictionQuery), signal),
    [predictionQuery],
  );
  const sources = useResource(`external-sources-${sourceQuery}`, loadSources);
  const predictions = useResource(`external-predictions-${predictionQuery}`, loadPredictions);

  const sourceItems = sources.data ?? [];
  const predictionItems = useMemo(
    () => (predictions.data ?? [])
      .filter((item) => item.prediction_date === day)
      .sort((left, right) => right.collected_at.localeCompare(left.collected_at)),
    [day, predictions.data],
  );
  const consensus = useMemo(() => consensusRows(predictionItems).slice(0, 3), [predictionItems]);
  const reviewed = sourceItems.length;
  const approved = sourceItems.filter((item) => item.adapter_status === "ENABLED").length;
  const tracked = sourceItems.reduce((sum, item) => sum + item.tracked_selections, 0);

  const changeDay = (nextDay: string) => {
    setDay(nextDay);
    setViewMode("live");
  };
  const updateFilter = (key: keyof FacetFilters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setViewMode("live");
  };
  const resetFilters = () => {
    setFilters(EMPTY_FILTERS);
    setViewMode("live");
  };

  return (
    <div className="min-h-screen bg-[#0f131c] text-[#dfe2ef] antialiased">
      <PredictionsHeader />
      <main id="main" className="min-h-[calc(100vh-3.5rem)] pt-14">
        <Intro day={day} />
        <MetricStrip reviewed={reviewed} approved={approved} tracked={tracked} count={predictionItems.length} />
        <FiltersBar
          day={day}
          filters={filters}
          sources={sourceItems}
          count={predictionItems.length}
          refreshing={sources.refreshing || predictions.refreshing}
          onDayChange={changeDay}
          onFilterChange={updateFilter}
          onReset={resetFilters}
          onRefresh={() => {
            sources.retry();
            predictions.retry();
          }}
        />

        <SourceFailure error={sources.error} retry={sources.retry} />
        <ConsensusResource loading={predictions.loading} error={predictions.error} items={predictionItems} rows={consensus} />

        <StateBar count={predictionItems.length} value={viewMode} onChange={setViewMode} />
        <PredictionTableResource
          day={day}
          items={predictionItems}
          loading={predictions.loading}
          refreshing={predictions.refreshing}
          error={predictions.error}
          viewMode={viewMode}
          retry={predictions.retry}
          reset={resetFilters}
        />

        <SourceAudit sources={sourceItems} />
      </main>
      <PredictionsFooter />
    </div>
  );
}

function SourceFailure({ error, retry }: { error: string | null; retry: () => void }) {
  if (!error) return null;
  return <div className="px-4 pt-3"><ErrorState label="Source registry unavailable" message={error} retry={retry} /></div>;
}

function ConsensusResource({ loading, error, items, rows }: {
  loading: boolean;
  error: string | null;
  items: ExternalPrediction[];
  rows: ReturnType<typeof consensusRows>;
}) {
  if (loading || error || items.length === 0) return null;
  return <Consensus rows={rows} />;
}

function PredictionTableResource({ day, items, loading, refreshing, error, viewMode, retry, reset }: {
  day: string;
  items: ExternalPrediction[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  viewMode: ViewMode;
  retry: () => void;
  reset: () => void;
}) {
  let content: ReactNode;
  if (loading || viewMode === "loading") {
    content = <Loading />;
  } else if (error) {
    content = <ErrorState label="External selections unavailable" message={error} retry={retry} />;
  } else if (items.length === 0 || viewMode === "empty") {
    content = <EmptyState reset={reset} />;
  } else {
    content = <Results day={day} items={items} refreshing={refreshing} />;
  }
  return <section className="w-full bg-[#0f131c] px-4 py-3" aria-label="External prediction records"><div className="mx-auto max-w-[1720px]">{content}</div></section>;
}

function PredictionsHeader() {
  return (
    <header className="fixed inset-x-0 top-0 z-50 h-14 border-b border-[#262a34] bg-[#0a0e17]">
      <div className="flex h-full w-full items-center justify-between px-4">
        <div className="flex min-w-0 items-center gap-5">
          <div className="flex shrink-0 items-center gap-1.5">
            <Link href="/" aria-label="MatchForge home" className="flex items-center"><Logo /></Link>
            <span className={`${mono} hidden rounded-sm border border-[#3c4a42] bg-[#1c1f29] px-1 py-0.5 text-[9px] text-[#86948a] sm:inline`}>CORE.v4</span>
          </div>
          <nav aria-label="Primary navigation" className="hidden h-14 items-stretch md:flex">
            <HeaderLink href="/">Matches</HeaderLink>
            <HeaderLink href="/performance">Performance</HeaderLink>
            <HeaderLink href="/predictions" current>External Predictions</HeaderLink>
            <HeaderLink href="/admin/data-sync">Admin</HeaderLink>
          </nav>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <div className={`hidden items-center gap-2 rounded-sm border border-[#3c4a42] bg-[#1c1f29] px-2 py-1 text-[9px] uppercase tracking-wider sm:flex ${mono}`}><span className="h-2 w-2 rounded-full bg-[#4edea3]" />Feed: Live</div>
          <div className={`hidden items-center gap-1 text-[10px] text-[#bbcabf] lg:flex ${mono}`}><span aria-hidden="true">◷</span> UTC+0 London</div>
          <div className="hidden h-4 w-px bg-[#262a34] lg:block" />
          <span className="grid h-8 w-8 place-items-center rounded-full bg-[#4edea3] text-[#003824]"><Icon name="person" className="h-[18px] w-[18px]" /><span className="sr-only">Operator profile</span></span>
        </div>
      </div>
    </header>
  );
}

function HeaderLink({ href, current = false, children }: { href: string; current?: boolean; children: ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      className={`grid place-items-center border-b-2 px-3 font-['Space_Grotesk',system-ui,sans-serif] text-[13px] font-semibold transition-colors ${current ? "border-[#4edea3] bg-[#262a34] text-[#4edea3]" : "border-transparent text-[#bbcabf] hover:bg-[#1c1f29] hover:text-[#dfe2ef]"}`}
    >
      {children}
    </Link>
  );
}

function Intro({ day }: { day: string }) {
  return (
    <section className="w-full border-b border-[#262a34] bg-[#0a0e17] px-4 py-3">
      <div className="mx-auto grid max-w-[1720px] gap-3 lg:grid-cols-[minmax(0,1fr)_520px] lg:items-center">
        <div>
          <div className={`mb-1 flex flex-wrap items-center gap-1 text-[10px] font-semibold tracking-wider ${mono}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-[#7bd0ff]" />
            <span className="uppercase text-[#7bd0ff]">Independent comparison archive</span>
            <span className="text-[#86948a]">/</span>
            <span className="text-[#bbcabf]">VERIFIED_EXTERNAL_EVID_V2</span>
          </div>
          <div className="flex items-baseline gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">External predictions</h1>
            <span className={`hidden text-[10px] text-[#86948a] md:inline ${mono}`}>Daily partition {day}</span>
          </div>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[#bbcabf]">Public selections are cataloged strictly as immutable empirical evidence. They never calibrate, feed, weight, or overwrite MatchForge Poisson goal models or probability densities.</p>
        </div>

        <div className="flex items-center gap-2 rounded-sm border border-[#4edea3]/25 bg-[#181b25] px-3 py-2">
          <Icon name="verified" className="h-5 w-5 text-[#4edea3]" />
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <strong className={`text-[10px] uppercase tracking-wide text-[#4edea3] ${mono}`}>Model influence: 0.00%</strong>
              <span className={`rounded-sm border border-[#4edea3]/30 bg-[#4edea3]/10 px-1.5 py-0.5 text-[9px] uppercase text-[#4edea3] ${mono}`}>Air-gapped</span>
            </div>
            <p className={`mt-0.5 text-[9px] text-[#86948a] ${mono}`}>Strict isolation: external evidence does not alter model probabilities.</p>
          </div>
          <button type="button" disabled title="Proof log is not exposed by the current API" className={`ml-auto flex shrink-0 items-center gap-1 rounded-sm bg-[#262a34] px-2 py-1 text-[9px] text-[#bbcabf] ${mono}`}><Icon name="verified" className="h-3.5 w-3.5 text-[#7bd0ff]" />Proof Log</button>
        </div>
      </div>
    </section>
  );
}

function MetricStrip({ reviewed, approved, tracked, count }: { reviewed: number; approved: number; tracked: number; count: number }) {
  return (
    <section className="w-full border-b border-[#262a34] bg-[#0f131c] px-4 py-3" aria-label="External prediction summary">
      <div className="mx-auto grid max-w-[1720px] grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric icon="monitoring" label="Sources reviewed" value={fmt(reviewed)} detail="Active registries" footerLabel="Daily registry scope" footerValue={`${fmt(reviewed)} sources`} />
        <Metric icon="verified" label="Approved adapters" value={fmt(approved)} detail="Enabled" footerLabel="Adapter status" footerValue={`${fmt(approved)} operational`} />
        <Metric icon="table" label="Stored selections" value={fmt(tracked)} detail="Recorded records" footerLabel="Active day" footerValue={`${fmt(count)} selections`} />
        <Metric icon="verified" label="Model influence" value="0.0%" detail="Immutable isolation" footerLabel="Feedback prevention" footerValue="Zero weight" accent />
      </div>
    </section>
  );
}

function Metric({ icon, label, value, detail, footerLabel, footerValue, accent = false }: {
  icon: "monitoring" | "verified" | "table";
  label: string;
  value: string;
  detail: string;
  footerLabel: string;
  footerValue: string;
  accent?: boolean;
}) {
  return (
    <article className={`flex min-h-28 flex-col justify-between rounded-sm border bg-[#181b25] p-3 ${accent ? "border-[#4edea3]/25" : "border-[#262a34]"}`}>
      <div className={`flex items-center justify-between text-[9px] uppercase tracking-wider ${accent ? "text-[#4edea3]" : "text-[#bbcabf]"} ${mono}`}><span>{label}</span><Icon name={icon} className={`h-[18px] w-[18px] ${accent ? "text-[#4edea3]" : "text-[#7bd0ff]"}`} /></div>
      <div className="mt-2 flex flex-wrap items-baseline gap-1.5"><strong className={`text-2xl font-bold ${accent ? "text-[#4edea3]" : "text-[#dfe2ef]"} ${mono}`}>{value}</strong><span className={`text-[9px] font-semibold ${accent ? "text-[#4edea3]" : "text-[#bbcabf]"} ${mono}`}>{detail}</span></div>
      <div className={`mt-2 flex items-center justify-between border-t border-[#262a34] pt-2 text-[9px] text-[#86948a] ${mono}`}><span>{footerLabel}</span><span className={accent ? "text-[#4edea3]" : "text-[#bbcabf]"}>{footerValue}</span></div>
    </article>
  );
}

function FiltersBar({ day, filters, sources, count, refreshing, onDayChange, onFilterChange, onReset, onRefresh }: {
  day: string;
  filters: FacetFilters;
  sources: ExternalSource[];
  count: number;
  refreshing: boolean;
  onDayChange: (day: string) => void;
  onFilterChange: (key: keyof FacetFilters, value: string) => void;
  onReset: () => void;
  onRefresh: () => void;
}) {
  const active = Object.entries(filters).filter((entry): entry is [keyof FacetFilters, string] => entry[1] !== "");
  const today = utcToday();

  return (
    <section className="sticky top-14 z-30 w-full border-b border-[#262a34] bg-[#0a0e17]/95 px-4 py-2 backdrop-blur" aria-label="Prediction filters">
      <div className="mx-auto flex max-w-[1720px] flex-col gap-1.5">
        <div className="grid grid-cols-2 items-center gap-1.5 sm:grid-cols-4 md:grid-cols-8 lg:grid-cols-9">
          <div className="col-span-2 flex h-8 min-w-0 items-center rounded-sm border border-[#262a34] bg-[#1c1f29]">
            <button type="button" onClick={() => onDayChange(addDays(day, -1))} aria-label="Previous day" className="grid h-full w-8 shrink-0 place-items-center border-r border-[#262a34] text-[#bbcabf] hover:bg-[#262a34] hover:text-[#dfe2ef]"><Icon name="chevron-left" className="h-4 w-4" /></button>
            <Icon name="calendar" className="ml-2 h-4 w-4 shrink-0 text-[#86948a]" />
            <label className="min-w-0 flex-1">
              <span className="sr-only">Prediction day</span>
              <input aria-label="Prediction day" type="date" value={day} max={today} onChange={(event) => event.target.value && onDayChange(event.target.value)} className={`h-[30px] w-full min-w-0 border-0 bg-transparent px-2 text-[10px] text-[#dfe2ef] outline-none ${mono}`} />
            </label>
            <button type="button" onClick={() => onDayChange(addDays(day, 1))} aria-label="Next day" disabled={day >= today} className="grid h-full w-8 shrink-0 place-items-center border-l border-[#262a34] text-[#bbcabf] hover:bg-[#262a34] hover:text-[#dfe2ef] disabled:cursor-not-allowed disabled:opacity-35"><Icon name="chevron-right" className="h-4 w-4" /></button>
          </div>

          <select aria-label="Source" className={control} value={filters.source} onChange={(event) => onFilterChange("source", event.target.value)}><option value="">All Sources ({sources.length})</option>{sources.map((source) => <option key={source.code} value={source.code}>{source.name}</option>)}</select>
          <input aria-label="Continent" className={control} placeholder="All continents" value={filters.continent} onChange={(event) => onFilterChange("continent", event.target.value)} />
          <input aria-label="Country" className={control} placeholder="All countries" value={filters.country} onChange={(event) => onFilterChange("country", event.target.value)} />
          <input aria-label="Competition" className={control} placeholder="All competitions" value={filters.competition} onChange={(event) => onFilterChange("competition", event.target.value)} />
          <select aria-label="Market" className={control} value={filters.market} onChange={(event) => onFilterChange("market", event.target.value)}><option value="">All Markets</option><option value="RESULT_1X2">1X2 Match Result</option><option value="TOTAL_GOALS">Total Goals O/U</option><option value="BTTS">Both Teams To Score</option><option value="DOUBLE_CHANCE">Double Chance</option></select>
          <select aria-label="Agreement" className={control} value={filters.agreement} onChange={(event) => onFilterChange("agreement", event.target.value)}><option value="">All Statuses</option><option value="AGREES">Agrees</option><option value="WEAK_SUPPORT">Weak support</option><option value="DISAGREES">Disagrees</option><option value="UNABLE_TO_EVALUATE">Unable to evaluate</option></select>
          <div className="col-span-2 flex items-center gap-1 sm:col-span-1">
            <button type="button" aria-label="Reset filters" onClick={onReset} className={`flex h-8 flex-1 items-center justify-center gap-1 rounded-sm bg-[#262a34] px-2 text-[10px] text-[#bbcabf] hover:bg-[#353943] ${mono}`}><span aria-hidden="true">↻</span> Reset</button>
            <button type="button" aria-label="Refresh filtered data" onClick={onRefresh} className="grid h-8 w-8 shrink-0 place-items-center rounded-sm bg-[#4edea3] text-[#003824] hover:bg-[#6ffbbe]"><span aria-hidden="true">↻</span></button>
          </div>
        </div>

        <div className={`flex flex-wrap items-center justify-between gap-1.5 border-t border-[#262a34]/50 pt-1.5 text-[9px] ${mono}`}>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 uppercase tracking-wider text-[#86948a]">Active filters:</span>
            <FilterPill label="Date" value={day} onRemove={null} />
            {active.map(([key, value]) => <FilterPill key={key} label={FILTER_LABELS[key]} value={filterDisplay(key, value)} onRemove={() => onFilterChange(key, "")} />)}
            <span className="inline-flex items-center gap-1 rounded-sm border border-[#3c4a42] bg-[#1c1f29] px-2 py-0.5"><span>Isolation:</span><strong className="text-[#4edea3]">Zero Weight</strong><span aria-hidden="true">▣</span></span>
            {active.length > 0 && <button type="button" onClick={onReset} className="ml-1 text-[#86948a] underline hover:text-[#dfe2ef]">Clear all</button>}
          </div>
          <div className="ml-auto flex items-center gap-3">
            <span className="rounded-sm border border-[#3c4a42] bg-[#1c1f29] px-2 py-0.5">Showing <strong className="text-[#4edea3]">{fmt(count)}</strong> selections for {day}</span>
            <span className="flex items-center gap-1 text-[#86948a]" aria-live="polite"><span className={`h-2 w-2 rounded-full ${refreshing ? "bg-[#7bd0ff]" : "bg-[#4edea3]"}`} />{refreshing ? "Refreshing" : "Cluster Synced"}</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function FilterPill({ label, value, onRemove }: { label: string; value: string; onRemove: (() => void) | null }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm border border-[#3c4a42] bg-[#1c1f29] px-2 py-0.5">
      <span>{label}:</span><strong className={label === "Date" ? "text-[#dfe2ef]" : "text-[#7bd0ff]"}>{value}</strong>
      {onRemove && <button type="button" onClick={onRemove} aria-label={`Remove ${label} filter`} className="ml-1 hover:text-[#ffb4ab]">×</button>}
    </span>
  );
}

function Consensus({ rows }: { rows: ReturnType<typeof consensusRows> }) {
  return (
    <section className="w-full border-b border-[#262a34] bg-[#0f131c] px-4 py-3" aria-labelledby="consensus-title">
      <div className="mx-auto max-w-[1720px]">
        <header className="mb-1.5 flex flex-col justify-between gap-2 border-b border-[#262a34] pb-1 sm:flex-row sm:items-center">
          <div>
            <div className="flex items-center gap-2"><h2 id="consensus-title" className="text-[15px] font-semibold">Multi-Source External Consensus</h2><span className={`rounded-sm border border-[#353943] bg-[#262a34] px-1.5 py-0.5 text-[9px] uppercase text-[#7bd0ff] ${mono}`}>Cluster Evaluation</span></div>
            <p className="mt-0.5 text-[11px] text-[#bbcabf]">Informational only · Source concurrence never increments or calibrates MatchForge generative Poisson matrices.</p>
          </div>
          <span className={`text-[9px] text-[#86948a] ${mono}`}>Threshold: 2+ verified sources</span>
        </header>

        <div className="grid grid-cols-1 gap-1.5 lg:grid-cols-3">
          {rows.map((row) => {
            const ratio = Math.round((row.count / row.total) * 100);
            return (
              <article key={row.id} className="rounded-sm border border-[#262a34] bg-[#181b25] p-1.5 hover:border-[#86948a]/40">
                <div className="mb-2 flex items-center justify-between gap-2 border-b border-[#262a34]/60 pb-1"><h3 className="text-[15px] font-semibold">{row.fixture}</h3><span className={`text-[9px] text-[#86948a] ${mono}`}>{kickoff(row.kickoff)} UTC</span></div>
                <dl className="space-y-1.5 text-[11px]">
                  <div className="flex items-center justify-between gap-2"><dt className="text-[#bbcabf]">Dominant Ext. Pick:</dt><dd className={`rounded-sm bg-[#1c1f29] px-1.5 py-0.5 font-semibold text-[#7bd0ff] ${mono}`}>{row.selection}</dd></div>
                  <div className="flex items-center justify-between gap-2"><dt className="text-[#bbcabf]">Consensus Ratio:</dt><dd className={`flex items-center gap-1.5 ${mono}`}><span className="h-1.5 w-16 overflow-hidden rounded-full bg-[#1c1f29]"><span className={`block h-full ${row.agreement === "AGREES" ? "bg-[#4edea3]" : "bg-amber-400"}`} style={{ width: `${ratio}%` }} /></span>{row.count} of {row.total} sources ({ratio}%)</dd></div>
                  <div className="flex items-center justify-between gap-2 border-t border-[#262a34]/40 pt-1"><dt className="text-[#bbcabf]">MatchForge Audit:</dt><dd><Badge value={row.agreement} /></dd></div>
                </dl>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function StateBar({ count, value, onChange }: { count: number; value: ViewMode; onChange: (mode: ViewMode) => void }) {
  return (
    <section className={`w-full border-b border-[#262a34] bg-[#1c1f29] px-4 py-1 text-[9px] ${mono}`} aria-label="Table state">
      <div className="mx-auto flex max-w-[1720px] flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2"><span className="uppercase tracking-wider text-[#86948a]">Terminal State View:</span><StateButton active={value === "live"} onClick={() => onChange("live")}>Live Feed ({fmt(count)})</StateButton><StateButton active={value === "empty"} onClick={() => onChange("empty")}>Empty State</StateButton><StateButton active={value === "loading"} onClick={() => onChange("loading")}>Ingestion Skeleton</StateButton></div>
        <div className="flex items-center gap-2 text-[#86948a]"><span>Display density: <strong>Compact 40px</strong></span><span>•</span><span>Deterministic sorting: <strong>Date DESC</strong></span></div>
      </div>
    </section>
  );
}

function StateButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return <button type="button" aria-pressed={active} onClick={onClick} className={`rounded-sm border px-2 py-0.5 ${active ? "border-[#4edea3]/40 bg-[#262a34] font-semibold text-[#4edea3]" : "border-[#262a34] bg-[#1c1f29] text-[#bbcabf] hover:text-[#dfe2ef]"}`}>{children}</button>;
}

function Results({ day, items, refreshing }: { day: string; items: ExternalPrediction[]; refreshing: boolean }) {
  return (
    <div className="overflow-hidden rounded-sm border border-[#262a34] bg-[#0a0e17]" aria-busy={refreshing}>
      <div className="overflow-x-auto" tabIndex={0} aria-label="External selection records table">
        <table className={`w-full min-w-[1180px] border-collapse text-left text-[10px] ${mono}`}>
          <thead><tr className="h-10 border-b border-[#262a34] bg-[#181b25] text-[9px] font-semibold uppercase tracking-wider text-[#bbcabf]"><TH><span className="flex items-center justify-between">Date (UTC)<span aria-hidden="true">↓</span></span></TH><TH>Source Provider</TH><TH>Competition</TH><TH>Fixture / Match</TH><TH className="text-center">Kickoff</TH><TH>Target Market</TH><TH>External Pick</TH><TH className="text-right">MF Prob. (%)</TH><TH className="text-center">Consensus Status</TH></tr></thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={item.id} className={`h-11 border-b border-[#262a34]/50 transition-colors hover:bg-[#262a34]/60 ${index % 2 ? "bg-[#181b25]/40" : "bg-[#0a0e17]"}`}>
                <TD className="text-[#86948a]">{collected(item.collected_at)}</TD>
                <TD><a href={item.source_page} target="_blank" rel="noreferrer" className="font-['Space_Grotesk',system-ui,sans-serif] font-semibold hover:text-[#7bd0ff]">{item.source}<span aria-hidden="true" className="ml-1 text-[#86948a]">↗</span><span className="sr-only"> (opens in new tab)</span></a></TD>
                <TD className="text-[#bbcabf]">{item.competition}</TD>
                <TD><strong className="font-['Space_Grotesk',system-ui,sans-serif] text-[15px] font-semibold">{item.home_team} <span className="font-normal text-[#86948a]">vs</span> {item.away_team}</strong></TD>
                <TD className="text-center text-[#86948a]">{kickoffTime(item.kickoff_at)}</TD>
                <TD className="text-[#bbcabf]">{market(item.market)}</TD>
                <TD><span className={`rounded-sm border border-[#353943] bg-[#1c1f29] px-2 py-0.5 font-semibold ${tone(item.agreement)}`}>{item.selection}</span></TD>
                <TD className={`text-right font-bold ${tone(item.agreement)}`}>{probability(item.matchforge_probability)}</TD>
                <TD className="text-center"><Badge value={item.agreement} /></TD>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={`flex flex-col items-center justify-between gap-2 border-t border-[#262a34] bg-[#181b25] px-4 py-1.5 text-[9px] text-[#86948a] sm:flex-row ${mono}`}>
        <span>All <strong className="text-[#dfe2ef]">{fmt(items.length)}</strong> selections for {day}</span>
      </div>
    </div>
  );
}

function SourceAudit({ sources }: { sources: ExternalSource[] }) {
  if (!sources.length) return null;
  const settled = sources.reduce((sum, item) => sum + item.settled_selections, 0);
  const correct = sources.reduce((sum, item) => sum + item.correct_selections, 0);

  return (
    <section id="source-audit" className="mt-3 w-full border-t border-[#262a34] bg-[#0a0e17] px-4 py-8" aria-labelledby="audit-title">
      <div className="mx-auto max-w-[1720px]">
        <header className="mb-1.5 flex flex-col justify-between gap-2 border-b border-[#262a34] pb-1 md:flex-row md:items-end">
          <div><h2 id="audit-title" className="flex items-center gap-2 text-lg font-semibold"><Icon name="verified" className="h-5 w-5 text-[#7bd0ff]" />Source Access &amp; Adapter Performance Audit</h2><p className="mt-1 max-w-4xl text-[12px] text-[#bbcabf]">Metrics reflect the active source, competition, market, country, continent, and selected-day filters.</p></div>
          <span className={`flex items-center gap-2 text-[9px] text-[#86948a] ${mono}`}>Selected day audit <span className="h-1.5 w-1.5 rounded-full bg-[#4edea3]" /></span>
        </header>

        <div className="overflow-hidden rounded-sm border border-[#262a34] bg-[#181b25]">
          <div className="overflow-x-auto" tabIndex={0} aria-label="Source adapter performance table">
            <table className={`w-full min-w-[1100px] border-collapse text-[10px] ${mono}`}>
              <thead><tr className="h-9 border-b border-[#262a34] bg-[#1c1f29] text-[9px] font-semibold uppercase tracking-wider text-[#bbcabf]"><TH>Source Provider</TH><TH>Access Status</TH><TH>Adapter Health</TH><TH className="text-right">Tracked</TH><TH className="text-right">Settled</TH><TH className="text-right">Correct</TH><TH className="text-right">Hit Rate</TH><TH className="text-right">MF Agreement</TH><TH>Known Issue / Advisory</TH></tr></thead>
              <tbody>
                {sources.map((item, index) => (
                  <tr key={item.code} className={`h-10 border-b border-[#262a34]/50 hover:bg-[#262a34]/50 ${index % 2 ? "bg-[#0a0e17]" : "bg-[#181b25]"}`}>
                    <TD><a href={item.url} target="_blank" rel="noreferrer" className="font-['Space_Grotesk',system-ui,sans-serif] font-semibold hover:text-[#7bd0ff]">{item.name}<span className="sr-only"> (opens in new tab)</span></a></TD>
                    <TD className="text-[#7bd0ff]">{status(item.automated_access_status)}</TD>
                    <TD className={item.adapter_status === "ENABLED" ? "text-[#4edea3]" : "text-amber-300"}><span aria-hidden="true">●</span> {status(item.adapter_status)}</TD>
                    <TD className="text-right">{fmt(item.tracked_selections)}</TD><TD className="text-right">{fmt(item.settled_selections)}</TD><TD className="text-right">{fmt(item.correct_selections)}</TD>
                    <TD className="text-right font-bold text-[#4edea3]">{probability(item.settled_hit_rate)}</TD><TD className="text-right font-bold text-[#7bd0ff]">{probability(item.matchforge_agreement_rate)}</TD><TD className="max-w-72 whitespace-normal text-[#86948a]">{item.known_issues}</TD>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className={`flex flex-col items-center justify-between gap-2 border-t border-[#262a34] bg-[#1c1f29] px-4 py-1.5 text-[9px] text-[#86948a] sm:flex-row ${mono}`}><span>Composite Registry Consensus: <strong>{settled ? probability(correct / settled) : "—"} Mean Hit Rate</strong> across {fmt(settled)} settled records.</span><span className="font-semibold text-[#4edea3]">CURRENT API RESPONSE</span></div>
        </div>
      </div>
    </section>
  );
}

function PredictionsFooter() {
  return <footer className={`flex w-full flex-col items-center justify-between gap-1 border-t border-[#262a34] bg-[#0a0e17] px-4 py-2 text-[9px] text-[#86948a] sm:flex-row ${mono}`}><span>MatchForge Quantitative Football Engine. Institutional Analytical Terminal.</span><span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-[#4edea3]" />External evidence isolated</span></footer>;
}

function Badge({ value }: { value: ExternalPrediction["agreement"] }) {
  const classes = value === "AGREES" ? "border-[#4edea3]/35 bg-emerald-950/30 text-[#4edea3]" : value === "WEAK_SUPPORT" ? "border-amber-400/35 bg-amber-950/20 text-amber-300" : value === "DISAGREES" ? "border-[#ffb4ab]/35 bg-rose-950/20 text-[#ffb4ab]" : "border-[#86948a]/40 bg-[#262a34] text-[#bbcabf]";
  return <span className={`inline-flex whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[9px] font-semibold ${classes} ${mono}`}><span aria-hidden="true">●</span>&nbsp;{agreement(value)}</span>;
}

function TH({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <th scope="col" className={`whitespace-nowrap border-r border-[#262a34]/60 px-3 py-2 ${className}`}>{children}</th>;
}

function TD({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <td className={`whitespace-nowrap border-r border-[#262a34]/40 px-3 py-2 ${className}`}>{children}</td>;
}

function ErrorState({ label, message, retry }: { label: string; message: string; retry: () => void }) {
  return <div role="alert" className="mx-auto flex max-w-[1720px] items-start justify-between gap-3 rounded-sm border border-[#ffb4ab]/30 bg-rose-950/15 p-3"><div><strong className="text-[#ffb4ab]">{label}</strong><p className="text-[#bbcabf]">{message}</p></div><button type="button" onClick={retry} className="rounded-sm bg-[#262a34] px-3 py-1.5">Retry</button></div>;
}

function Loading() {
  return <div role="status" className="space-y-3 overflow-hidden rounded-sm border border-[#262a34] bg-[#0a0e17] p-3"><span className="sr-only">Loading external selections</span><div className="flex justify-between border-b border-[#262a34] pb-2"><span className="h-4 w-48 animate-pulse rounded-sm bg-[#262a34]" /><span className="h-4 w-24 animate-pulse rounded-sm bg-[#262a34]" /></div>{Array.from({ length: 7 }, (_, index) => <div key={index} className="h-8 animate-pulse rounded-sm bg-[#181b25]" />)}</div>;
}

function EmptyState({ reset }: { reset: () => void }) {
  return <div className="flex min-h-80 flex-col items-center justify-center rounded-sm border border-[#262a34] bg-[#0a0e17] p-12 text-center"><span className="grid h-12 w-12 place-items-center rounded-full bg-[#262a34]"><Icon name="search" className="h-7 w-7 text-[#86948a]" /></span><h2 className="mt-3 text-lg font-semibold">No approved external selections</h2><p className="mt-1 max-w-lg text-[#bbcabf]">No external selections match the current day and filters. MatchForge collects only sources whose access and reuse conditions have been reviewed.</p><div className="mt-4 flex items-center gap-1.5"><button type="button" onClick={reset} className="rounded-sm bg-[#4edea3] px-3 py-1.5 font-semibold text-[#003824]">Reset All Filters</button><a href="#source-audit" className="rounded-sm bg-[#262a34] px-3 py-1.5 hover:bg-[#353943]">Review Source Registry</a></div></div>;
}

function buildPredictionQuery(day: string, filters: FacetFilters) {
  const query = new URLSearchParams({ date: day });
  appendFilters(query, filters);
  return query.toString();
}

function buildSourceQuery(day: string, filters: FacetFilters) {
  const query = new URLSearchParams({ date_from: day, date_to: day });
  appendFilters(query, filters);
  return query.toString();
}

function appendFilters(query: URLSearchParams, filters: FacetFilters) {
  Object.entries(filters).forEach(([key, value]) => {
    if (value) query.set(key, value);
  });
}

function consensusRows(items: ExternalPrediction[]) {
  const groups = new Map<string, ExternalPrediction[]>();
  items.forEach((item) => {
    const key = item.fixture_id ?? `${item.prediction_date}|${item.home_team}|${item.away_team}`;
    groups.set(key, [...(groups.get(key) ?? []), item]);
  });
  return [...groups.values()].map((group) => {
    const counts = new Map<string, number>();
    group.forEach((item) => counts.set(item.selection, (counts.get(item.selection) ?? 0) + 1));
    const [selection, count] = [...counts].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))[0];
    const row = group.find((item) => item.selection === selection) ?? group[0];
    return { id: row.fixture_id ?? `${row.prediction_date}|${row.home_team}|${row.away_team}`, fixture: `${row.home_team} vs ${row.away_team}`, kickoff: row.kickoff_at, selection, count, total: group.length, agreement: row.agreement };
  });
}

function utcToday() {
  return new Date().toISOString().slice(0, 10);
}

function addDays(value: string, amount: number) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}

function fmt(value: number) {
  return new Intl.NumberFormat("en-GB").format(value);
}

function probability(value: number | null) {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function collected(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-CA", { timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date).replace(",", "");
}

function kickoff(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function kickoffTime(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function agreement(value: ExternalPrediction["agreement"]) {
  return value === "UNABLE_TO_EVALUATE" ? "Unable to eval" : status(value);
}

function market(value: string) {
  return ({ RESULT_1X2: "1X2 Match Result", DOUBLE_CHANCE: "Double Chance", TOTAL_GOALS: "Total Goals O/U", BTTS: "Both Teams to Score" } as Record<string, string>)[value] ?? status(value);
}

function filterDisplay(key: keyof FacetFilters, value: string) {
  if (key === "market") return market(value);
  if (key === "agreement") return agreement(value as ExternalPrediction["agreement"]);
  return value;
}

function status(value: string) {
  return value.toLowerCase().replaceAll("_", " ").replace(/^./, (character) => character.toUpperCase());
}

function tone(value: ExternalPrediction["agreement"]) {
  if (value === "AGREES") return "text-[#4edea3]";
  if (value === "WEAK_SUPPORT") return "text-amber-300";
  if (value === "DISAGREES") return "text-[#ffb4ab]";
  return "text-[#86948a]";
}
