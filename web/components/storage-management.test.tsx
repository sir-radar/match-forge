import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StorageManagement } from "@/components/storage-management";
import { parseResource } from "@/lib/storage-management";

const id = (c: string) => c.repeat(64);
const resource = (over: Record<string, unknown>) => ({
  resource_id: id("a"), backend: "postgres", kind: "database", name: "football_copy", location: "1/football_copy", identity_key: "postgres:1:9",
  purpose: "REHEARSAL", logical_bytes: 9e9, allocated_bytes: 9e9, measurement_complete: true, observed_at: "2026-11-12T03:00:00Z",
  classification: "ELIGIBLE", role: "", reasons: ["no canonical identities absent from the authoritative database"], remediation: [],
  actions: ["DELETE", "QUARANTINE"], active_consumers: 0, recovery: "INDEPENDENTLY_DISPOSABLE",
  evidence: { finding: "NO_UNIQUE_CANONICAL_IDENTITIES", unique_identity_rows: 0, observed_at: "2026-11-12T03:00:00Z", current: true, tables: {} },
  disposition: null, quarantine: null, details: {}, evidence_sha256: id("e"), ...over,
});
const authoritative = resource({
  resource_id: id("b"), name: "football", identity_key: "postgres:1:16384", role: "AUTHORITATIVE_OPERATING_DATABASE", purpose: "OPERATING",
  classification: "PROTECTED", actions: [], active_consumers: 11, recovery: "RECOVERABLE_WITH_DECLARED_GAPS", evidence: null,
  reasons: ["This is MatchForge's authoritative operating database. Deletion is permanently disabled through Storage Management."],
});
const review = resource({ resource_id: id("c"), name: "football_unique", classification: "REVIEW_REQUIRED", actions: [], recovery: "RECOVERY_VERIFICATION_PENDING",
  reasons: ["3 canonical identity row(s) exist only in this database"], remediation: ["Reconcile valid rows, or record that the unique rows are not required."] });
const inventory = {
  inventory: {
    observed_at: "2026-11-12T03:00:00Z", authority: { system_identifier: "1", oid: 16384, database: "football", verified: true },
    resources: [authoritative, resource({}), review], warnings: [],
    summary: { host_total_bytes: 1e12, host_free_bytes: 2e11, postgres_bytes: 3e10, authoritative_bytes: 1.5e10, other_database_bytes: 1.5e10, database_count: 3,
      worktree_bytes: 0, managed_file_bytes: 0, quarantined_bytes: 0, bytes_by_classification: {}, count_by_classification: { PROTECTED: 1, ELIGIBLE: 1, REVIEW_REQUIRED: 1 },
      estimated_reclaimable_bytes: 9e9, verified_reclaimed_bytes: 0, note: "Databases are measured inside the PostgreSQL volume." },
    policy: { configured: false, managed_roots: [], protected_paths: [], automatic_cleanup: [], quarantine_days: 7 },
  },
  comparisons: [],
};
const plan = { action: "DELETE", items: [{ resource_id: id("a"), name: "football_copy", backend: "postgres", location: "1/football_copy", classification: "ELIGIBLE", expected_bytes: 9e9, reasons: [], remediation: [] }],
  blocked: [{ resource_id: id("b"), name: "football", backend: "postgres", location: "1/football", classification: "PROTECTED", expected_bytes: null, reasons: ["authoritative"], remediation: [] }],
  plan_sha256: id("f"), expected_unique_bytes: 9e9, typed_confirmation: "DELETE 1", irreversible: true, consequences: ["Permanently removes the listed resources. There is no undo."], authoritative_verified: true };
const json = (value: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(value), { status }));

function api(extra: (url: string, init?: RequestInit) => Promise<Response> | undefined = () => undefined) {
  const fetch = vi.fn((url: string, init?: RequestInit) => extra(url, init) ?? (url.includes("/operations") ? json({ operations: [] }) : json(inventory)));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("Storage resource management", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("marks the authoritative database protected and never selectable or deletable", async () => {
    api();
    render(<StorageManagement />);
    const row = (await screen.findByText("football (operating)")).closest("tr")!;
    expect(within(row).getByRole("checkbox")).toBeDisabled();
    expect(within(row).getByText("Protected")).toBeVisible();
    fireEvent.click(within(row).getByRole("button", { name: /Details/ }));
    expect(screen.getByRole("button", { name: "Delete…" })).toBeDisabled();
    expect(screen.getAllByText(/Deletion is permanently disabled through Storage Management/).length).toBeGreaterThan(0);
  });

  it("select all only selects actionable resources", async () => {
    api();
    render(<StorageManagement />);
    fireEvent.click(await screen.findByRole("button", { name: "Select all actionable" }));
    expect(screen.getByText(/1 selected of 1 actionable/)).toBeVisible();
    expect(screen.getByRole("checkbox", { name: "Select football_copy" })).toBeChecked();
  });

  it("requires exact typed confirmation and owner credential before deleting", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    api((url, init) => {
      calls.push({ url, init });
      if (url.endsWith("/actions/preview")) return json(plan);
      if (url.endsWith("/actions")) return json({ batch_id: "11111111-1111-4111-8111-111111111111", operations: 1 }, 202);
      return undefined;
    });
    render(<StorageManagement />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select football_copy" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete selected…" }));
    await screen.findByRole("heading", { name: /Delete: review 1 resource/ });
    expect(screen.getByText(/blocked and excluded/)).toBeVisible();
    const execute = screen.getByRole("button", { name: "Delete 1 resource(s)" });
    fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value: "delete 1" } });
    fireEvent.change(screen.getByLabelText("Owner credential"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /I approve exactly these resources/ }));
    expect(execute).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/to confirm/), { target: { value: "DELETE 1" } });
    expect(execute).toBeEnabled();
    fireEvent.click(execute);
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/v1/admin/storage/actions"))).toBe(true));
    const sent = calls.find((c) => c.url.endsWith("/v1/admin/storage/actions"))!;
    expect((sent.init?.headers as Record<string, string>).Authorization).toBe("Bearer secret");
    expect(JSON.parse(String(sent.init?.body))).toEqual({ action: "DELETE", resource_ids: [id("a")], plan_sha256: id("f"), confirmation: "DELETE 1", confirmed: true });
  });

  it("explains review-required resources and offers an owner decision instead of deletion", async () => {
    api();
    render(<StorageManagement />);
    const row = (await screen.findByText("football_unique")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: /Details/ }));
    expect(screen.getByText("3 canonical identity row(s) exist only in this database")).toBeVisible();
    expect(screen.getByRole("button", { name: "Delete…" })).toBeDisabled();
    expect(screen.getByText("Record an owner decision")).toBeVisible();
  });

  it("rejects a response where a protected resource exposes deletion", () => {
    expect(() => parseResource({ ...authoritative, actions: ["DELETE"] })).toThrow(/Protected resource/);
    expect(() => parseResource({ ...review, actions: ["DELETE"] })).toThrow(/Unreviewed/);
  });

  it("shows server errors without hiding the page", async () => {
    api((url) => url.includes("resources") ? json({ error: "Storage management migration has not been deployed." }, 409) : undefined);
    render(<StorageManagement />);
    expect(await screen.findByRole("alert")).toHaveTextContent("migration has not been deployed");
  });
});
