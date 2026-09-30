import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FixtureExplorer } from "@/components/fixture-explorer";

const competition = {
  id: "league-1", name: "Premier League", country: "England", continent: "Europe", division: 1,
  type: "LEAGUE", season: "2026", availability: { fixtures: true, results: true, standings: true, h2h: true, forecast: true, xg: false, team_stats: false },
  availability_status: "FORECAST_AVAILABLE", sources: { fixtures: ["api_football"] },
};

const fixture = {
  id: "fixture-1", kickoff_at: "2026-09-29T15:00:00Z", status: "SCHEDULED", home: { id: "home", name: "Arsenal", crest_url: null },
  away: { id: "away", name: "Chelsea", crest_url: null }, home_score: null, away_score: null, venue: "Emirates Stadium", round: "Round 6",
  forecast_availability: "FORECAST_AVAILABLE", forecast: { id: "forecast-1", expected_home_goals: 1.5, expected_away_goals: 1.1, probabilities: { home: .46, draw: .27, away: .27 } },
};

const forecast = { ...fixture.forecast, fixture_id: fixture.id, model_label: "MVP_FORECAST", model_algorithm_version: "transferable-rolling-goals-poisson-v1", created_at: "2026-09-29T06:00:00Z", football_cutoff: "2026-09-29T06:00:00Z", knowledge_cutoff: "2026-09-29T06:00:00Z", knowledge_mode: "bitemporal", publication_mode: "MVP_OWNER_AUTHORIZED", score_matrix: [{ home_goals: 1, away_goals: 0, probability: .14 }] };
const context = { fixture_id: fixture.id, home_form: [], away_form: [], h2h: [], h2h_summary: { meetings: 0, home_wins: 0, draws: 0, away_wins: 0, home_goals: 0, away_goals: 0 }, home_team_statistics: null, away_team_statistics: null, standings: [], data_availability: { recent_form: false, h2h: false, standings: false, team_stats: false } };

describe("FixtureExplorer", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.includes("/v1/competitions?") ? { competitions: [competition] }
        : url.includes("/v1/fixtures?") ? { date: "2026-09-29", groups: [{ competition, fixtures: [fixture] }] }
        : url.includes("/context") ? context
        : url.includes("/forecasts/") ? forecast
        : url.includes("external-predictions") ? { predictions: [] }
        : {};
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("renders the dense fixture list and expands the match inline", async () => {
    render(<FixtureExplorer initialDate="2026-09-29" />);
    const row = await screen.findByRole("button", { name: /Arsenal.*Chelsea/s });
    expect(screen.getByText("England — Premier League")).toBeInTheDocument();
    expect(row).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("tab", { name: "Score matrix" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Forecast record")).toBeInTheDocument());
  });

  it("keeps unavailable fixtures visible without invented probabilities", async () => {
    const unavailable = { ...fixture, id: "fixture-2", forecast: null, forecast_availability: "NOT_ENOUGH_HISTORY" };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = String(input).includes("competitions") ? { competitions: [competition] } : { groups: [{ competition, fixtures: [unavailable] }] };
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
    render(<FixtureExplorer initialDate="2026-09-29" />);
    expect(await screen.findByText("Not enough history", { selector: ".availability" })).toBeInTheDocument();
    expect(screen.getByText("Arsenal")).toBeInTheDocument();
  });
});
