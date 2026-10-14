import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ForecastHistory } from "@/components/forecast-history";
import { parseForecastHistory } from "@/lib/contracts";
import { api } from "@/lib/api";

function revision(id: string, home = .6) {
  return { forecast_id: id, fixture_id: "fixture", issued_at: "2026-10-13T08:00:00Z", football_cutoff: "2026-10-13T08:00:00Z", knowledge_cutoff: "2026-10-13T08:00:00Z", forecast_horizon: "24H", supersedes_forecast_id: null, model_id: "transferable-rolling-goals-poisson-v1", artifact_sha256: "a".repeat(64), predictive_input_snapshot_sha256: "b".repeat(64), context_snapshot_sha256: "c".repeat(64), payload_sha256: "d".repeat(64), revision_reason_codes: ["INITIAL_FORECAST"], new_information_ids: [], probability_payload: { expected_home_goals: 1.5, expected_away_goals: 1.1, probabilities: { home, draw: .2, away: 1 - home - .2 }, score_matrix_version: "legacy-compact-index-v1", score_matrix: [{ home_goals: 5, away_goals: 0, probability: .1 }] } };
}

describe("forecast history", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("displays original revisions with current and selected distinction and full lineage", async () => {
    const old = revision("old", .4), current = { ...revision("current"), supersedes_forecast_id: "old" };
    const original = JSON.stringify({ forecasts: [old, current] });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(original, { status: 200 })));
    render(<ForecastHistory fixtureId="fixture" currentId="current" />);
    expect(screen.getByText("Loading forecast history")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "View revision current" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "View revision old" }));
    expect(screen.getByRole("button", { name: "View revision old" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("old · Historical revision")).toBeInTheDocument();
    expect(screen.getAllByText(/40.0%/).length).toBeGreaterThan(0);
    expect(screen.getByText("b".repeat(64))).toBeInTheDocument();
    expect(JSON.stringify({ forecasts: [old, current] })).toBe(original);
  });
  it("shows empty, failure and retry states", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response('{"error":"history unavailable"}', { status: 503 })).mockResolvedValue(new Response('{"forecasts":[]}', { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    render(<ForecastHistory fixtureId="fixture" currentId={null} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("history unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No published revisions")).toBeInTheDocument();
  });
  it("rejects malformed lineage and labels while preserving legacy bucket interpretation", () => {
    const row = revision("legacy");
    expect(parseForecastHistory({ forecasts: [row] })[0].probability_payload.score_matrix[0].home_label).toBe("5+");
    expect(() => parseForecastHistory({ forecasts: [{ ...row, artifact_sha256: "bad" }] })).toThrow(/artifact/);
    expect(() => parseForecastHistory({ forecasts: [{ ...row, issued_at: "bad" }] })).toThrow(/timestamp/);
    expect(() => parseForecastHistory({ forecasts: [{ ...row, probability_payload: { ...row.probability_payload, score_matrix_version: "unknown" } }] })).toThrow(/version/);
  });
  it("encodes an untrusted fixture segment without changing the API origin", async () => {
    const fixture = "https://untrusted.example/a?redirect=/other#fragment";
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => new Response('{"forecasts":[]}', { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.forecastHistory(fixture);
    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.origin).toBe(new URL(process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8080").origin);
    expect(url.pathname).toBe(`/v1/fixtures/${encodeURIComponent(fixture)}/forecasts`);
    expect(url.search).toBe("");
    expect(url.hash).toBe("");
  });
  it("rejects a revision belonging to another fixture", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ forecasts: [revision("other")] }), { status: 200 })));
    await expect(api.forecastHistory("requested-fixture")).rejects.toThrow("forecast history fixture mismatch");
  });
});
