import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const competition = { id: "31ba91ba-d228-41f7-b5fd-dd9222aa95dc", name: "Premier League", country: "England", continent: "Europe", division: 1, type: "LEAGUE", season: "2026", availability: { fixtures: true, results: true, standings: true, h2h: true, forecast: true, xg: false, team_stats: false }, availability_status: "FORECAST_AVAILABLE", sources: { fixtures: ["api_football"] } };
const performance = { competition_id: competition.id, league: competition.name, country: competition.country, continent: competition.continent, rating: "GOOD", forecasts: 86, outcome_hit_rate: .53, brier: .58, log_loss: .94, baseline_brier: .63, baseline_log_loss: 1.02, exact_score_rate: .12, top_three_score_rate: .31, top_five_score_rate: .45, total_goals_hit_rate: .54, btts_hit_rate: .51, latest_fifty_brier: .56, latest_fifty_log_loss: .91, latest_fifty_baseline_brier: .62, latest_fifty_baseline_log_loss: 1.01 };
const performanceRows = Array.from({ length: 45 }, (_, index) => ({ ...performance, competition_id: `competition-${index + 1}`, league: `League ${index + 1}` }));
const fixture = { id: "fixture-1", kickoff_at: "2026-10-04T15:00:00Z", status: "SCHEDULED", home: { id: "home", name: "Home", crest_url: null }, away: { id: "away", name: "Away", crest_url: null }, home_score: null, away_score: null, venue: null, round: null, forecast_availability: "NOT_ENOUGH_HISTORY", forecast: null };
const source = { code: "public-source", name: "Public Source", url: "https://example.com", public_predictions: true, prediction_date_available: true, login_required: false, paid_content: false, automated_access_status: "ALLOWED", adapter_status: "ENABLED", known_issues: "None", checked_at: "2026-10-01T00:00:00Z", tracked_selections: 8, settled_selections: 6, correct_selections: 4, settled_hit_rate: .667, matchforge_agreement_rate: .5 };
const predictions = Array.from({ length: 9 }, (_, index) => ({ id: `prediction-${index}`, source: "Public Source", source_page: "https://example.com", prediction_date: "2026-10-01", original_date_text: "2026-10-01", collected_at: `2026-10-01T${String(index).padStart(2, "0")}:00:00Z`, fixture_id: `fixture-${index}`, kickoff_at: "2026-10-02T15:00:00Z", competition: "National League", home_team: `Home ${index + 1}`, away_team: `Away ${index + 1}`, market: "RESULT_1X2", selection: index ? "Away" : "Home", match_status: "MATCHED", matchforge_probability: .5, agreement: "AGREES" }));

test.beforeEach(async ({ page }) => {
  await page.route("http://127.0.0.1:8080/**", async (route) => {
    const url = route.request().url();
    const requestedDay = new URL(url).searchParams.get("date");
    const payload = url.includes("/v1/competitions?") ? { competitions: [competition] }
      : url.includes("/v1/performance?") ? performancePayload(url)
      : url.includes("/v1/fixtures?") ? { date: requestedDay, groups: [{ competition, fixtures: [fixture] }] }
      : url.includes("external-prediction-sources") ? { sources: [source] }
      : { predictions: predictions.map((prediction) => ({ ...prediction, prediction_date: requestedDay ?? prediction.prediction_date })) };
    await route.fulfill({ json: payload });
  });
});

test("performance uses the approved analytics system", async ({ page }) => {
  if (test.info().project.name === "mobile") await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/performance");
  await expect(page.getByRole("heading", { name: "League-level performance" })).toBeVisible();
  await expect(page.getByRole("rowheader", { name: /League 1$/ })).toBeVisible();
  await expect(page.locator("table tbody tr")).toHaveCount(20);
  await expect(page.getByText("Showing 1–20 of 45 · Page 1 of 3")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("rowheader", { name: /League 21$/ })).toBeVisible();
  await page.getByLabel("Rows per page").selectOption("50");
  await expect(page.locator("table tbody tr")).toHaveCount(45);
  await expect(page.getByText("Showing 1–45 of 45 · Page 1 of 1")).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({ path: `test-results/${test.info().project.name}-performance.png`, fullPage: true });
});

test("landing page offers an accessible back-to-top control", async ({ page }) => {
  if (test.info().project.name === "mobile") await page.setViewportSize({ width: 320, height: 800 });
  await page.emulateMedia({ reducedMotion: "reduce", forcedColors: "active" });
  await page.goto("/");
  await page.evaluate(() => { document.body.style.minHeight = "2000px"; });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight)).toBeGreaterThan(800);
  await page.evaluate(() => { window.scrollTo(0, 500); window.dispatchEvent(new Event("scroll")); });
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThanOrEqual(300);
  const button = page.getByRole("button", { name: "Back to top" });
  await expect(button).toBeVisible();
  await expect(button).toHaveCSS("border-top-style", "solid");
  if (test.info().project.name === "mobile") {
    const bounds = await button.boundingBox();
    expect(bounds && bounds.y + bounds.height).toBeLessThanOrEqual(page.viewportSize()!.height - 62);
  }
  await button.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await expect(page.locator("main")).toBeFocused();
  await page.emulateMedia({ reducedMotion: "reduce", forcedColors: "none" });
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("predictions matches the approved external terminal design", async ({ page }) => {
  if (test.info().project.name === "desktop") await page.setViewportSize({ width: 1187, height: 1600 });
  const consoleErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  const predictionRequestPromise = page.waitForRequest((request) => request.url().includes("/v1/external-predictions?") && request.url().includes("date="));
  await page.goto("/predictions");
  await expect(page.getByRole("heading", { name: "External predictions" })).toBeVisible();
  const consensus = page.locator("section").filter({ has: page.getByRole("heading", { name: "Multi-Source External Consensus" }) });
  await expect(consensus).toBeVisible();
  await expect(consensus.getByText("Home 9 vs Away 9")).toHaveCount(1);
  await expect(page.getByLabel("External selection records table").locator("tbody tr")).toHaveCount(9);
  await expect(page.getByText(/Page \d+ of \d+/)).toHaveCount(0);
  const selectedDay = await page.getByLabel("Prediction day").inputValue();
  const predictionRequest = await predictionRequestPromise;
  expect(predictionRequest.url()).toContain(`date=${selectedDay}`);
  await page.getByRole("button", { name: "Previous day" }).click();
  await expect(page.getByLabel("Prediction day")).not.toHaveValue(selectedDay);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(consoleErrors).toEqual([]);
  await page.screenshot({ path: `test-results/${test.info().project.name}-predictions.png`, fullPage: true });
});

function performancePayload(url: string) {
  const query = new URL(url).searchParams;
  const page = Number(query.get("page") ?? "1");
  const pageSize = Number(query.get("page_size") ?? "20");
  const start = (page - 1) * pageSize;
  return {
    performance: performanceRows.slice(start, start + pageSize),
    pagination: { page, page_size: pageSize, total_items: performanceRows.length, total_pages: Math.ceil(performanceRows.length / pageSize) },
  };
}
