import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BackupAdmin } from "@/components/backup-admin";
import { api } from "@/lib/api";
import { parseBackupView } from "@/lib/backup";
import fixture from "@/test-fixtures/backup-status.json";

const initial = () => parseBackupView(structuredClone(fixture));
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
const run = { run_id: "10000000-0000-4000-8000-000000000001", sync_type: "MANUAL_BACKUP", status: "QUEUED", requested_at: "2026-11-10T11:00:00Z", started_at: null, finished_at: null, requested_date: null, parameters: { scope: fixture.availability.scope, unavailable_sha256: fixture.availability.unavailable_sha256 }, summary: {}, error_message: null, log_path: null };
const snapshot = "a".repeat(64);
const receiptView = () => parseBackupView({
  ...fixture,
  backup_age_seconds: 1,
  next_due_at: "2026-12-10T22:05:00Z",
  reminder_due: false,
  availability: {
    ...fixture.availability,
    prior_verified: {
      scope: "RECOVERABLE_ONLY", snapshot_id: snapshot, verified: true, full_recovery: false,
      captured_at: "2026-11-10T21:12:00Z", verified_at: "2026-11-10T22:05:00Z",
      unavailable_dependencies: 159, logical_bytes: 3, data_added_packed_bytes: 2, repository_file_bytes: 4,
    },
  },
});

