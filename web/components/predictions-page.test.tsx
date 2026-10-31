import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PredictionsPage } from "@/components/predictions-page";

const source = {
  code: "tactical-quant",
  name: "TacticalQuant Lab",
  url: "https://example.com/source",
  public_predictions: true,
  prediction_date_available: true,
  login_required: false,
  paid_content: false,
  automated_access_status: "ALLOWED",
  adapter_status: "ENABLED",
  known_issues: "None",
  checked_at: "2026-09-28T04:00:00Z",
  tracked_selections: 482,
  settled_selections: 410,
  correct_selections: 246,
  settled_hit_rate: 0.6,
  matchforge_agreement_rate: 0.642,
};

const prediction = {
  id: "prediction-1",
  source: source.name,
  source_page: source.url,
  prediction_date: "2026-09-28",
  original_date_text: "28 Sep 2026",
  collected_at: "2026-09-28T08:15:00Z",
  fixture_id: "fixture-1",
  kickoff_at: "2026-09-28T15:00:00Z",
  competition: "Premier League",
  home_team: "Arsenal",
  away_team: "Chelsea",
  market: "RESULT_1X2",
  selection: "Home Win (Arsenal)",
  match_status: "MATCHED",
  matchforge_probability: 0.439,
  agreement: "AGREES",
};

describe("PredictionsPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.includes("external-prediction-sources")
        ? { sources: [source] }
        : predictionPage([prediction]);
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("labels actual request state and capture/kickoff clocks without simulated controls", async () => {
    render(<PredictionsPage initialDate="2026-09-28" />);
    expect(await screen.findByText("Records: Loaded")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /First capture \(Africa\/Lagos\)/ })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Kickoff \(Africa\/Lagos\)/ })).toBeInTheDocument();
    expect(screen.queryByText(/Cluster Synced|Feed: Live|UTC\+0 London/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Empty State|Ingestion Skeleton/ })).not.toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "2026-09-28 09:15" })).toBeInTheDocument();
  });
  it("renders API-backed metrics, consensus, selections, and source audit", async () => {
    render(<PredictionsPage initialDate="2026-09-28" />);

    expect(screen.getByRole("heading", { name: "External predictions" })).toBeInTheDocument();
    expect(await screen.findByRole("cell", { name: "Arsenal vs Chelsea" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Multi-Source External Consensus" })).not.toBeInTheDocument();
    expect(screen.getByText("43.9%")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /TacticalQuant Lab/ })[0]).toHaveAttribute("href", source.url);
    expect(screen.getByRole("heading", { name: "Source Access & Adapter Performance Audit" })).toBeInTheDocument();
    expect(screen.getByText("64.2%")).toBeInTheDocument();
    expect(screen.getByText("0.0%", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByLabelText("Prediction day")).toHaveValue("2026-09-28");
    expect(screen.getByRole("option", { name: "Unmapped Provider Market" })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("external-predictions?date=2026-09-28"),
      expect.any(Object),
    );
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/external-prediction-sources\?.*date_from=2026-09-28.*date_to=2026-09-28/),
      expect.any(Object),
    );
  });

  it("keeps a small selected-day result on one bounded page", async () => {
    const dailyPredictions = Array.from({ length: 9 }, (_, index) => ({
      ...prediction,
      id: `prediction-${index + 1}`,
      fixture_id: `fixture-${index + 1}`,
      home_team: `Home ${index + 1}`,
      away_team: `Away ${index + 1}`,
      collected_at: `2026-09-28T${String(index).padStart(2, "0")}:15:00Z`,
    }));
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
      const payload = String(input).includes("external-prediction-sources")
        ? { sources: [source] }
        : predictionPage(dailyPredictions);
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    render(<PredictionsPage initialDate="2026-09-28" />);

    const table = await screen.findByLabelText("External selection records table");
    expect(table.querySelectorAll("tbody tr")).toHaveLength(9);
    expect(table.parentElement).toHaveTextContent("9 selections on this page");
    expect(screen.getByText(/Page 1 of 1/)).toBeInTheDocument();
  });

  it("uses server consensus independently of the visible record page", async () => {
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
      const payload = String(input).includes("external-prediction-sources") ? { sources: [source] } : {
        ...predictionPage([prediction], 1, 20, 25),
        consensus: [{ id: "other:RESULT_1X2", fixture: "Verified Home vs Verified Away", market: "RESULT_1X2", kickoff: "2026-09-28T15:00:00Z", selection: "HOME_WIN", count: 2, total: 3, agreement: "AGREES" }],
      };
      return new Response(JSON.stringify(payload), { status: 200 });
    });
    render(<PredictionsPage initialDate="2026-09-28" />);
    expect(await screen.findByText("Verified Home vs Verified Away")).toBeInTheDocument();
    expect(screen.getByText("2 of 3 sources (67%)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("page=2&page_size=20"), expect.any(Object)));
  });

  it("moves one day at a time and keeps the table scoped to that day", async () => {
    render(<PredictionsPage initialDate="2026-09-28" />);
    await screen.findByRole("cell", { name: "Arsenal vs Chelsea" });

    fireEvent.click(screen.getByRole("button", { name: "Previous day" }));

    expect(screen.getByLabelText("Prediction day")).toHaveValue("2026-09-27");
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("external-predictions?date=2026-09-27"),
        expect.any(Object),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Next day" }));
    expect(screen.getByLabelText("Prediction day")).toHaveValue("2026-09-28");
  });

  it("applies live filters and resets them without removing the daily scope", async () => {
    render(<PredictionsPage initialDate="2026-09-28" />);
    await screen.findByRole("cell", { name: "Arsenal vs Chelsea" });

    fireEvent.change(screen.getByLabelText("Competition"), { target: { value: "Premier League" } });
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("competition=Premier+League"),
        expect.any(Object),
      );
    });
    expect(screen.getByText("Comp:")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getByLabelText("Competition")).toHaveValue("");
    expect(screen.queryByText("Comp:")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Prediction day")).toHaveValue("2026-09-28");
  });
});

function predictionPage(items: Record<string, unknown>[], page = 1, pageSize = 20, total = items.length) {
  return { predictions: items, consensus: [], pagination: { page, page_size: pageSize, total_items: total, total_pages: Math.ceil(total / pageSize) } };
}
