import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const coverage = {
  historical_matches: 120430, competitions_with_history: 84, teams_with_10_matches: 930,
  teams_below_10_matches: 23, scheduled_fixtures: 22, forecast_available: 14,
  not_enough_history: 8, mapping_failures: 3, source_conflicts: 1,
};

test.beforeEach(async ({ page }) => {
  await page.route("http://127.0.0.1:8080/v1/admin/**", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 202, json: run("new-run", "ALL_DATA", "QUEUED") });
      return;
    }
    if (route.request().url().endsWith("/sync-runs/new-run")) {
      await route.fulfill({ json: run("new-run", "ALL_DATA", "RUNNING") });
      return;
    }
    await route.fulfill({ json: { runs: [run("old-run", "OPENFOOTBALL", "SUCCEEDED")], coverage } });
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
  await expect(page.getByText("Queued", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sync OpenFootball" })).toBeDisabled();
});

test("admin remains usable at mobile width", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "mobile-only assertion");
  await page.goto("/admin/data-sync");
  await expect(page.getByRole("navigation", { name: "Mobile navigation" }).getByText("Admin")).toBeVisible();
  await expect(page.getByRole("button", { name: "Run Full Sync" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent sync runs" })).toBeVisible();
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
