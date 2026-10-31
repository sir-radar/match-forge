"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ResolutionBatch } from "@/components/resolution-batch";
import { ResolutionDecisionForm } from "@/components/resolution-decision";
import { AdminNavigation } from "@/components/admin-navigation";
import { EmptyState, ResourceError, ResourceLoading } from "@/components/resource-state";
import { TableScroll } from "@/components/table-scroll";
import { resolutionApi, resolutionViews, text, type RecordValue, type ResolutionPage, type ResolutionView } from "@/lib/resolution";

type Filters = { q: string; provider: string; status: string; kind: string };
const EMPTY_FILTERS: Filters = { q: "", provider: "", status: "", kind: "" };
const VIEW_LABELS: Record<ResolutionView, string> = { identity: "Identity Review", fixtures: "Fixture Review", missing: "Missing Data", parity: "Migration Parity", cutover: "Cutover Controls", history: "Resolution History" };
const IDENTITY_STATUSES = ["VERIFIED", "NEEDS_REVIEW", "CONTRADICTORY", "UNRESOLVED", "BLOCKED"];
const FIXTURE_STATUSES = ["AUTO_ACCEPTED", "MANUAL_ACCEPTED", "REVIEW_REQUIRED"];
const HISTORY_STATUSES = ["ORIGIN_ANCHOR", "CROSSWALK", "REVOKED", "UNIQUE", "DUPLICATE_RESOLVED", "AMBIGUOUS_QUARANTINED", "IMPOSSIBLE_TEAM_SCHEDULE_QUARANTINED"];
const FILTER_OPTIONS: Record<ResolutionView, { statuses: string[]; entities: string[] }> = {
  identity: { statuses: IDENTITY_STATUSES, entities: ["team", "competition"] },
  fixtures: { statuses: [...IDENTITY_STATUSES, ...FIXTURE_STATUSES], entities: ["fixture"] },
  missing: { statuses: ["BLOCKED"], entities: ["resource", "dataset"] },
  parity: { statuses: ["PASS", "FAIL", "BLOCKED", "NOT_RUN"], entities: [] },
  cutover: { statuses: ["BLOCKED", "NOT_RUN"], entities: [] },
  history: { statuses: [...IDENTITY_STATUSES, ...FIXTURE_STATUSES, ...HISTORY_STATUSES], entities: ["team", "competition", "fixture"] },
};
const message = (error: unknown) => error instanceof Error ? error.message : "Resolution request unavailable";

function useResolutionPage(view: ResolutionView, filters: Filters, page: number) {
  const key = JSON.stringify([view, filters, page]);
  const [state, setState] = useState<{ key: string; data?: ResolutionPage; error?: string; loading: boolean }>({ key, loading: true });
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    const controller = new AbortController(), current = ++generation.current;
    const publish = (value: typeof state | ((old: typeof state) => typeof state)) => { if (!controller.signal.aborted && current === generation.current) setState(value); };
    queueMicrotask(() => publish((old) => ({ key, data: old.key === key ? old.data : undefined, loading: true })));
    const [selectedView, selectedFilters, selectedPage]: [ResolutionView, Filters, number] = JSON.parse(key);
    const query = new URLSearchParams({ ...selectedFilters, page: String(selectedPage), page_size: "20" });
    void resolutionApi.page(selectedView, query, controller.signal).then((data) => publish({ key, data, loading: false })).catch((error) => publish((old) => ({ ...old, key, loading: false, error: message(error) })));
    return () => controller.abort();
  }, [key, refresh]);
  const reload = useCallback(() => setRefresh((value) => value + 1), []);
  return { ...(state.key === key ? state : { key, loading: true }), reload };
}

