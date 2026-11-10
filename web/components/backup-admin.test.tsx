import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BackupAdmin } from "@/components/backup-admin";
import { parseBackupView } from "@/lib/backup";
import fixture from "@/test-fixtures/backup-status.json";

const initial = () => parseBackupView(structuredClone(fixture));
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
const run = { run_id: "10000000-0000-4000-8000-000000000001", sync_type: "MANUAL_BACKUP", status: "QUEUED", requested_at: "2026-11-10T11:00:00Z", started_at: null, finished_at: null, requested_date: null, parameters: {}, summary: {}, error_message: null, log_path: null };

describe("manual backup Admin", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("renders empty history, due reminder, and honest protection window without starting work", () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    render(<BackupAdmin initial={initial()} />);
    expect(screen.getByText("Monthly backup due")).toBeVisible();
    expect(screen.getByText("No backup attempts recorded.")).toBeVisible();
    expect(screen.getByText(/24-hour protection target is not guaranteed/)).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("disables manual work for a disconnected drive and allows status retry", async () => {
    const value = initial(); value.safe_to_eject = false; value.availability.state = "DISCONNECTED"; value.availability.message = "Connect the enrolled external drive.";
    vi.stubGlobal("fetch", vi.fn(async () => json(fixture)));
    render(<BackupAdmin initial={value} />);
    expect(screen.getByRole("button", { name: "Back Up Now" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Refresh drive status" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Back Up Now" })).toBeEnabled());
  });
  it("preflights, confirms once, and displays authoritative queued progress", async () => {
    const fetch = vi.fn(async (url: string, options: RequestInit) => url.endsWith("/preview") ? json(fixture) : json({ ...run, run_id: JSON.parse(String(options.body)).request_id }, 202));
    vi.stubGlobal("fetch", fetch);
    render(<BackupAdmin initial={initial()} />);
    fireEvent.click(screen.getByRole("button", { name: "Back Up Now" }));
    const confirm = await screen.findByRole("button", { name: "Confirm backup" });
    expect(screen.getByRole("heading", { name: "Confirm manual backup" })).toHaveFocus();
    fireEvent.click(confirm); fireEvent.click(confirm);
    expect(await screen.findByRole("heading", { name: "Backup in progress" })).toBeVisible();
    expect(fetch.mock.calls.filter(([url]) => !url.endsWith("/preview"))).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Back Up Now" })).toBeDisabled();
  });
  it("retains status during refresh failure and recovers from malformed data", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({})).mockResolvedValueOnce(json(fixture));
    vi.stubGlobal("fetch", fetch); render(<BackupAdmin initial={initial()} />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh drive status" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid backup response");
    expect(screen.getByText("No backup attempts recorded.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry status" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });
  it("retains usable data offline and recovers through local retry", async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new TypeError("Network unavailable")).mockResolvedValueOnce(json(fixture));
    vi.stubGlobal("fetch", fetch); render(<BackupAdmin initial={initial()} />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh drive status" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Network unavailable");
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
    expect(screen.queryByRole("button", { name: "Confirm backup" })).not.toBeInTheDocument();
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
    fireEvent.click(await screen.findByRole("button", { name: "Confirm backup" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Drive disconnected");
    fireEvent.click(screen.getByRole("button", { name: "Confirm backup" }));
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
