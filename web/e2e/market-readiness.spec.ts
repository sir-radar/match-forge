import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixture from "../test-fixtures/market-capability-summary.json";

async function fillScope(page: import("@playwright/test").Page, competition = fixture.competition_id, season = fixture.season_id) {
  await page.getByLabel("Competition ID", { exact: true }).fill(competition);
  await page.getByLabel("Season ID", { exact: true }).fill(season);
  await page.getByLabel("Knowledge cutoff", { exact: true }).fill(fixture.knowledge_cutoff);
  await page.getByRole("button", { name: "Inspect market readiness" }).click();
}

test("market readiness stays diagnostic with keyboard disclosures and local retry", async ({ page }, info) => {
  await page.clock.setFixedTime(new Date(fixture.recorded_at));
  let failed = true;
  const writes: string[] = [];
  page.on("request", (request) => { if (request.method() === "POST") writes.push(request.url()); });
  await page.route("http://127.0.0.1:8080/v1/admin/sync-runs", (route) => route.fulfill({ status: 503, json: { error: "Independent sync status unavailable" } }));
  await page.route("http://127.0.0.1:8080/v1/admin/market-capabilities?**", (route) => failed
    ? route.fulfill({ status: 503, json: { error: "Qualification temporarily unavailable" } }) : route.fulfill({ json: fixture }));
  await page.goto("/admin/data-sync");
  await fillScope(page);
  await expect(page.getByText("Qualification temporarily unavailable", { exact: true })).toBeVisible();
  failed = false;
  await page.getByLabel("Scoped market readiness").getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByText(/Model metadata is not target qualification/)).toBeVisible();
  const goals = page.getByText("Results and goals — 1 target families", { exact: true });
  await goals.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("rowheader", { name: "RESULT_1X2", exact: true })).toBeVisible();
  await expect(page.getByText("DATA_COLLECTION_REQUIRED", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/Current publication: UNKNOWN/).first()).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await expect(goals).toHaveCSS("min-height", "36px");
  await expect(page.locator(".market-readiness > p")).toHaveCSS("padding", "12px");
  await expect(page.locator(".market-readiness form")).toHaveCSS("flex-wrap", "wrap");
  await expect(page.locator(".market-readiness form button")).toHaveCSS("min-height", "36px");
  await page.evaluate(() => document.fonts.ready);
  const viewport = page.viewportSize()!;
  const name = `admin-market-readiness--diagnostic--${viewport.width}x${viewport.height}--dark--${info.project.name}.png`;
  await page.locator(".market-readiness").evaluate((node) => window.scrollTo(0, window.scrollY + node.getBoundingClientRect().top - 104));
  await info.attach("market-layout", { body: JSON.stringify(await page.evaluate(() => ({fonts:[...document.fonts].map((font) => ({family:font.family,status:font.status})),bodyFont:getComputedStyle(document.body).fontFamily}))), contentType: "application/json" });
  await page.screenshot({ path: `${process.cwd()}/../.local/reports/v4/phase-22/${name}`, animations: "disabled", caret: "hide" });
  await page.setViewportSize({ width: 320, height: 800 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  const table = page.getByRole("region", { name: "Results and goals readiness", exact: true });
  await table.focus(); await page.keyboard.press("ArrowRight");
  expect(await table.evaluate((node) => node.scrollLeft)).toBeGreaterThan(0);
  await page.emulateMedia({ forcedColors: "active" });
  await expect(page.getByRole("button", { name: "Inspect market readiness" })).toBeVisible();
  expect(writes).toEqual([]);

});

test("real Go and Python reader exposes unknown qualification without activation", async ({ page }) => {
  const backend = process.env.MATCHFORGE_MARKET_BACKEND;
  test.skip(!backend, "requires disposable backend harness");
  test.setTimeout(60_000);
  await page.route("http://127.0.0.1:8080/v1/admin/**", async (route) => {
    const response = await route.fetch({ url: route.request().url().replace("http://127.0.0.1:8080", backend!), headers: { ...route.request().headers(), host: new URL(backend!).host } });
    await route.fulfill({ response });
  });
  await page.goto("/admin/data-sync");
  await fillScope(page, process.env.MATCHFORGE_MARKET_COMPETITION!, process.env.MATCHFORGE_MARKET_SEASON!);
  await expect(page.getByText(/Model metadata is not target qualification/)).toBeVisible();
  await page.getByText("Results and goals — 14 target families", { exact: true }).click();
  await expect(page.getByRole("rowheader", { name: "RESULT_BTTS", exact: true })).toBeVisible();
  await expect(page.getByText("DATA_COLLECTION_REQUIRED", { exact: true }).first()).toBeVisible();
  await page.getByText("Provider resource candidates — 0", { exact: true }).click();
  await expect(page.getByText(/No registered candidate resources/)).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
