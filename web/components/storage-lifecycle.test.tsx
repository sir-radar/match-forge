import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LifecyclePanel, MaintenancePanel, countdown } from "@/components/storage-lifecycle";
import { parseLifecycle } from "@/lib/storage-management";

const now = Date.parse("2026-11-13T09:00:00Z");
const record = (over: Record<string, unknown>) => ({
  identity_key: "postgres:1:900", resource_class: "TEST_DATABASE", backend: "postgres", location: "1/football_api_test_42",
  owner_kind: "INTEGRATION_HARNESS", identity: {}, owner_ref: { pid: 42, host: "mac" }, created_at: "2026-11-13T01:00:00Z",
  last_activity_at: "2026-11-13T06:00:00Z", completed_at: "2026-11-13T06:00:00Z", completion: "OWNER_EXITED", state: "WAITING",
  eligible_at: "2026-11-13T11:00:00Z", blockers: [], checked_at: "2026-11-13T08:45:00Z", operation_id: null, reclaimed_bytes: null, ...over,
});
const lifecycle = {
  observed_at: "2026-11-13T09:00:00Z", deployed: true, reclaimed_bytes: 2e9,
  policy: { inactivity_seconds: 18000, check_interval_seconds: 900, max_per_run: 10, test_databases: true,
    worktrees: { target_ref: "refs/remotes/origin/main", roots: ["/r/.claude/worktrees"] }, approved_by: "owner", approval_record: "docs/evidence/x.json" },
  resources: [
    record({}),
    record({ identity_key: "git:/r/.git/worktrees/a", resource_class: "WORKTREE", backend: "git", location: "/r/.claude/worktrees/a",
      owner_kind: "WORKTREE_DISCOVERY", owner_ref: { branch: "docs/a" }, state: "BLOCKED", blockers: ["uncommitted or untracked changes"] }),
  ],
  events: [{ identity_key: "postgres:1:900", event: "COMPLETED", detail: {}, recorded_at: "2026-11-13T06:00:00Z" }],
  unregistered_test_databases: [{ name: "football_api_test_7", oid: 7, bytes: 1e8 }],
};
const maintenance = { policy: { growth_warning_bytes_per_day: 5e9, max_non_operating_databases: 4, stale_after_days: 30 },
  reports: [{ run_id: "r1", cadence: "DAILY", slot: "2026-11-13", state: "SUCCEEDED", alerts: 1, error: null, started_at: "2026-11-13T00:01:00Z",
    finished_at: "2026-11-13T00:02:00Z", findings: [{ task: "backup", severity: "WARNING", message: "latest verified backup is older than the backup interval" },
      { task: "capacity", severity: "INFO", message: "host free space is above the warning threshold", bytes: 3e11 }] }] };

function api(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status }))));
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("five-hour cleanup", () => {
  it("formats the countdown to the deadline", () => {
    expect(countdown(null, now)).toBe("Not complete");
    expect(countdown("2026-11-13T11:00:00Z", now)).toBe("2 h 0 min");
    expect(countdown("2026-11-13T09:00:30Z", now)).toBe("0 h 1 min");
    expect(countdown("2026-11-13T08:00:00Z", now)).toBe("Due");
  });

  it("shows policy, states, blockers, unregistered databases and the audit trail", async () => {
    vi.spyOn(Date, "now").mockReturnValue(now);
    api(lifecycle);
    render(<LifecyclePanel />);
    const table = await screen.findByRole("table", { name: /five-hour cleanup policy/i });
    const rows = within(table).getAllByRole("row");
    expect(within(rows[1]).getByText("Waiting")).toBeTruthy();
    expect(within(rows[1]).getByText("2 h 0 min")).toBeTruthy();
    expect(within(rows[1]).getByText("Test run 42 on mac")).toBeTruthy();
    expect(within(rows[2]).getByText("Blocked")).toBeTruthy();
    expect(within(rows[2]).getByText("uncommitted or untracked changes")).toBeTruthy();
    expect(screen.getByText(/after 5 hours without activity/)).toBeTruthy();
    expect(screen.getByText(/football_api_test_7/)).toBeTruthy();
    fireEvent.click(screen.getByText(/Audit trail/));
    expect(screen.getByText("COMPLETED")).toBeTruthy();
  });

  it("says nothing is deleted before the migration is deployed", async () => {
    api({ ...lifecycle, deployed: false });
    render(<LifecyclePanel />);
    expect(await screen.findByText(/has not been deployed/)).toBeTruthy();
  });

  it("rejects an unknown lifecycle state", () => {
    expect(() => parseLifecycle({ ...lifecycle, resources: [record({ state: "PURGED" })] })).toThrow("Invalid lifecycle state");
  });

  it("offers retry when the request fails", async () => {
    api({ error: "Storage management migration has not been deployed." }, 409);
    render(<LifecyclePanel />);
    expect((await screen.findByRole("alert")).textContent).toContain("migration has not been deployed");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});

describe("maintenance reports", () => {
  it("lists findings with alert severity", async () => {
    api(maintenance);
    render(<MaintenancePanel />);
    expect(await screen.findByText("Daily report 2026-11-13")).toBeTruthy();
    expect(screen.getByText("1 alert")).toBeTruthy();
    expect(screen.getByText(/WARNING: backup/)).toBeTruthy();
    expect(screen.getByText(/Reports never delete anything/)).toBeTruthy();
  });
});
