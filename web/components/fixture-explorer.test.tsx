import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FixtureExplorer } from "@/components/fixture-explorer";
import { parseFixtureGroups, parseForecast } from "@/lib/contracts";
import { ExpandedFixture } from "@/components/expanded-fixture";

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

const forecast = { ...fixture.forecast, probabilities: { ...fixture.forecast.probabilities, total_over_2_5: .51, total_under_2_5: .49, btts_yes: .55, home_clean_sheet: .33, away_clean_sheet: .22 }, fixture_id: fixture.id, model_label: "MVP_FORECAST", model_algorithm_version: "transferable-rolling-goals-poisson-v1", created_at: "2026-09-29T06:00:00Z", football_cutoff: "2026-09-29T06:00:00Z", knowledge_cutoff: "2026-09-29T06:00:00Z", knowledge_mode: "bitemporal", publication_mode: "MVP_OWNER_AUTHORIZED", score_matrix: [{ home_goals: 1, away_goals: 0, probability: .14 }] };
const context = { fixture_id: fixture.id, home_form: [], away_form: [], h2h: [], h2h_summary: { meetings: 0, home_wins: 0, draws: 0, away_wins: 0, home_goals: 0, away_goals: 0 }, home_team_statistics: null, away_team_statistics: null, standings: [], data_availability: { recent_form: false, h2h: false, standings: false, team_stats: false } };
const liveMatch = {
  fixture_id: fixture.id, status: "FINISHED", home: fixture.home, away: fixture.away,
  home_score: 2, away_score: 1, match_minute: null, added_time: null, period: "FULL_TIME",
  events: [{ id: "pitchapi:1", type: "GOAL", team_id: fixture.home.id, team_side: "HOME", player_id: "p1", player_name: "Saka", minute: 14, added_time: 0, period: "FirstHalf", own_goal: false, penalty: false, disallowed: false, provider: "pitchapi" }],
  statistics: [{ metric: "possession", label: "Ball possession", period: "FULL_MATCH", home: 55, away: 45, unit: "percent", original_field: "ball_possession", available: true }],
  score_source: { provider: "pitchapi", provider_match_id: "m_123456", observed_at: "2026-09-29T17:00:00Z", last_fetched_at: "2026-09-29T17:00:00Z", stale: false },
  event_source: { provider: "pitchapi", provider_match_id: "m_123456", observed_at: "2026-09-29T17:00:00Z", last_fetched_at: "2026-09-29T17:00:00Z", stale: false },
  statistics_source: { provider: "pitchapi", provider_match_id: "m_123456", observed_at: "2026-09-29T17:00:00Z", last_fetched_at: "2026-09-29T17:00:00Z", stale: false },
  availability: { score: true, events: true, statistics: true }, partial: false,
};

