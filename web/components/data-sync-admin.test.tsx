import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DataSyncAdmin } from "@/components/data-sync-admin";

const coverage = {
  historical_matches: 124806, competitions_with_history: 84, teams_with_10_matches: 934,
  teams_below_10_matches: 19, scheduled_fixtures: 22, forecast_available: 14,
  not_enough_history: 8, mapping_failures: 2, source_conflicts: 1,
};

describe("DataSyncAdmin", () => {
  afterEach(() => vi.unstubAllGlobals());

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
    for (const name of ["Run MVP Sync", "Sync OpenFootball", "Sync Football-Data.co.uk", "Run Both Historical Sources", "Refresh Forecasts", "Sync External Predictions", "Run Full Sync"]) {
      expect(screen.getByRole("button", { name })).toBeEnabled();
    }
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

  it("shows internal history queue progress without changing top-level status", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ runs: [{
      run_id: "run-active", sync_type: "MVP_SYNC", status: "RUNNING",
      requested_at: "2026-10-04T10:00:00Z", started_at: "2026-10-04T10:00:01Z",
      finished_at: null, requested_date: "2026-10-04", parameters: {}, summary: {},
      error_message: null, log_path: ".local/sync-runs/run-active.log",
      history_queue: { total: 227, pending: 181, running: 3, succeeded: 40, failed: 3 },
    }], coverage })));

    render(<DataSyncAdmin />);

    expect(await screen.findByText("Running")).toBeInTheDocument();
    expect(screen.getByText("History queue: 40/227 succeeded, 3 running, 181 pending, 3 failed")).toBeInTheDocument();
  });
});

function json(value: object, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}
