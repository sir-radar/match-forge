"use client";

import { useCallback, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { MARKET_GROUPS, type MarketCapabilitySummary, type MarketScope } from "@/lib/contracts";
import { useResource } from "@/hooks/use-resource";
import { EmptyState, ResourceError, ResourceLoading } from "@/components/resource-state";
import { TableScroll } from "@/components/table-scroll";
import styles from "./market-readiness-admin.module.css";

const groups: Record<typeof MARKET_GROUPS[number], string> = { GOALS: "Results and goals", PERIODS: "Halves", CORNERS: "Corners", CARDS: "Cards", TEAM_STATISTICS: "Shots and team statistics", PLAYERS: "Players", JOINT: "Combinations" };
const uuid = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}";

export function MarketReadinessAdmin() {
  const [scope, setScope] = useState<MarketScope | null>(null);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setScope({ competition_id: String(data.get("competition_id")).trim().toLowerCase(), season_id: String(data.get("season_id")).trim().toLowerCase(), knowledge_cutoff: String(data.get("knowledge_cutoff") || new Date().toISOString()).trim() });
  };
  return <section className={`coverage-panel market-readiness ${styles.root}`} aria-labelledby="market-readiness-title">
    <header><div><small>Registered evidence</small><h2 id="market-readiness-title">Market readiness</h2></div></header>
    <p>Inspect one canonical competition and season at a knowledge cutoff. This diagnostic does not approve markets, publish probabilities or change existing forecasts. Identity decisions remain in the <a href="/admin/resolution">Resolution Center</a>.</p>
    <form className="sync-controls" onSubmit={submit}>
      <label>Competition ID<input name="competition_id" required pattern={uuid} placeholder="Canonical UUID" /></label>
      <label>Season ID<input name="season_id" required pattern={uuid} placeholder="Canonical UUID" /></label>
      <label>Knowledge cutoff<input name="knowledge_cutoff" placeholder="ISO time with timezone; blank uses request time" /></label>
      <button type="submit">Inspect market readiness</button>
    </form>
    {scope ? <ScopedReadiness scope={scope} /> : <p>Choose a scope to inspect qualified history, source gaps, model metadata and settlement readiness.</p>}
  </section>;
}

function ScopedReadiness({ scope }: { scope: MarketScope }) {
  const load = useCallback((signal: AbortSignal) => api.marketCapabilities(scope, signal), [scope]);
  const report = useResource(JSON.stringify(scope), load);
  return <div aria-label="Scoped market readiness">
    {report.loading && <ResourceLoading label="Loading market readiness" />}
    {report.refreshing && <p role="status">Refreshing market readiness…</p>}
    {report.error && <ResourceError message={report.error} retry={report.retry} />}
    {report.data && <ReadinessReport report={report.data} />}
  </div>;
}

function ReadinessReport({ report }: { report: MarketCapabilitySummary }) {
  return <>
    <p>Knowledge cutoff: <time>{report.knowledge_cutoff}</time>. Snapshot: <time>{report.recorded_at}</time>. Forecast horizon: not applicable to unbound market families.</p>
    <p role="status">Diagnostic only. Model metadata is not target qualification. The current configured registration is shown for traceability. Research and shadow results are not qualified production probabilities.</p>
    <p>New market settlement: not implemented. Monitoring supports existing published goal forecasts only; this does not confirm an active worker. Automatic promotion is disabled.</p>
    {!report.markets.length && <EmptyState title="No target definitions returned" detail="This does not establish that any market is supported." />}
    {MARKET_GROUPS.map((group) => {
      const rows = report.markets.filter((row) => row.group === group);
      if (!rows.length) return null;
      return <details key={group}><summary>{groups[group]} — {rows.length} target families</summary>
        <TableScroll label={`${groups[group]} readiness`}><table><thead><tr><th scope="col">Target</th><th scope="col">Readiness and missing inputs</th><th scope="col">Model metadata</th><th scope="col">Semantics and publication</th></tr></thead><tbody>{rows.map((row) => <tr key={row.market_id}>
          <th scope="row">{row.market_id}</th>
          <td><b>{row.status}</b><p>{row.unavailable_reason ?? "No diagnostic blocker reported; this is not publication approval."}</p><p>Unqualified inputs: {row.unqualified_inputs.join(", ") || "None listed; sufficiency and semantic gates still apply."}</p><p>{row.next_action}</p></td>
          <td>{row.model_id ? <><b>{row.model_id}</b><p>{row.model_version} · {row.model_role}</p><details><summary>Artifact checksum</summary><code>{row.model_artifact_sha256}</code></details></> : "No configured model metadata for this family"}</td>
          <td>{row.semantic_version}<p>Source compatibility: {row.source_compatibility}</p><p>Evaluation: {row.evaluation_status}. Current publication: {row.publication_status}.</p><p>Eligible under declared evidence: {row.publication_eligible ? "Yes; no new publication granted" : "No"}.</p></td>
        </tr>)}</tbody></table></TableScroll>
      </details>;
    })}
    <details><summary>Provider resource candidates — {report.provider_candidates.length}</summary><p>These native resource candidates are not verified for this canonical scope. Access is separate from field coverage, historical eligibility and target qualification.</p>{report.provider_candidates.length ? <ul>{report.provider_candidates.map((source) => <li key={`${source.provider}:${source.resource}:${source.availability}`}>{source.provider} · {source.resource} · {source.availability}</li>)}</ul> : <p>No registered candidate resources at this cutoff. Source availability remains unknown.</p>}</details>
    <details><summary>Diagnostic limitations</summary><ul>{report.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details>
  </>;
}