describe("FixtureExplorer", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.includes("/v1/competitions?") ? { competitions: [competition] }
        : url.includes("/v1/fixtures?") ? { date: "2026-09-29", groups: [{ competition, fixtures: [fixture] }] }
        : url.includes("/context") ? context
        : url.includes("/live") ? liveMatch
        : url.includes("/forecasts/") ? forecast
        : url.includes("external-predictions") ? { predictions: [] }
        : {};
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("isolates failed context and live resources from a successful forecast", async () => {
    const original = fetch;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, options?: RequestInit) => /\/(context|live)$/.test(String(input))
      ? Promise.resolve(new Response(JSON.stringify({ error: "Resource unavailable" }), { status: 503 })) : original(input, options)));
    render(<FixtureExplorer initialDate="2026-09-29" />);
    fireEvent.click(await screen.findByRole("button", { name: /Arsenal.*Chelsea/s }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Resource unavailable");
    expect(await screen.findByText("Forecast record")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Score matrix" }));
    await waitFor(() => expect(screen.getAllByText("14.0%")).toHaveLength(2));
    fireEvent.click(screen.getByRole("tab", { name: "Live Match" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Resource unavailable");
    expect(screen.queryByText("Loading live match")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Arsenal.*Chelsea/s })).toBeInTheDocument();
  });

  it("keeps an immutable forecast request stable and rejects its late superseded result", async () => {
    const original = fetch;
    let finish!: (value: Response) => void;
    let oldSignal: AbortSignal | undefined;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, options?: RequestInit) => {
      if (String(input).endsWith("/forecasts/forecast-1")) {
        oldSignal = options?.signal ?? undefined;
        return new Promise<Response>((resolve) => { finish = resolve; });
      }
      if (String(input).endsWith("/forecasts/forecast-2")) return Promise.resolve(new Response(JSON.stringify({ ...forecast, id: "forecast-2", score_matrix: [{ home_goals: 2, away_goals: 0, probability: .21 }] })));
      return original(input, options);
    }));
    const group = parseFixtureGroups({ groups: [{ competition, fixtures: [fixture] }] })[0];
    const view = render(<ExpandedFixture fixture={group.fixtures[0]} competition={group.competition} />);
    await waitFor(() => expect(oldSignal).toBeDefined());
    view.rerender(<ExpandedFixture fixture={{ ...group.fixtures[0], forecast: { ...group.fixtures[0].forecast! } }} competition={group.competition} />);
    expect(vi.mocked(fetch).mock.calls.filter(([input]) => String(input).includes("/forecasts/")).length).toBe(1);
    expect(oldSignal!.aborted).toBe(false);
    view.rerender(<ExpandedFixture fixture={{ ...group.fixtures[0], forecast: { ...group.fixtures[0].forecast!, id: "forecast-2" } }} competition={group.competition} />);
    expect(oldSignal!.aborted).toBe(true);
    fireEvent.click(screen.getByRole("tab", { name: "Score matrix" }));
    await waitFor(() => expect(screen.getAllByText("21.0%")).toHaveLength(2));
    await act(async () => finish(new Response(JSON.stringify(forecast))));
    expect(screen.getAllByText("21.0%")).toHaveLength(2);
    expect(screen.queryByText("14.0%")).not.toBeInTheDocument();
  });

  it("retains fixtures on polling failure, retries locally, and clears them on date change", async () => {
    const original = fetch;
    let fail = false;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, options?: RequestInit) => fail && String(input).includes("/v1/fixtures?")
      ? Promise.resolve(new Response(JSON.stringify({ error: "Report unavailable" }), { status: 503 })) : original(input, options)));
    vi.useFakeTimers();
    try {
      render(<FixtureExplorer initialDate="2026-09-29" />);
      await vi.waitFor(() => expect(screen.getByText("Arsenal")).toBeInTheDocument());
      fail = true;
      await act(async () => vi.advanceTimersByTimeAsync(45_000));
      await vi.waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Showing previously loaded fixtures"));
      expect(screen.getByText("Arsenal")).toBeInTheDocument();
      fail = false;
      fireEvent.click(screen.getByRole("button", { name: "Retry" }));
      await vi.waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
      fail = true;
      fireEvent.click(screen.getByRole("button", { name: "Next day" }));
      expect(screen.queryByText("Arsenal")).not.toBeInTheDocument();
      await vi.waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Report unavailable"));
      expect(screen.queryByText("Arsenal")).not.toBeInTheDocument();
    } finally { vi.useRealTimers(); }
  });

  it.each(["Unknown", "UNKNOWN"])("labels missing country %s clearly and keeps the API filter value", async (country) => {
    const unknown = { ...competition, country, continent: "Unknown", type: "UNKNOWN" };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = String(input).includes("competitions")
        ? { competitions: [unknown] } : { groups: [{ competition: unknown, fixtures: [fixture] }] };
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
    render(<FixtureExplorer initialDate="2026-09-29" />);
    expect(await screen.findByRole("heading", { name: "Country unavailable — Premier League" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Country unavailable" })).toHaveValue(country);
    fireEvent.change(screen.getByLabelText("Country"), { target: { value: country } });
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes(`country=${country}`))).toBe(true));
  });

  it("keeps the last valid day when the date input is cleared", async () => {
    render(<FixtureExplorer initialDate="2026-09-29" />);
    await screen.findByRole("button", { name: /Arsenal.*Chelsea/s });
    fireEvent.change(screen.getByLabelText("Selected date"), { target: { value: "" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a valid fixture date");
    expect(screen.getByLabelText("Selected date")).toHaveValue("2026-09-29");
    fireEvent.click(screen.getByRole("button", { name: "Next day" }));
    expect(screen.getByLabelText("Selected date")).toHaveValue("2026-09-30");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.some(([input]) => /date=(&|$)/.test(String(input)))).toBe(false);
  });

  it("uses roving focus and complete tab-panel associations", async () => {
    render(<FixtureExplorer initialDate="2026-09-29" />);
    fireEvent.click(await screen.findByRole("button", { name: /Arsenal.*Chelsea/s }));
    const overview = screen.getByRole("tab", { name: "Overview" });
    overview.focus(); fireEvent.keyDown(overview, { key: "ArrowRight" });
    const markets = screen.getByRole("tab", { name: "Markets" });
    expect(markets).toHaveFocus(); expect(markets).toHaveAttribute("aria-selected", "true");
    expect(overview).toHaveAttribute("tabindex", "-1");
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", markets.id);
    expect(markets.getAttribute("aria-controls")).toBe(screen.getByRole("tabpanel").id);
    fireEvent.keyDown(markets, { key: "Home" }); expect(screen.getByRole("tab", { name: "Live Match" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("tab", { name: "Live Match" }), { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Forecast history" })).toHaveFocus();
  });

  it("renders the dense fixture list and expands the match inline", async () => {
    render(<FixtureExplorer initialDate="2026-09-29" />);
    const row = await screen.findByRole("button", { name: /Arsenal.*Chelsea/s });
    expect(screen.getByText("England — Premier League")).toBeInTheDocument();
    expect(row).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("tab", { name: "Score matrix" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Forecast record")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "MatchForge interpretation" })).toBeInTheDocument();
    expect(screen.getByText(/Arsenal win is the single most likely result at 46.0%/)).toBeInTheDocument();
    expect(screen.getByText(/Most likely exact score is/).closest("p")).toHaveTextContent("Most likely exact score is 1–0 at 14.0%");
    fireEvent.click(screen.getByRole("tab", { name: "Score matrix" }));
    expect(screen.getByText("0–3 goals · fixed intensity scale: 0–20%")).toBeInTheDocument();
  });

  it.each(["legacy", "v2"])("renders %s aggregated tail buckets without claiming an exact score", async (representation) => {
    const cell = representation === "legacy"
      ? { home_goals: 5, away_goals: 5, probability: .7 }
      : { home_goals: 5, away_goals: 5, probability: .7, home_label: "5+", away_label: "5+", home_bucket_kind: "AT_LEAST", away_bucket_kind: "AT_LEAST" };
    const exactCells = representation === "legacy" ? forecast.score_matrix : forecast.score_matrix.map((score) => ({ ...score, home_label: String(score.home_goals), away_label: String(score.away_goals), home_bucket_kind: "EXACT", away_bucket_kind: "EXACT" }));
    const tailForecast = { ...forecast, ...(representation === "v2" ? { score_matrix_version: "compact-buckets-v2" } : {}), score_matrix: [...exactCells, cell] };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.includes("/v1/competitions?") ? { competitions: [competition] }
        : url.includes("/v1/fixtures?") ? { groups: [{ competition, fixtures: [fixture] }] }
        : url.includes("/context") ? context : tailForecast;
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
    render(<FixtureExplorer initialDate="2026-09-29" />);
    fireEvent.click(await screen.findByRole("button", { name: /Arsenal.*Chelsea/s }));
    await waitFor(() => expect(screen.getByText(/Most likely score category is/).closest("p")).toHaveTextContent("5+–5+ at 70.0%"));
    expect(screen.queryByText("5–5")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Score matrix" }));
    expect(screen.getByText("5+–5+")).toBeInTheDocument();
    expect(screen.queryByText("5–5")).not.toBeInTheDocument();
  });

  it("rejects contradictory score-bucket metadata and unknown legacy interpretation", () => {
    expect(() => parseForecast({ ...forecast, score_matrix_version: "compact-buckets-v2", score_matrix: [{ home_goals: 5, away_goals: 5, probability: .1, home_label: "5", away_label: "5+", home_bucket_kind: "AT_LEAST", away_bucket_kind: "AT_LEAST" }] })).toThrow("home_label");
    expect(() => parseForecast({ ...forecast, model_algorithm_version: "unknown-model" })).toThrow("score_matrix_version");
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

  it("shows recent form for fixtures without a forecast", async () => {
    const unavailable = { ...fixture, id: "fixture-no-forecast", forecast: null, forecast_availability: "NOT_ENOUGH_HISTORY" };
    const availableContext = {
      ...context,
      fixture_id: unavailable.id,
      home_form: [{ kickoff_at: "2026-09-20T15:00:00Z", opponent: "Liverpool", venue: "HOME", goals_for: 2, goals_against: 0, result: "W" }],
      away_form: [{ kickoff_at: "2026-09-20T15:00:00Z", opponent: "Manchester City", venue: "AWAY", goals_for: 1, goals_against: 1, result: "D" }],
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(String(input).includes("/context") ? availableContext : liveMatch), { status: 200 })));
    const group = parseFixtureGroups({ groups: [{ competition, fixtures: [unavailable] }] })[0];
    render(<ExpandedFixture fixture={group.fixtures[0]} competition={group.competition} />);
    expect(await screen.findByRole("heading", { name: "Recent form" })).toBeInTheDocument();
    expect(screen.getByText("W")).toBeInTheDocument();
    expect(screen.getByText("D")).toBeInTheDocument();
    expect(screen.getAllByText("Not enough qualified match history")).toHaveLength(2);
  });

  it("retries context after a temporary report miss", async () => {
    vi.useFakeTimers();
    let contextRequests = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("/context") && ++contextRequests === 1) return new Response(JSON.stringify({ error: "Resource unavailable" }), { status: 503 });
      return new Response(JSON.stringify(String(input).includes("/context") ? context : liveMatch), { status: 200 });
    }));
    try {
      const group = parseFixtureGroups({ groups: [{ competition, fixtures: [fixture] }] })[0];
      render(<ExpandedFixture fixture={group.fixtures[0]} competition={group.competition} />);
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(screen.getAllByText("Recent form is refreshing")).toHaveLength(2);
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(contextRequests).toBe(2);
      expect(screen.getAllByText("No qualified match history")).toHaveLength(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("renders live score, clock, stale state, and live-only filter", async () => {
    const live = {
      ...fixture,
      status: "LIVE",
      home_score: 2,
      away_score: 1,
      provider: "pitchapi",
      provider_status: "live",
      match_minute: 72,
      added_time: 2,
      period: "second_half",
      last_successful_update: "2026-09-29T16:30:00Z",
      stale: true,
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = String(input).includes("competitions")
        ? { competitions: [competition] }
        : { groups: [{ competition, fixtures: [live] }] };
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));

    render(<FixtureExplorer initialDate="2026-09-29" />);

    expect(await screen.findByText("LIVE", { selector: ".live-indicator" })).toBeInTheDocument();
    expect(screen.getByText("72+2′ · stale")).toBeInTheDocument();
    expect(screen.getByText("2–1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Live 1/ }));
    expect(screen.getByText("Arsenal")).toBeInTheDocument();
  });

  it("shows suspended state and score without treating it as actively live", async () => {
    const suspended = {
      ...fixture,
      status: "SUSPENDED",
      home_score: 1,
      away_score: 1,
      provider: "fotmob",
      provider_status: "SUSP",
      match_minute: null,
      added_time: null,
      period: null,
      last_successful_update: "2026-09-29T16:30:00Z",
      stale: false,
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = String(input).includes("competitions")
        ? { competitions: [competition] }
        : { groups: [{ competition, fixtures: [suspended] }] };
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));

    render(<FixtureExplorer initialDate="2026-09-29" />);

    expect(await screen.findByText("SUSPENDED")).toBeInTheDocument();
    expect(screen.getByText("1–1")).toBeInTheDocument();
    expect(screen.queryByText("LIVE", { selector: ".live-indicator" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Live 0/ })).toBeInTheDocument();
  });

  it("renders confirmed live 0-0, compact scorers, and provider statistics", async () => {
    const live = { ...fixture, status: "LIVE", home_score: 0, away_score: 0, goal_scorers: liveMatch.events };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.includes("competitions") ? { competitions: [competition] }
        : url.includes("/live") ? { ...liveMatch, status: "LIVE", home_score: 0, away_score: 0, match_minute: 14 }
        : { groups: [{ competition, fixtures: [live] }] };
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
    render(<FixtureExplorer initialDate="2026-09-29" />);
    expect(await screen.findByText("0–0")).toBeInTheDocument();
    expect(screen.getByText("Saka 14′")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Arsenal.*Chelsea/s }));
    expect(await screen.findByRole("heading", { name: "Current match statistics" })).toBeInTheDocument();
    expect(screen.getByText("Ball possession")).toBeInTheDocument();
    expect(screen.getByText("55%")).toBeInTheDocument();
  });

  it("polls scheduled fixtures and sends the selected display timezone", async () => {
    vi.useFakeTimers();
    try {
      render(<FixtureExplorer initialDate="2026-09-29" />);
      await vi.waitFor(() => expect(screen.getByText("Arsenal")).toBeInTheDocument());
      const fixtureCalls = () => vi.mocked(fetch).mock.calls.filter(([input]) => String(input).includes("/v1/fixtures?")).length;
      expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes("timezone=Africa%2FLagos"))).toBe(true);
      const before = fixtureCalls();
      await vi.advanceTimersByTimeAsync(45_000);
      await vi.waitFor(() => expect(fixtureCalls()).toBeGreaterThan(before));
    } finally {
      vi.useRealTimers();
    }
  });

  it.each([
    ["Europa League", "2026-10-15"],
    ["Conference League", "2026-10-15"],
    ["Botola Pro", "2026-10-14"],
  ])("replaces %s representatives across polling and date navigation", async (name, date) => {
    const league = { ...competition, name };
    let current = { ...fixture, id: "provisional", forecast: null, home_score: null as number | null, away_score: null as number | null };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(
      String(input).includes("/competitions?") ? { competitions: [league] }
        : { groups: [{ competition: league, fixtures: [current, { ...fixture, id: "separate-cup-leg" }] }] },
    ))));
    vi.useFakeTimers();
    try {
      const view = render(<FixtureExplorer initialDate={date} />);
      await vi.waitFor(() => expect(screen.getAllByRole("button", { name: /Arsenal.*Chelsea/s })).toHaveLength(2));
      current = { ...current, id: "admitted-representative", status: "LIVE", home_score: 1, away_score: 0 };
      await vi.advanceTimersByTimeAsync(45_000);
      await vi.waitFor(() => expect(screen.getByText("1–0")).toBeInTheDocument());
      view.rerender(<FixtureExplorer initialDate={date} />);
      expect(screen.getAllByRole("button", { name: /Arsenal.*Chelsea/s })).toHaveLength(2);
      expect(screen.getAllByRole("heading", { name: `England — ${name}` })).toHaveLength(1);
      expect(screen.getByRole("button", { name: "All 2" })).toBeInTheDocument();
      expect(document.querySelector('[aria-controls="fixture-panel-provisional"]')).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Next day" }));
      await vi.waitFor(() => expect(screen.getAllByRole("button", { name: /Arsenal.*Chelsea/s })).toHaveLength(2));
      fireEvent.click(screen.getByRole("button", { name: "Previous day" }));
      await vi.waitFor(() => expect(screen.getAllByRole("button", { name: /Arsenal.*Chelsea/s })).toHaveLength(2));
    } finally {
      vi.useRealTimers();
    }
  });

});
