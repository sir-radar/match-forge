import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StorageAdmin } from "@/components/storage-admin";
import { parseStorageView } from "@/lib/storage";
import fixture from "@/test-fixtures/storage-status.json";

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
describe("Storage lifecycle Admin", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("shows protected resources and measured bytes without authorizing cleanup", () => {
    render(<StorageAdmin initial={parseStorageView(fixture)} />);
    expect(screen.getByText("0 bytes")).toBeVisible();
    expect(screen.getByText(/Destructive cleanup, quarantine and backup pruning are disabled/)).toBeVisible();
    fireEvent.click(screen.getByText(/cluster\/football_rehearsal/));
    expect(screen.getByText("Current post-rehearsal recovery is unverified")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
  });
  it("distinguishes archive representation savings from physical reclamation", () => {
    const archive = {
      ...fixture.latest.resources[0],
      resource_id: "e".repeat(64), backend: "filesystem", location: "/evidence/packed",
      kind: "archive", subsystem: "evidence_archives", logical_bytes: 4e9,
      details: { packed_bytes: 345e6, unique_bytes: 2e9, verified_at: fixture.latest.observed_at },
    };
    const view = parseStorageView({ ...fixture, latest: { ...fixture.latest, resources: [...fixture.latest.resources, archive] } });
    render(<StorageAdmin initial={view} />);
    fireEvent.click(screen.getByText(/\/evidence\/packed/));
    expect(screen.getByText("345 MB")).toBeVisible();
    expect(screen.getByText("2 GB")).toBeVisible();
    expect(screen.getByText("0 bytes")).toBeVisible();
  });
  it.each([403, 404, 500])("retains prior measurements on HTTP %s and retries", async (status) => {
    const fetch = vi.fn().mockResolvedValueOnce(json({}, status)).mockResolvedValueOnce(json(fixture)); vi.stubGlobal("fetch", fetch);
    render(<StorageAdmin initial={parseStorageView(fixture)} />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh storage status" }));
    await screen.findByRole("alert"); expect(screen.getByText("0 bytes")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Refresh storage status" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });
  it("handles empty, migration-pending and malformed payloads", async () => {
    const empty = parseStorageView({ ...fixture, state: "MIGRATION_PENDING", latest: null, work_id: null, manifest_sha256: null });
    vi.stubGlobal("fetch", vi.fn(async () => json({ ...fixture, destructive_cleanup_enabled: true })));
    render(<StorageAdmin initial={empty} />);
    expect(screen.getByRole("button", { name: "Run dry-run review" })).toBeDisabled();
    expect(screen.getByText("No completed reviews yet.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Refresh storage status" }));
    await screen.findByRole("alert");
  });
  it("submits only dry-run work and disables duplicate submits", async () => {
    let resolve!: (value: Response) => void;
    const fetch = vi.fn().mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done; })).mockResolvedValue(json(fixture)); vi.stubGlobal("fetch", fetch);
    render(<StorageAdmin initial={parseStorageView(fixture)} />);
    fireEvent.click(screen.getByRole("button", { name: "Run dry-run review" }));
    expect(screen.getByRole("button", { name: "Run dry-run review" })).toBeDisabled();
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ dry_run: true });
    resolve(json({})); await screen.findByText(/Dry-run review submitted/);
  });
  it("ignores responses after unmount and reports network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Network unavailable")));
    const { unmount } = render(<StorageAdmin initial={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Refresh storage status" }));
    await screen.findByRole("alert"); unmount();
  });
});

describe("storage transport contract", () => {
  it.each([
    { ...fixture, destructive_cleanup_enabled: true },
    { ...fixture, latest: { ...fixture.latest, reclaimed_bytes: 1 } },
    { ...fixture, latest: { ...fixture.latest, observed_at: "invalid" } },
    { ...fixture, latest: { ...fixture.latest, capacity: { total_bytes: 1, free_bytes: 2 } } },
  ])("fails closed on incompatible safety or measurement fields", (value) => { expect(() => parseStorageView(value)).toThrow(); });
});
