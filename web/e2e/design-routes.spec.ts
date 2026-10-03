import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const competition = { id: "31ba91ba-d228-41f7-b5fd-dd9222aa95dc", name: "Premier League", country: "England", continent: "Europe", division: 1, type: "LEAGUE", season: "2026", availability: { fixtures: true, results: true, standings: true, h2h: true, forecast: true, xg: false, team_stats: false }, availability_status: "FORECAST_AVAILABLE", sources: { fixtures: ["api_football"] } };
const performance = { competition_id: competition.id, league: competition.name, country: competition.country, continent: competition.continent, rating: "GOOD", forecasts: 86, outcome_hit_rate: .53, brier: .58, log_loss: .94, baseline_brier: .63, baseline_log_loss: 1.02, exact_score_rate: .12, top_three_score_rate: .31, top_five_score_rate: .45, total_goals_hit_rate: .54, btts_hit_rate: .51, latest_fifty_brier: .56, latest_fifty_log_loss: .91, latest_fifty_baseline_brier: .62, latest_fifty_baseline_log_loss: 1.01 };
const source = { code: "public-source", name: "Public Source", url: "https://example.com", public_predictions: true, prediction_date_available: true, login_required: false, paid_content: false, automated_access_status: "ALLOWED", adapter_status: "ENABLED", known_issues: "None", checked_at: "2026-10-01T00:00:00Z", tracked_selections: 8, settled_selections: 6, correct_selections: 4, settled_hit_rate: .667, matchforge_agreement_rate: .5 };
const predictions = Array.from({ length: 9 }, (_, index) => ({ id: `prediction-${index}`, source: "Public Source", source_page: "https://example.com", prediction_date: "2026-10-01", original_date_text: "2026-10-01", collected_at: `2026-10-01T${String(index).padStart(2, "0")}:00:00Z`, fixture_id: `fixture-${index}`, kickoff_at: "2026-10-02T15:00:00Z", competition: "National League", home_team: `Home ${index + 1}`, away_team: `Away ${index + 1}`, market: "RESULT_1X2", selection: index ? "Away" : "Home", match_status: "MATCHED", matchforge_probability: .5, agreement: "AGREES" }));

test.beforeEach(async ({ page }) => {
  await page.route("http://127.0.0.1:8080/**", async (route) => {
    const url = route.request().url();
    const requestedDay = new URL(url).searchParams.get("date");
    const payload = url.includes("/v1/competitions?") ? { competitions: [competition] }
      : url.includes("/v1/performance?") ? { performance: [performance] }
      : url.includes("external-prediction-sources") ? { sources: [source] }
      : { predictions: predictions.map((prediction) => ({ ...prediction, prediction_date: requestedDay ?? prediction.prediction_date })) };
    await route.fulfill({ json: payload });
  });
});

test("performance uses the approved analytics system", async ({ page }) => {
  await page.goto("/performance");
  await expect(page.getByRole("heading", { name: "League-level performance" })).toBeVisible();
  await expect(page.getByRole("rowheader", { name: /Premier League/ })).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({ path: `test-results/${test.info().project.name}-performance.png`, fullPage: true });
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
