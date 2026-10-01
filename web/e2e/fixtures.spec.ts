import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const competition = { id: "31ba91ba-d228-41f7-b5fd-dd9222aa95dc", name: "Premier League", country: "England", continent: "Europe", division: 1, type: "LEAGUE", season: "2026", availability: { fixtures: true, results: true, standings: true, h2h: true, forecast: true, xg: false, team_stats: false }, availability_status: "FORECAST_AVAILABLE", sources: { fixtures: ["api_football"] } };
const fixture = { id: "1f3ce86e-743f-49b7-a957-4725495329b1", kickoff_at: "2026-09-29T15:00:00Z", status: "SCHEDULED", home: { id: "bed584cb-1830-42a2-904b-dbf97c526a62", name: "Arsenal", crest_url: null }, away: { id: "780bd040-4ad6-4e40-af03-b2fe9f52e140", name: "Chelsea", crest_url: null }, home_score: null, away_score: null, venue: "Emirates Stadium", round: "Round 6", forecast_availability: "FORECAST_AVAILABLE", forecast: { id: "6b0326f4-bc7c-4ec0-a0ca-b6f0ca6477ea", expected_home_goals: 1.5, expected_away_goals: 1.1, probabilities: { home: .46, draw: .27, away: .27 } } };

test.beforeEach(async ({ page }) => {
  await page.route("http://127.0.0.1:8080/**", async (route) => {
    const url = route.request().url();
    const payload = url.includes("/v1/competitions?") ? { competitions: [competition] }
      : url.includes("/v1/fixtures?") ? { groups: [{ competition, fixtures: [fixture] }] }
      : url.includes("/context") ? { fixture_id: fixture.id, home_form: [], away_form: [], h2h: [], h2h_summary: { meetings: 0, home_wins: 0, draws: 0, away_wins: 0, home_goals: 0, away_goals: 0 }, home_team_statistics: null, away_team_statistics: null, standings: [], data_availability: {} }
      : url.includes("/forecasts/") ? { ...fixture.forecast, fixture_id: fixture.id, model_label: "MVP_FORECAST", model_algorithm_version: "transferable-rolling-goals-poisson-v1", created_at: "2026-09-29T06:00:00Z", football_cutoff: "2026-09-29T06:00:00Z", knowledge_cutoff: "2026-09-29T06:00:00Z", knowledge_mode: "bitemporal", publication_mode: "MVP_OWNER_AUTHORIZED", score_matrix: [{ home_goals: 1, away_goals: 0, probability: .14 }] }
      : { predictions: [] };
    await route.fulfill({ json: payload });
  });
});

test("fixture expands inline", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("svg[data-icon]")).toHaveCount(11);
  await expect(page.locator('svg[data-icon="chevron-left"]')).toHaveCSS("width", "16px");
  await expect(page.locator('svg[data-icon="chevron-left"]')).toHaveCSS("height", "16px");
  const fixtureRow = page.getByRole("button", { name: /Arsenal.*Chelsea/ });
  await expect(fixtureRow).toBeVisible();
  await fixtureRow.click();
  await expect(page.locator('svg[data-icon="verified"]')).toBeVisible();
  await expect(page.getByRole("tab", { name: "Markets" })).toBeVisible();
  await expect(page.getByText("Model boundary")).toBeVisible();
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
  await page.screenshot({ path: `test-results/${test.info().project.name}-expanded.png`, fullPage: true });
});

test("mobile uses the designed compact navigation and hides desktop rail", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "mobile-only assertion");
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Mobile navigation" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Competition coverage" })).toBeHidden();
  await expect(page.getByRole("button", { name: /Arsenal.*Chelsea/ })).toBeVisible();
  await page.screenshot({ path: "test-results/mobile-collapsed.png", fullPage: true });
});
