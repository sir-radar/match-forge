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
        : performancePage([performance]));
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
      String(input).includes("/v1/competitions") ? { competitions: [] } : performancePage([]),
    )));
    render(<PerformancePage />);

    expect(await screen.findByText("No leagues match these filters")).toBeInTheDocument();
  });

  it("requests and renders backend-driven pages", async () => {
    const items = Array.from({ length: 45 }, (_, index) => ({
      ...performance,
      competition_id: `competition-${index + 1}`,
      league: `League ${index + 1}`,
    }));
    const requestedUrls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/v1/competitions")) return json({ competitions: [competition] });
      requestedUrls.push(url);
      const query = new URL(url).searchParams;
      const page = Number(query.get("page"));
      const pageSize = Number(query.get("page_size"));
      const start = (page - 1) * pageSize;
      return json(performancePage(items.slice(start, start + pageSize), page, pageSize, items.length));
    }));
    render(<PerformancePage />);

    expect(await screen.findByRole("rowheader", { name: /League 1$/ })).toBeInTheDocument();
    expect(screen.getAllByRole("rowheader")).toHaveLength(20);
    expect(screen.getByText("Showing 1–20 of 45 · Page 1 of 3")).toBeInTheDocument();
    expect(requestedUrls[0]).toContain("page=1&page_size=20");

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("rowheader", { name: /League 21$/ })).toBeInTheDocument();
    expect(screen.getByText("Showing 21–40 of 45 · Page 2 of 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("rowheader", { name: /League 41$/ })).toBeInTheDocument();
    expect(screen.getAllByRole("rowheader")).toHaveLength(5);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Rows per page"), { target: { value: "50" } });
    await waitFor(() => expect(screen.getAllByRole("rowheader")).toHaveLength(45));
    expect(screen.getByText("Showing 1–45 of 45 · Page 1 of 1")).toBeInTheDocument();
    expect(requestedUrls.at(-1)).toContain("page=1&page_size=50");
  });

  it("returns to page one when filters change", async () => {
    const items = Array.from({ length: 25 }, (_, index) => ({
      ...performance, competition_id: `competition-${index + 1}`, league: `League ${index + 1}`,
    }));
    const requestedUrls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/v1/competitions")) return json({ competitions: [competition] });
      requestedUrls.push(url);
      const query = new URL(url).searchParams;
      const page = Number(query.get("page"));
      const pageSize = Number(query.get("page_size"));
      const start = (page - 1) * pageSize;
      return json(performancePage(items.slice(start, start + pageSize), page, pageSize, items.length));
    }));
    render(<PerformancePage />);

    await screen.findByRole("rowheader", { name: /League 1$/ });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("rowheader", { name: /League 21$/ });
    fireEvent.change(screen.getByLabelText("Rating"), { target: { value: "GOOD" } });
    await waitFor(() => expect(requestedUrls.at(-1)).toMatch(/page=1.*page_size=20.*rating=GOOD/));
  });

  it("adopts a backend-clamped page after the result set shrinks", async () => {
    const items = Array.from({ length: 25 }, (_, index) => ({
      ...performance, competition_id: `competition-${index + 1}`, league: `League ${index + 1}`,
    }));
    const requestedPages: number[] = [];
    let shrunk = false;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/v1/competitions")) return json({ competitions: [competition] });
      const requestedPage = Number(new URL(url).searchParams.get("page"));
      requestedPages.push(requestedPage);
      if (requestedPage === 2) shrunk = true;
      return json(shrunk
        ? performancePage(items.slice(0, 20), 1, 20, 20)
        : performancePage(items.slice(0, 20), 1, 20, 25));
    }));
    render(<PerformancePage />);

    await screen.findByText("Showing 1–20 of 25 · Page 1 of 2");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("Showing 1–20 of 20 · Page 1 of 1");
    await waitFor(() => expect(requestedPages).toEqual([1, 2, 1]));
  });
});

function performancePage(items: typeof performance[], page = 1, pageSize = 20, totalItems = items.length) {
  return {
    performance: items,
    pagination: { page, page_size: pageSize, total_items: totalItems, total_pages: totalItems === 0 ? 0 : Math.ceil(totalItems / pageSize) },
  };
}

function json(value: object) {
  return new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } });
}
