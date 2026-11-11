import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const coverage = {
  eligible_history: 120000, excluded_history: 430, provisional_fixtures: 300,
  verified_provider_matches: 250, identity_conflicts: 12,
  historical_matches: 120430, competitions_with_history: 84, teams_with_10_matches: 930,
  teams_below_10_matches: 23, scheduled_fixtures: 22, forecast_available: 14,
  not_enough_history: 8, mapping_failures: 3, source_conflicts: 1,
  forecast_refresh_pending: 3, forecast_refresh_complete: 19,
  missing_live_scores: 2, fotmob_mapped: 420, fotmob_unmapped: 3,
  pitchapi_mapped: 215, pitchapi_unmapped: 7, fotmob_history: 310,
  pitchapi_history: 90, api_football_requests_used: 100,
  api_football_remaining: 0, api_football_exhausted: true,
};

test.beforeEach(async ({ page }) => {
  await page.route("http://127.0.0.1:8080/v1/admin/**", async (route) => {
    if (route.request().method() === "POST" && route.request().url().endsWith("/sync/history")) {
      const { provider } = route.request().postDataJSON();
      await route.fulfill({ status: 202, json: { ...run("provider-history", "HISTORY_BACKFILL", "QUEUED"), parameters: { provider } } });
      return;
    }
    if (route.request().url().endsWith("/sync-runs/provider-history")) {
      await route.fulfill({ json: { ...run("provider-history", "HISTORY_BACKFILL", "RUNNING"), parameters: { provider: "pitchapi" } } });
      return;
    }
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 202, json: run("new-run", "ALL_DATA", "QUEUED") });
      return;
    }
    if (route.request().url().endsWith("/sync-runs/new-run")) {
      await route.fulfill({ json: run("new-run", "ALL_DATA", "RUNNING") });
      return;
    }
    await route.fulfill({ json: {
      runs: [run("old-run", "OPENFOOTBALL", "SUCCEEDED")], coverage,
      provider_configuration: {
        fotmob_enabled: true, pitchapi_enabled: true, operational_sync_interval: "45s",
      },
    } });
  });
});

test("admin data sync exposes fixed actions, coverage, history, and accessible controls", async ({ page }) => {
  await page.goto("/admin/data-sync");
  await expect(page.getByRole("heading", { name: "Data Sync", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run Full Sync" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Historical Coverage" })).toBeVisible();
  await expect(page.getByText("120,430")).toBeVisible();
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
  await page.getByRole("button", { name: "Run Full Sync" }).click();
  await expect(page.getByText("Running", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sync OpenFootball" })).toBeDisabled();
});

test("provider history has a keyboard-accessible action separate from live sync", async ({ page }) => {
  await page.goto("/admin/data-sync");
  const live = page.getByRole("region", { name: "Live fixtures and scores" });
  const history = page.getByRole("region", { name: "Historical acquisition" });
  const action = history.getByRole("button", { name: "Acquire PitchAPI History" });
  await expect(action).toBeEnabled();
  await action.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toContainText("PitchAPI History");
  await expect(live.getByRole("button", { name: "Sync PitchAPI" })).toBeEnabled();
});

test("admin remains usable at mobile width", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "mobile-only assertion");
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/admin/data-sync");
  await expect(page.getByRole("navigation", { name: "Mobile navigation" }).getByText("Admin")).toBeVisible();
  await expect(page.getByRole("button", { name: "Run Full Sync" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent sync runs" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  const table = page.getByRole("region", { name: "Recent sync runs table" });
  await table.focus();
  expect(await table.evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => table.evaluate((node) => node.scrollLeft)).toBeGreaterThan(0);
});

function run(id: string, type: string, status: string) {
  return {
    run_id: id, sync_type: type, status, requested_at: "2026-09-30T08:00:00Z",
    started_at: status === "QUEUED" ? null : "2026-09-30T08:00:01Z",
    finished_at: status === "SUCCEEDED" ? "2026-09-30T08:01:01Z" : null,
    requested_date: "2026-09-30", parameters: {},
    summary: status === "SUCCEEDED" ? { matches_inserted: 86, result_conflicts: 1 } : {},
    error_message: null, log_path: null,
  };
}
