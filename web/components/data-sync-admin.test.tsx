import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DataSyncAdmin } from "@/components/data-sync-admin";

const coverage = {
  eligible_history: 1000, excluded_history: 100, provisional_fixtures: 60,
  verified_provider_matches: 80, identity_conflicts: 2,
  historical_matches: 124806, competitions_with_history: 84, teams_with_10_matches: 934,
  teams_below_10_matches: 19, scheduled_fixtures: 22, forecast_available: 14,
  not_enough_history: 8, mapping_failures: 2, source_conflicts: 1,
  forecast_refresh_pending: 3, forecast_refresh_complete: 19,
  missing_live_scores: 3, fotmob_mapped: 100, fotmob_unmapped: 4,
  pitchapi_mapped: 80, pitchapi_unmapped: 8, fotmob_history: 60,
  pitchapi_history: 40, api_football_requests_used: 100,
  api_football_remaining: 0, api_football_exhausted: true,
};

describe("DataSyncAdmin", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows bounded background queue diagnostics without inventing quota or throughput", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({
      runs: [], provider_configuration: { fotmob_enabled: false, pitchapi_enabled: true, operational_sync_interval: "30s", history_sync_enabled: false, history_sync_interval: "1h0m0s" },
      coverage: { ...coverage, provider_history: [{
        provider: "pitchapi", pending: 323, running: 0, completed: 2, failed: 1, deferred: 3,
        oldest_pending_observed_at: "2026-10-13T08:00:00Z", completions_24_hours: 2,
        observed_seconds: 100, requests_used: 5, historical_requests_used: 3,
        remaining_requests: null, exhausted: false, deferred_until: null,
        completions_per_hour: null, estimated_drain_hours: null,
      }] },
    })));
    render(<DataSyncAdmin />);
    expect(await screen.findByText("323 / 0 / 2")).toBeInTheDocument();
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
    expect(screen.getByText("5 / 3")).toBeInTheDocument();
    expect(screen.getByText("Forecast refresh pending")).toBeInTheDocument();
    expect(screen.getByText("Forecast refresh complete")).toBeInTheDocument();
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
  });

  it("rejects malformed background diagnostics and offers status retry", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({
      runs: [], coverage: { ...coverage, provider_history: [{ provider: "pitchapi", pending: -1 }] },
    })));
    render(<DataSyncAdmin />);
    expect(await screen.findByRole("alert")).toHaveTextContent("pending");
    expect(screen.getByText("History queue diagnostics are unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry status" })).toBeInTheDocument();
  });

  it("renders every fixed action, coverage, history, and prevents duplicate submission", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") return json({
        run_id: "run-new", sync_type: "ALL_DATA", status: "QUEUED",
        requested_at: "2026-09-30T10:00:00Z", started_at: null, finished_at: null,
        requested_date: "2026-09-30", parameters: {}, summary: {}, error_message: null, log_path: null,
      }, 202);
      return json({ runs: [{
        run_id: "run-old", sync_type: "OPENFOOTBALL", status: "SUCCEEDED",
        requested_at: "2026-09-30T08:00:00Z", started_at: "2026-09-30T08:00:01Z",
        finished_at: "2026-09-30T08:01:01Z", requested_date: "2026-09-30", parameters: {},
        summary: { matches_inserted: 86, resources_cached: 420, source_revision: "abcdef123456", result_conflicts: 1 },
        error_message: null, log_path: ".local/sync-runs/run-old.log",
      }], coverage });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<DataSyncAdmin />);
    expect(await screen.findByRole("heading", { name: "Historical Coverage" })).toBeInTheDocument();
    expect(screen.getByText("124,806")).toBeInTheDocument();
    expect(screen.getByLabelText("Backfill fixtures from")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Backfill fixtures from"), { target: { value: "2026-09-29" } });
    for (const name of ["Run MVP Sync", "Sync OpenFootball", "Sync Football-Data.co.uk", "Run Both Historical Sources", "Refresh Forecasts", "Sync External Predictions", "Sync FotMob", "Sync PitchAPI", "Run Full Sync"]) {
      expect(screen.getByRole("button", { name })).toBeEnabled();
    }
    expect(screen.getAllByText("Disabled").length).toBeGreaterThanOrEqual(2);
    fireEvent.click(screen.getByRole("button", { name: "Run Full Sync" }));
    expect(await screen.findByText("Queued")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run MVP Sync" })).toBeDisabled();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/v1/admin/sync/all"),
      expect.objectContaining({ method: "POST", body: expect.stringContaining('"from_date"') }),
    ));
  });

  it("shows actionable API errors", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ error: "database unavailable" }, 503)));
    render(<DataSyncAdmin />);
    expect(await screen.findByRole("alert")).toHaveTextContent("database unavailable");
    expect(screen.getByRole("button", { name: "Retry status" })).toBeInTheDocument();
  });

  it("rejects malformed eligibility metrics instead of showing misleading zeroes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({
      runs: [], coverage: { ...coverage, eligible_history: null },
    })));
    render(<DataSyncAdmin />);
    expect(await screen.findByRole("alert")).toHaveTextContent("eligible_history");
    expect(screen.getByText("Coverage is unavailable.")).toBeInTheDocument();
  });

  it("shows internal history queue progress without changing top-level status", async () => {
    const active = {
      run_id: "run-active", sync_type: "MVP_SYNC", status: "RUNNING",
      requested_at: "2026-10-04T10:00:00Z", started_at: "2026-10-04T10:00:01Z",
      finished_at: null, requested_date: "2026-10-04", parameters: {}, summary: {},
      error_message: null, log_path: ".local/sync-runs/run-active.log",
      history_queue: { total: 227, pending: 181, running: 3, succeeded: 40, failed: 3 },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST" && String(input).endsWith("/stop")) {
        return json({ ...active, status: "CANCELLED", finished_at: "2026-10-04T10:02:00Z", error_message: "stopped by operator" });
      }
      return json({ runs: [active], coverage });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<DataSyncAdmin />);

    expect(await screen.findByText("Running")).toBeInTheDocument();
    expect(screen.getByText("History queue: 40/227 succeeded, 3 running, 181 pending, 3 failed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Stop sync" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/v1/admin/sync-runs/run-active/stop"),
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("retries failed and cancelled runs", async () => {
    const failed = {
      run_id: "run-failed", sync_type: "PITCHAPI_SYNC", status: "FAILED",
      requested_at: "2026-10-04T10:00:00Z", started_at: "2026-10-04T10:00:01Z",
      finished_at: "2026-10-04T10:01:00Z", requested_date: "2026-10-04",
      parameters: {}, summary: {}, error_message: "provider timeout", log_path: null,
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") return json({
        ...failed, run_id: "run-retry", status: "QUEUED", started_at: null,
        finished_at: null, error_message: null,
      }, 202);
      return json({ runs: [failed], coverage });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<DataSyncAdmin />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Queued")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/v1/admin/sync-runs/run-failed/retry"),
      expect.objectContaining({ method: "POST" }),
    );
  });
});

function json(value: object, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}
