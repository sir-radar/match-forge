import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixture from "../test-fixtures/storage-status.json";

test("storage dry-run protections, keyboard, reflow and accessibility", async ({ page }, info) => {
  await page.route("**/v1/admin/storage", (route) => route.fulfill({ json: fixture, headers: { "Access-Control-Allow-Origin": "http://127.0.0.1:3009" } }));
  await page.goto("/admin/storage");
  const refresh = page.getByRole("button", { name: "Refresh storage status" });
  await refresh.focus(); await page.keyboard.press("Enter");
  await expect(page.getByText("0 bytes")).toBeVisible();
  const resource = page.locator("summary").filter({ hasText: "cluster/football_rehearsal" });
  await resource.focus(); await page.keyboard.press("Enter");
  await expect(page.getByText("Current post-rehearsal recovery is unverified")).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: info.outputPath("storage-admin.png"), fullPage: true });
  await page.setViewportSize({ width: 320, height: 850 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.addStyleTag({ content: "p {line-height:1.5!important;margin-bottom:2em!important} * {letter-spacing:.12em!important;word-spacing:.16em!important}" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
  await expect(refresh).toBeVisible();
});

const hex = (c: string) => c.repeat(64);
const managed = (over: Record<string, unknown>) => ({
  resource_id: hex("a"), backend: "postgres", kind: "database", name: "football_copy", location: "1/football_copy", identity_key: "postgres:1:9",
  purpose: "REHEARSAL", logical_bytes: 9e9, allocated_bytes: 9e9, measurement_complete: true, observed_at: "2026-11-12T03:00:00Z",
  classification: "ELIGIBLE", role: "", reasons: ["no canonical identities absent from the authoritative database"], remediation: [],
  actions: ["DELETE", "QUARANTINE"], active_consumers: 0, recovery: "INDEPENDENTLY_DISPOSABLE",
  evidence: { finding: "NO_UNIQUE_CANONICAL_IDENTITIES", unique_identity_rows: 0, observed_at: "2026-11-12T03:00:00Z", current: true, tables: {} },
  disposition: null, quarantine: null, details: {}, evidence_sha256: hex("e"), ...over,
});
const managementInventory = { comparisons: [], inventory: {
  observed_at: "2026-11-12T03:00:00Z", authority: { system_identifier: "1", oid: 16384, database: "football", verified: true }, warnings: [],
  resources: [
    managed({ resource_id: hex("b"), name: "football", role: "AUTHORITATIVE_OPERATING_DATABASE", purpose: "OPERATING", classification: "PROTECTED", actions: [], active_consumers: 11,
      recovery: "RECOVERABLE_WITH_DECLARED_GAPS", evidence: null, reasons: ["This is MatchForge's authoritative operating database. Deletion is permanently disabled through Storage Management."] }),
    managed({}),
  ],
  summary: { host_total_bytes: 1e12, host_free_bytes: 2e11, postgres_bytes: 2.5e10, authoritative_bytes: 1.6e10, other_database_bytes: 9e9, database_count: 2,
    worktree_bytes: 0, managed_file_bytes: 0, quarantined_bytes: 0, bytes_by_classification: {}, count_by_classification: { PROTECTED: 1, ELIGIBLE: 1 },
    estimated_reclaimable_bytes: 9e9, verified_reclaimed_bytes: 0, note: "Databases are measured inside the PostgreSQL volume." },
  policy: { configured: false, managed_roots: [], protected_paths: [], automatic_cleanup: [], quarantine_days: 7 },
} };

test("resource management protects the operating database and gates deletion", async ({ page }) => {
  const cors = { "Access-Control-Allow-Origin": "http://127.0.0.1:3009" };
  await page.route("**/v1/admin/storage", (route) => route.fulfill({ json: fixture, headers: cors }));
  await page.route("**/v1/admin/storage/resources**", (route) => route.fulfill({ json: managementInventory, headers: cors }));
  await page.route("**/v1/admin/storage/operations", (route) => route.fulfill({ json: { operations: [] }, headers: cors }));
  await page.route("**/v1/admin/storage/actions/preview", (route) => route.fulfill({ headers: cors, json: {
    action: "DELETE", items: [{ resource_id: hex("a"), name: "football_copy", backend: "postgres", location: "1/football_copy", classification: "ELIGIBLE", expected_bytes: 9e9, reasons: [], remediation: [] }],
    blocked: [], plan_sha256: hex("f"), expected_unique_bytes: 9e9, typed_confirmation: "DELETE 1", irreversible: true,
    consequences: ["Permanently removes the listed resources. There is no undo."], authoritative_verified: true } }));
  await page.goto("/admin/storage");
  const operating = page.getByRole("checkbox", { name: /football cannot be selected/ });
  await expect(operating).toBeDisabled();
  await page.getByRole("button", { name: "Select all actionable" }).click();
  await expect(page.getByText(/1 selected of 1 actionable/)).toBeVisible();
  await page.getByRole("button", { name: "Delete selected…" }).click();
  const execute = page.getByRole("button", { name: "Delete 1 resource(s)" });
  await expect(execute).toBeDisabled();
  await page.getByLabel(/to confirm/).fill("DELETE 1");
  await page.getByLabel("Owner credential").first().fill("token");
  await page.getByRole("checkbox", { name: /I approve exactly these resources/ }).check();
  await expect(execute).toBeEnabled();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  await page.setViewportSize({ width: 320, height: 850 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
