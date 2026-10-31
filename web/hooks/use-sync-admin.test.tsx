import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import { parseSyncRun, parseSyncRuns } from "@/lib/contracts";
import { mergeSyncRuns, useSyncAdminState } from "@/hooks/use-sync-admin";

const active = parseSyncRun({ run_id: "active", sync_type: "MVP_SYNC", status: "RUNNING", requested_at: "2026-10-13T10:00:00Z", started_at: "2026-10-13T10:00:01Z", finished_at: null, requested_date: "2026-10-13", parameters: {}, summary: {}, error_message: null, log_path: null });
const completed = { ...active, status: "CANCELLED" as const, finished_at: "2026-10-13T10:01:00Z" };
const response = parseSyncRuns({ runs: [active], coverage: {
  eligible_history: 0, excluded_history: 0, provisional_fixtures: 0, verified_provider_matches: 0, identity_conflicts: 0,
  historical_matches: 0, competitions_with_history: 0, teams_with_10_matches: 0, teams_below_10_matches: 0, scheduled_fixtures: 0, forecast_available: 0, not_enough_history: 0, mapping_failures: 0, source_conflicts: 0, missing_live_scores: 0, fotmob_mapped: 0, fotmob_unmapped: 0, pitchapi_mapped: 0, pitchapi_unmapped: 0, fotmob_history: 0, pitchapi_history: 0, api_football_requests_used: 0, api_football_remaining: -1, api_football_exhausted: false,
} });
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((done) => { resolve = done; }); return { promise, resolve }; }

describe("admin polling", () => {
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });
  it("discovers scheduled work after opening idle and refreshes on visibility", async () => {
    vi.useFakeTimers();
    const status = vi.spyOn(api, "syncRuns").mockResolvedValue({ ...response, runs: [] });
    const state = renderHook(() => useSyncAdminState("2026-10-13"));
    await act(async () => { await Promise.resolve(); });
    expect(state.result.current.active).toHaveLength(0);
    status.mockResolvedValue(response);
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(state.result.current.active).toHaveLength(1);
    expect(status).toHaveBeenCalledTimes(2);
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(status).toHaveBeenCalledTimes(3);
    state.unmount();
  });
  it("preserves terminal status against delayed RUNNING or QUEUED snapshots", () => {
    for (const status of ["SUCCEEDED", "FAILED", "CANCELLED"] as const) {
      const terminal = { ...completed, status };
      expect(mergeSyncRuns([terminal], [active])[0]).toEqual(terminal);
      expect(mergeSyncRuns([terminal], [{ ...active, status: "QUEUED" }])[0]).toEqual(terminal);
    }
  });
  it("polls sequentially, aborts superseded requests and cannot regress a stopped run", async () => {
    vi.useFakeTimers();
    const delayed = deferred<typeof response>();
    let signal: AbortSignal | undefined;
    const status = vi.spyOn(api, "syncRuns").mockResolvedValue(response);
    vi.spyOn(api, "stopSyncRun").mockResolvedValue(completed);
    const state = renderHook(() => useSyncAdminState("2026-10-13"));
    await act(async () => { await Promise.resolve(); });
    expect(state.result.current.active).toHaveLength(1);
    status.mockImplementationOnce((value) => { signal = value; return delayed.promise; });
    await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
    expect(status).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(status).toHaveBeenCalledTimes(2); // pending poll never overlaps
    await act(async () => { await state.result.current.stop(active); });
    expect(signal?.aborted).toBe(true);
    expect(state.result.current.active).toHaveLength(0);
    await act(async () => delayed.resolve(response));
    expect(state.result.current.runs[0].status).toBe("CANCELLED");
    const count = status.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(status).toHaveBeenCalledTimes(count);
    state.unmount();
  });
  it("keeps independent lanes usable and blocks duplicate pending submissions", async () => {
    const posted = deferred<typeof active>();
    vi.spyOn(api, "syncRuns").mockResolvedValue(response);
    vi.spyOn(api, "syncRun").mockResolvedValue({ ...active, run_id: "fotmob", sync_type: "FOTMOB_SYNC" });
    const state = renderHook(() => useSyncAdminState("2026-10-13"));
    await act(async () => { await Promise.resolve(); });
    expect(state.result.current.laneBusy("MVP_SYNC")).toBe(true);
    expect(state.result.current.laneBusy("FOTMOB_SYNC")).toBe(false);
    const submit = vi.fn(() => posted.promise);
    let mutation!: Promise<void>;
    act(() => { mutation = state.result.current.start("FOTMOB_SYNC", submit); void state.result.current.start("FOTMOB_SYNC", submit); });
    expect(submit).toHaveBeenCalledTimes(1);
    expect(state.result.current.laneBusy("FOTMOB_SYNC")).toBe(true);
    expect(state.result.current.laneBusy("PITCHAPI_SYNC")).toBe(false);
    await act(async () => { posted.resolve({ ...active, run_id: "fotmob", sync_type: "FOTMOB_SYNC" }); await mutation; });
    expect(state.result.current.active).toHaveLength(2);
    state.unmount();
  });
  it("keeps lane failures separate and reloads authoritative status after a conflict", async () => {
    const status = vi.spyOn(api, "syncRuns").mockResolvedValue({ ...response, runs: [] });
    const state = renderHook(() => useSyncAdminState("2026-10-13"));
    await act(async () => { await Promise.resolve(); });
    const fail = vi.fn(async () => { throw new ApiError("provider unavailable", 503); });
    await act(async () => { await state.result.current.start("FOTMOB_SYNC", fail); });
    expect(state.result.current.laneErrors.LIVE_FOTMOB).toContain("provider unavailable");
    expect(state.result.current.laneErrors.LIVE_PITCHAPI).toBeUndefined();
    expect(state.result.current.laneBusy("FOTMOB_SYNC")).toBe(false);
    const conflict = vi.fn(async () => { throw new ApiError("lane is occupied", 409); });
    const before = status.mock.calls.length;
    status.mockResolvedValue(response);
    await act(async () => { await state.result.current.start("MVP_SYNC", conflict); });
    expect(status).toHaveBeenCalledTimes(before + 1);
    expect(state.result.current.active).toEqual([active]);
    expect(state.result.current.laneErrors.BULK).toBe("lane is occupied");
    expect(state.result.current.laneErrors.LIVE_FOTMOB).toContain("provider unavailable");
    state.unmount();
  });
  it("clears a lane error on retry and ignores a mutation finishing after unmount", async () => {
    const status = vi.spyOn(api, "syncRuns").mockResolvedValue({ ...response, runs: [] });
    const state = renderHook(() => useSyncAdminState("2026-10-13"));
    await act(async () => { await Promise.resolve(); });
    await act(async () => { await state.result.current.start("FOTMOB_SYNC", async () => { throw new Error("offline"); }); });
    expect(state.result.current.laneErrors.LIVE_FOTMOB).toContain("offline");
    const posted = deferred<typeof active>();
    let mutation!: Promise<void>;
    act(() => { mutation = state.result.current.start("FOTMOB_SYNC", () => posted.promise); });
    expect(state.result.current.laneErrors.LIVE_FOTMOB).toBeUndefined();
    const before = status.mock.calls.length;
    state.unmount();
    await act(async () => { posted.resolve({ ...active, sync_type: "FOTMOB_SYNC" }); await mutation; });
    expect(status).toHaveBeenCalledTimes(before);
  });
});