export function ResolutionCenter() {
  const [view, setView] = useState<ResolutionView>("identity"), [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const toggle = (key: string) => setSelected((old) => old.includes(key) ? old.filter((value) => value !== key) : old.length < 20 ? [...old, key] : old);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [detail, setDetail] = useState<string | null>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const resource = useResolutionPage(view, filters, page);
  const changeView = (value: ResolutionView) => { setSelected([]); setDetail(null); setView(value); setPage(1); setFilters(EMPTY_FILTERS); };
  const changeFilter = (key: keyof Filters, value: string) => { setDetail(null); setPage(1); setFilters((current) => ({ ...current, [key]: value })); };
  const inspect = (key: string, button: HTMLButtonElement) => { opener.current = button; setDetail(key); };
  const history = (key: string) => { setView("history"); setPage(1); setFilters({ ...EMPTY_FILTERS, q: key }); setDetail(null); };
  return <div className="page sync-admin resolution-center">
    <AdminNavigation />
    <header className="page-heading"><div><small>Local operations</small><h1>Resolution Center</h1><p>Inspect identity cases, retained evidence, and migration blockers.</p></div></header>
    <nav aria-label="Resolution sections" className="resolution-nav">{resolutionViews.map((key) => <button key={key} aria-pressed={key === view} onClick={() => changeView(key)}>{VIEW_LABELS[key]}</button>)}</nav>
    <p className="resolution-notice">Inspect retained evidence and preview qualified identity decisions. Production cutover and legacy retirement require complete parity and explicit owner acceptance. A recorded exception does not establish parity.</p>
    <CaseFilters view={view} filters={filters} update={changeFilter} loading={resource.loading} reload={resource.reload} />
    {resource.error && <ResourceError message={resource.error} retry={resource.reload} />}
    {resource.loading && <ResourceLoading label={resource.data ? "Refreshing cases" : "Loading cases"} />}
    {resource.data && <CaseResults selected={selected} toggle={toggle} data={resource.data} view={view} page={page} loading={resource.loading} inspect={inspect} changePage={(value) => { setDetail(null); setPage(value); }} />}
    {!!selected.length && <><button onClick={() => setSelected([])}>Clear selected cases</button><ResolutionBatch key={selected.join(",")} keys={selected} onApplied={resource.reload} /></>}
    {detail && <CaseReview key={detail} caseKey={detail} onApplied={resource.reload} close={() => { setDetail(null); opener.current?.focus(); }} history={history} />}
  </div>;
}

function CaseFilters({ view, filters, update, loading, reload }: { view: ResolutionView; filters: Filters; update: (key: keyof Filters, value: string) => void; loading: boolean; reload: () => void }) {
  const options = FILTER_OPTIONS[view], migration = !options.entities.length;
  return <form className="sync-controls" onSubmit={(event) => event.preventDefault()} aria-label="Case filters">
    <label>Search<input type="search" value={filters.q} onChange={(event) => update("q", event.target.value)} /></label>
    {!migration && <label>Provider<input value={filters.provider} onChange={(event) => update("provider", event.target.value)} /></label>}
    <label>Status<select value={filters.status} onChange={(event) => update("status", event.target.value)}><option value="">All statuses</option>{options.statuses.map((status) => <option key={status}>{status}</option>)}</select></label>
    {!migration && <label>Entity<select value={filters.kind} onChange={(event) => update("kind", event.target.value)}><option value="">All entities</option>{options.entities.map((kind) => <option key={kind}>{kind}</option>)}</select></label>}
    <button type="button" disabled={loading} onClick={reload}>Recheck current view</button>
  </form>;
}

function CaseResults({ data, view, page, loading, inspect, changePage, selected, toggle }: { selected: string[]; toggle: (key: string) => void; data: ResolutionPage; view: ResolutionView; page: number; loading: boolean; inspect: (key: string, button: HTMLButtonElement) => void; changePage: (page: number) => void }) {
  return <>
    <p role="status">{data.total.toLocaleString()} cases in this scope. {Object.entries(data.counts).map(([status, count]) => `${status}: ${count.toLocaleString()}`).join(" · ")}</p>
    {data.scope && <p className="resolution-scope">{data.scope.replaceAll("_", " ")}</p>}
    {!!data.blockers?.length && <details><summary>Required migration blockers ({data.blockers.length})</summary><ul>{data.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul></details>}
    {!!data.groups.length && <CaseGroups groups={data.groups} />}
    {!data.items.length ? <EmptyState title="No cases in this scope" detail="Change the filters or recheck after new evidence arrives." /> : <CaseTable selected={selected} toggle={toggle} selectable={["identity", "fixtures"].includes(view)} items={data.items} inspectable={["identity", "fixtures", "missing"].includes(view)} inspect={inspect} />}
    <div className="resolution-pagination"><button disabled={page <= 1 || loading} onClick={() => changePage(page - 1)}>Previous page</button><span>Page {page}</span><button disabled={page * data.page_size >= data.total || loading} onClick={() => changePage(page + 1)}>Next page</button></div>
  </>;
}

function CaseGroups({ groups }: { groups: RecordValue[] }) {
  return <details><summary>Grouped backlog (up to 100 groups; cases can span seasons)</summary><TableScroll label="Case groups"><table><thead><tr><th>Provider</th><th>Entity</th><th>Country</th><th>Competition / season</th><th>Status</th><th>Reason</th><th>Count</th></tr></thead><tbody>{groups.map((group, index) => <tr key={index}><td>{text(group.provider)}</td><td>{text(group.kind)}</td><td>{text(group.country)}</td><td>{text(group.competition_id)} / {text(group.season_id)}</td><td>{text(group.status)}</td><td>{text(group.reason)}</td><td>{String(group.count)}</td></tr>)}</tbody></table></TableScroll></details>;
}

function CaseTable({ items, inspectable, inspect, selected, toggle, selectable }: { selected: string[]; toggle: (key: string) => void; selectable: boolean; items: RecordValue[]; inspectable: boolean; inspect: (key: string, button: HTMLButtonElement) => void }) {
  return <TableScroll label="Resolution cases"><table><thead><tr>{selectable && <th>Select</th>}<th>Case</th><th>Provider</th><th>Status</th><th>Reason / next action</th><th>Review</th></tr></thead><tbody>{items.map((item, index) => {
    const key = text(item.case_key);
    return <tr key={`${key}:${text(item.event_id)}`}>{selectable && <td><input type="checkbox" aria-label={`Select ${key}`} checked={selected.includes(key)} disabled={!selected.includes(key) && selected.length >= 20} onChange={() => toggle(key)} /></td>}<td>{typeof item.name === "string" ? item.name : key}{typeof item.name === "string" && <small className="resolution-id">{key}</small>}</td><td>{text(item.provider)}</td><td>{text(item.status)}</td><td>{text(item.reason === undefined ? item.next_action : item.reason)}</td><td>{inspectable ? <button onClick={(event) => inspect(key, event.currentTarget)}>Inspect case {index + 1}</button> : <details><summary>Inspect evidence {index + 1}</summary><Evidence value={item} /></details>}</td></tr>;
  })}</tbody></table></TableScroll>;
}

function CaseReview({ caseKey, close, history, onApplied }: { onApplied: () => void; caseKey: string; close: () => void; history: (key: string) => void }) {
  const [data, setData] = useState<RecordValue>(), [error, setError] = useState<string>();
  const [retry, setRetry] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    void resolutionApi.detail(caseKey, controller.signal).then((value) => { if (!controller.signal.aborted) { setData(value); setError(undefined); heading.current?.focus(); } }).catch((cause) => { if (!controller.signal.aborted) { setError(message(cause)); heading.current?.focus(); } });
    return () => controller.abort();
  }, [caseKey, retry]);
  return <section aria-label="Case review" className="resolution-review">
    <h2 tabIndex={-1} ref={heading}>Review {caseKey}</h2><button onClick={close}>Close case</button><button onClick={() => setRetry((value) => value + 1)}>Recheck case evidence</button><button onClick={() => history(caseKey)}>Show resolution history</button>
    {error && <ResourceError message={error} retry={() => { setError(undefined); setRetry((value) => value + 1); }} />}
    {!data && !error && <ResourceLoading label="Loading retained evidence" />}
    {data && <><p>Status: {text(data.status)}</p><Evidence value={data} />{["team", "competition", "fixture", "fixture_record"].includes(caseKey.split(":")[0]) && <ResolutionDecisionForm caseKey={caseKey} data={data} onApplied={() => { onApplied(); setRetry((value) => value + 1); }} />}</>}
  </section>;
}

function Evidence({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span>Not recorded</span>;
  if (Array.isArray(value)) return value.length ? <ul>{value.map((item, index) => <li key={index}><Evidence value={item} /></li>)}</ul> : <span>None</span>;
  if (typeof value === "object") return <dl className="resolution-evidence">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{item !== null && typeof item === "object" ? <details><summary>Inspect {key.replaceAll("_", " ")}</summary><Evidence value={item} /></details> : <Evidence value={item} />}</dd></div>)}</dl>;
  return <span>{String(value)}</span>;
}
