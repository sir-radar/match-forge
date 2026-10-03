import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PerformancePage } from "@/components/performance-page";

const competition = {
  id: "competition-1", name: "Premier League", country: "England", continent: "Europe",
  division: 1, type: "LEAGUE", season: "2026",
  availability: {
    fixtures: true, results: true, standings: true, h2h: true,
    forecast: true, xg: false, team_stats: true,
  },
  availability_status: "AVAILABLE", sources: {},
};

const performance = {
  competition_id: competition.id, league: competition.name, country: competition.country,
  continent: competition.continent, rating: "GOOD", forecasts: 86, outcome_hit_rate: 0.53,
  brier: 0.58, log_loss: 0.94, baseline_brier: 0.63, baseline_log_loss: 1.02,
  exact_score_rate: 0.12, top_three_score_rate: 0.31, top_five_score_rate: 0.45,
  total_goals_hit_rate: 0.54, btts_hit_rate: 0.51, latest_fifty_brier: 0.56,
  latest_fifty_log_loss: 0.91, latest_fifty_baseline_brier: 0.62,
  latest_fifty_baseline_log_loss: 1.01,
};

describe("PerformancePage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads performance and sends selected filters", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      return json(url.includes("/v1/competitions")
        ? { competitions: [competition] }
        : { performance: [performance] });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<PerformancePage />);

    expect(await screen.findByRole("rowheader", { name: /Premier League/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Continent"), { target: { value: "Europe" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("continent=Europe"), expect.any(Object),
    ));
    fireEvent.change(screen.getByLabelText("Rating"), { target: { value: "GOOD" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/continent=Europe.*rating=GOOD/), expect.any(Object),
    ));
  });

  it("shows the empty state", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => json(
      String(input).includes("/v1/competitions") ? { competitions: [] } : { performance: [] },
    )));
    render(<PerformancePage />);

    expect(await screen.findByText("No leagues match these filters")).toBeInTheDocument();
  });
});

function json(value: object) {
  return new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } });
}
