import { useResolutionBackend } from "./resolution-backend";
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const key = "team:00000000-0000-4000-8000-000000000001";
// Deterministic UI fixtures; the retained-backend journey below uses actual responses.
const rows: Record<string, object> = {
  identity: { case_key: key, name: "Northside FC", provider: "api_football", status: "UNRESOLVED", reason: "RETAINED_SOURCE_EVIDENCE_REQUIRED" },
  fixtures: { case_key: "fixture:test:1", name: "Fixture identity", provider: "test", status: "CONTRADICTORY", reason: "CONFLICTING_NATIVE_IDS" },
  missing: { case_key: "resource:00000000-0000-4000-8000-000000000002", name: "Retained payload", provider: "test", status: "BLOCKED", reason: "REGISTERED_BYTES_UNAVAILABLE" },
  parity: { case_key: "parity:serving", name: "Serving parity", status: "BLOCKED", reason: "COMPLETE_SCOPE_REQUIRED", source_sha256: "a".repeat(64) },
  cutover: { case_key: "stage:1", name: "Acquisition", status: "BLOCKED", reason: "MANDATORY_PARITY_UNMET", current_route: "LEGACY" },
  history: { case_key: key, event_id: "retained-decision", status: "UNRESOLVED", reason: "RETAINED_SOURCE_EVIDENCE_REQUIRED", source: "product_identity_admissions" },
};
test.beforeEach(async ({ page }) => {
  if (process.env.MATCHFORGE_RESOLUTION_BACKEND) return;
  await page.route("http://127.0.0.1:8080/v1/admin/resolution/**", async (route) => {
    const url = new URL(route.request().url()), view = url.pathname.split("/").at(-1)!;
    if (view === "detail") {
      await route.fulfill({ json: { case_key: url.searchParams.get("case_key"), status: "UNRESOLVED", evidence_version: "a".repeat(64), source_snapshot_id: "retained-source", proposed_action: "Obtain source-backed review" } });
      return;
    }
    const item = rows[view], status = "status" in item ? String(item.status) : "BLOCKED";
    await route.fulfill({ json: { items: [item], page: 1, page_size: 20, total: 1, counts: { [status]: 1 }, groups: [], scope: "SYNTHETIC_UI_TEST" } });
  });
});
test("resolution sections expose evidence with keyboard navigation and no decisions", async ({ page }, info) => {
  const posts: string[] = [];
  page.on("request", (request) => { if (request.method() === "POST") posts.push(request.url()); });
  await page.goto("/admin/resolution");
  await expect(page.getByRole("heading", { name: "Resolution Center", exact: true })).toBeVisible();
  const inspect = page.getByRole("button", { name: "Inspect case 1" });
  await inspect.focus(); await page.keyboard.press("Enter");
  const review = page.getByRole("region", { name: "Case review" });
  await expect(review.getByText("retained-source", { exact: true })).toBeVisible();
  await expect(review.getByRole("heading")).toBeFocused();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await review.getByRole("button", { name: "Close case" }).click();
  await expect(inspect).toBeFocused();
  for (const section of ["Fixture Review", "Missing Data", "Migration Parity", "Cutover Controls", "Resolution History"]) {
    const button = page.getByRole("navigation", { name: "Resolution sections" }).getByRole("button", { name: section, exact: true });
    await button.focus(); await page.keyboard.press("Enter");
    await expect(button).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("region", { name: "Resolution cases" })).toBeVisible();
  }
  await expect(page.getByRole("button", { name: /Approve|Apply mapping|Execute cutover/ })).toHaveCount(0);
  expect(posts).toEqual([]);
  await page.screenshot({ path: `${process.cwd()}/../.local/resolution-center-${info.project.name}.png`, fullPage: true });
});
test("resolution view reflows at 320px and keeps table keyboard scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/admin/resolution");
  const table = page.getByRole("region", { name: "Resolution cases" });
  await expect(table).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  await table.focus(); await page.keyboard.press("ArrowRight");
  expect(await table.evaluate((node) => node.scrollLeft)).toBeGreaterThan(0);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.emulateMedia({ forcedColors: "active" });
  await expect(page.getByRole("button", { name: "Recheck current view" })).toBeVisible();
});
test("retained backend resolves real read-only cases through Go and Python", async ({ page }) => {
  const backend = process.env.MATCHFORGE_RESOLUTION_BACKEND;
  test.skip(!backend, "started by the disposable database acceptance harness");
  test.setTimeout(90_000);
  await useResolutionBackend(page, backend!);
  await page.goto("/admin/resolution");
  await expect(page.getByRole("cell", { name: /^Brentford FC team:/ })).toBeVisible();
  await page.getByLabel("Search", { exact: true }).fill("Brentford FC");
  await page.getByLabel("Provider", { exact: true }).fill("football_data_org");
  await expect(page.getByText("1 cases in this scope.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Inspect case 1" }).click();
  const review = page.getByRole("region", { name: "Case review" });
  await expect(review.getByRole("heading")).toContainText("team:");
  await review.getByText("Inspect decision", { exact: true }).click();
  await expect(review.getByText("football_data_org", { exact: true }).first()).toBeVisible();
  await review.getByRole("button", { name: "Show resolution history" }).click();
  await page.getByText("Inspect evidence 1", { exact: true }).click();
  await expect(page.getByText("product_identity_admissions", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Missing Data", exact: true }).click();
  await expect(page.getByRole("cell", { name: "api_football", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Inspect case 1" }).click();
  await expect(page.getByRole("region", { name: "Case review" }).getByText("Status: BLOCKED", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Migration Parity", exact: true }).click();
  await expect(page.getByText("11 cases in this scope.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Cutover Controls", exact: true }).click();
  await expect(page.getByText("13 cases in this scope.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: /Approve|Execute cutover/ })).toHaveCount(0);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