describe("manual backup Admin", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("renders empty history, due reminder, and honest protection window without starting work", () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    render(<BackupAdmin initial={initial()} />);
    expect(screen.getByText("Monthly backup due")).toBeVisible();
    expect(screen.getByText("No backup attempts recorded.")).toBeVisible();
    expect(screen.getByText(/159 unavailable dependencies in the reviewed inventory/)).toBeVisible();
    expect(screen.getByText(/24-hour protection target is not guaranteed/)).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("disables manual work for a disconnected drive and allows status retry", async () => {
    const value = receiptView(); value.safe_to_eject = false; delete value.availability.drive;
    value.availability.state = "DISCONNECTED"; value.availability.message = "Connect the enrolled external drive.";
    vi.stubGlobal("fetch", vi.fn(async () => json(fixture)));
    render(<BackupAdmin initial={value} />);
    expect(screen.getByText("Connect the enrolled external drive.")).toBeVisible();
    expect(screen.getByText(snapshot)).toBeVisible();
    expect(screen.queryByText("Authenticated encrypted repository")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back Up Now" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Refresh drive status" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Back Up Now" })).toBeEnabled());
  });
  it.each([
    ["MIGRATION_PENDING", "Backup migration is pending separate operating approval."],
    ["DISABLED", "Backup activation is disabled."],
    ["WRONG_DRIVE", "Reconnect the correct drive."],
    ["CREDENTIALS", "Unlock the enrolled backup password in macOS Keychain."],
    ["MISSING_FILES", "Full recovery is blocked by the declared unavailable dependencies."],
  ])("shows %s without guessing repository setup", (state, message) => {
    const value = parseBackupView({
      ...fixture, safe_to_eject: false,
      availability: { ...fixture.availability, state, message, drive: undefined, repository_unlocked: false },
    });
    render(<BackupAdmin initial={value} />);
    expect(screen.getByText(message)).toBeVisible();
    expect(screen.queryByText(/awaiting setup/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back Up Now" })).toBeDisabled();
  });
  it("retries the initial 404 without suggesting repository setup", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response("404 page not found", { status: 404 }));
    vi.stubGlobal("fetch", fetch);
    const { view, error } = await api.backup(undefined, "http://127.0.0.1:3000");
    fetch.mockResolvedValueOnce(json(fixture));
    render(<BackupAdmin initial={view} initialError={error} />);
    expect(screen.getByRole("alert")).toHaveTextContent("HTTP 404");
    expect(screen.queryByText(/awaiting setup/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry status" }));
    expect(await screen.findByText("Authenticated encrypted repository")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("retains a verified receipt and blocks actions when the last status becomes stale", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({ error: "private detail" }, 503))
      .mockResolvedValueOnce(json(fixture));
    vi.stubGlobal("fetch", fetch);
    render(<BackupAdmin initial={receiptView()} />);
    expect(screen.getByText("Recoverable data verified")).toBeVisible();
    expect(screen.queryByText("Monthly backup due")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh drive status" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 503");
    expect(screen.getByText(snapshot)).toBeVisible();
    expect(screen.getByRole("button", { name: "Back Up Now" })).toBeDisabled();
    expect(screen.getByText(/Safe-to-eject status is not confirmed/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry status" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Back Up Now" })).toBeEnabled());
  });
  it("preflights, confirms once, and displays authoritative queued progress", async () => {
    const fetch = vi.fn(async (url: string, options: RequestInit) => url.endsWith("/preview") ? json(fixture) : json({ ...run, run_id: JSON.parse(String(options.body)).request_id }, 202));
    vi.stubGlobal("fetch", fetch);
    render(<BackupAdmin initial={initial()} />);
    fireEvent.click(screen.getByRole("button", { name: "Back Up Now" }));
    const confirm = await screen.findByRole("button", { name: "Confirm recoverable-only backup" });
    await waitFor(() => expect(screen.getByRole("heading", { name: "Confirm manual backup" })).toHaveFocus());
    fireEvent.click(confirm); fireEvent.click(confirm);
    expect(await screen.findByRole("heading", { name: "Backup in progress" })).toBeVisible();
    expect(fetch.mock.calls.filter(([url]) => !url.endsWith("/preview"))).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Back Up Now" })).toBeDisabled();
  });
  it("shows the prior operator receipt and preserves the full recovery limitation", () => {
    const status = initial();
    status.availability.prior_verified = {
      scope: "RECOVERABLE_ONLY", snapshot_id: "a".repeat(64),
      captured_at: "2026-11-10T10:00:00Z", verified_at: "2026-11-10T11:00:00Z",
      full_recovery: false, unavailable_dependencies: 159, logical_bytes: 1000,
      data_added_packed_bytes: 100, repository_file_bytes: 150,
    };
    status.backup_age_seconds = 3600;
    status.next_due_at = "2026-12-10T11:00:00Z";
    status.reminder_due = false;
    render(<BackupAdmin initial={status} />);
    expect(screen.getByText("Recovery point from operator receipt")).toBeVisible();
    expect(screen.getByText("Full recovery has yet to pass isolated verification.")).toBeVisible();
    expect(screen.queryByText("Monthly backup due")).not.toBeInTheDocument();
  });
  it("retains status during refresh failure and recovers from malformed data", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({})).mockResolvedValueOnce(json(fixture));
    vi.stubGlobal("fetch", fetch); render(<BackupAdmin initial={initial()} />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh drive status" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The API returned incompatible backup status");
    expect(screen.getByText("No backup attempts recorded.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry status" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });
  it("retains usable data offline and recovers through local retry", async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new TypeError("Network unavailable")).mockResolvedValueOnce(json(fixture));
    vi.stubGlobal("fetch", fetch); render(<BackupAdmin initial={initial()} />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh drive status" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The browser could not reach the backup API");
    expect(screen.getByText("No backup attempts recorded.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry status" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });
  it("shows actionable preflight errors without opening confirmation", async () => {
    const value = initial(); value.safe_to_eject = false; value.availability.state = "MISSING_FILES"; value.availability.message = "Original source files are missing.";
    vi.stubGlobal("fetch", vi.fn(async () => json(value)));
    render(<BackupAdmin initial={initial()} />);
    fireEvent.click(screen.getByRole("button", { name: "Back Up Now" }));
    expect(await screen.findByText("Original source files are missing.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Confirm recoverable-only backup" })).not.toBeInTheDocument();
  });
  it("preserves the manual request identity across a failed submission retry", async () => {
    const ids: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, options: RequestInit) => {
      if (url.endsWith("/preview")) return json(fixture);
      const id = JSON.parse(String(options.body)).request_id; ids.push(id);
      return ids.length === 1 ? json({ error: "Drive disconnected" }, 409) : json({ ...run, run_id: id }, 202);
    }));
    render(<BackupAdmin initial={initial()} />);
    fireEvent.click(screen.getByRole("button", { name: "Back Up Now" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm recoverable-only backup" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Drive disconnected");
    fireEvent.click(screen.getByRole("button", { name: "Confirm recoverable-only backup" }));
    expect(await screen.findByRole("heading", { name: "Backup in progress" })).toBeVisible();
    expect(ids).toHaveLength(2); expect(ids[0]).toBe(ids[1]);
  });
  it("ignores a response after navigation and aborts pending work", async () => {
    let resolve!: (value: Response) => void;
    const fetch = vi.fn((_url: string, options: RequestInit) => { expect(options.signal).toBeDefined(); return new Promise<Response>((done) => { resolve = done; }); });
    vi.stubGlobal("fetch", fetch);
    const component = render(<BackupAdmin initial={initial()} />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh drive status" })); component.unmount();
    expect(fetch.mock.calls[0][1].signal?.aborted).toBe(true);
    resolve(json(fixture));
  });
});
