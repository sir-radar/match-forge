"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { useResource } from "@/hooks/use-resource";
import { EmptyState, ResourceError, ResourceLoading } from "@/components/resource-state";
import { percent, ProbabilityBar } from "@/components/probability-bar";

export function ForecastHistory({ fixtureId, currentId }: { fixtureId: string; currentId: string | null }) {
  const load = useCallback((signal: AbortSignal) => api.forecastHistory(fixtureId, signal), [fixtureId]);
  const history = useResource(`forecast-history-${fixtureId}`, load);
  const [selectedId, setSelectedId] = useState(currentId);
  if (history.loading) return <ResourceLoading label="Loading forecast history" />;
  if (history.error) return <ResourceError message={history.error} retry={history.retry} />;
  if (!history.data?.length) return <EmptyState title="No published revisions" detail="No immutable forecast history is stored for this fixture." />;
  const selected = history.data.find((row) => row.forecast_id === selectedId) ?? history.data.at(-1)!;
  const forecast = selected.probability_payload;
  return <section className="panel forecast-history" aria-label="Published forecast revisions">
    <p>Each row is an immutable published forecast. Selecting an older revision displays its original values; the fixture’s current forecast remains unchanged.</p>
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Forecast revisions table"><table><caption className="sr-only">Immutable forecast revision history</caption><thead><tr><th>Revision</th><th>Issued (UTC)</th><th>Model/version</th><th>Home / Draw / Away</th><th>Selection</th></tr></thead><tbody>{history.data.map((row) => <tr key={row.forecast_id}><th scope="row">{row.forecast_id}{row.forecast_id === currentId && <small> · Current fixture revision</small>}</th><td>{new Date(row.issued_at).toISOString()}</td><td>{row.model_id}</td><td>{[row.probability_payload.probabilities.home, row.probability_payload.probabilities.draw, row.probability_payload.probabilities.away].map(percent).join(" / ")}</td><td><button type="button" aria-pressed={row.forecast_id === selected.forecast_id} onClick={() => setSelectedId(row.forecast_id)}>View revision {row.forecast_id}</button></td></tr>)}</tbody></table></div>
    <h4>Selected published revision</h4><p>{selected.forecast_id}{selected.forecast_id === currentId ? " · Current fixture revision" : " · Historical revision"}</p>
    <ProbabilityBar values={forecast.probabilities} />
    <p>Expected goals: {forecast.expected_home_goals.toFixed(2)} / {forecast.expected_away_goals.toFixed(2)}</p>
    <dl>{Object.entries({ "Issued (UTC)": selected.issued_at, "Football cutoff": selected.football_cutoff, "Knowledge cutoff": selected.knowledge_cutoff, Horizon: selected.forecast_horizon, "Model/version": selected.model_id, "Supersedes": selected.supersedes_forecast_id ?? "None", "Artifact SHA-256": selected.artifact_sha256, "Predictive input SHA-256": selected.predictive_input_snapshot_sha256, "Context SHA-256": selected.context_snapshot_sha256, "Payload SHA-256": selected.payload_sha256, Reasons: selected.revision_reason_codes.join(", "), "New information": selected.new_information_ids.join(", ") || "None" }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
  </section>;
}
