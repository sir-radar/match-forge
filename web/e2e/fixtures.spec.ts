import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const competition = { id: "31ba91ba-d228-41f7-b5fd-dd9222aa95dc", name: "Premier League", country: "England", continent: "Europe", division: 1, type: "LEAGUE", season: "2026", availability: { fixtures: true, results: true, standings: true, h2h: true, forecast: true, xg: false, team_stats: false }, availability_status: "FORECAST_AVAILABLE", sources: { fixtures: ["api_football"] } };
const fixture = { id: "1f3ce86e-743f-49b7-a957-4725495329b1", kickoff_at: "2026-09-29T15:00:00Z", status: "SCHEDULED", home: { id: "bed584cb-1830-42a2-904b-dbf97c526a62", name: "Arsenal", crest_url: null }, away: { id: "780bd040-4ad6-4e40-af03-b2fe9f52e140", name: "Chelsea", crest_url: null }, home_score: null, away_score: null, venue: "Emirates Stadium", round: "Round 6", forecast_availability: "FORECAST_AVAILABLE", forecast: { id: "6b0326f4-bc7c-4ec0-a0ca-b6f0ca6477ea", expected_home_goals: 1.5, expected_away_goals: 1.1, probabilities: { home: .46, draw: .27, away: .27 } } };
const duplicateForm = { kickoff_at: "2026-08-30T14:00:00+01:00", opponent: "Brentford FC", venue: "HOME", goals_for: 2, goals_against: 1, result: "W" };

for (const name of ["Europa League", "Conference League", "Botola Pro"]) {
  test(`${name} preserves canonical representatives through polling, navigation and reload`, async ({ page }) => {
    let updated = false;
    await page.clock.install();
    await page.route("http://127.0.0.1:8080/v1/fixtures?**", async (route) => {
      const current = updated ? { ...fixture, id: "admitted-representative", status: "LIVE", home_score: 1, away_score: 0 } : { ...fixture, id: "provisional" };
      await route.fulfill({ json: { groups: [{ competition: { ...competition, name }, fixtures: [current, { ...fixture, id: "separate-cup-leg" }] }] } });
    });
    await page.goto("/");
    const rows = page.getByRole("button", { name: /Arsenal.*Chelsea/ });
    await expect(rows).toHaveCount(2);
    updated = true;
    await page.clock.runFor(45_000);
    await expect(page.getByText("1–0", { exact: true })).toBeVisible();
    await expect(page.locator('[aria-controls="fixture-panel-provisional"]')).toHaveCount(0);
    await expect(rows).toHaveCount(2);
    await page.getByRole("button", { name: "Next day" }).click();
    await expect(rows).toHaveCount(2);
    await page.getByRole("button", { name: "Previous day" }).click();
    await expect(rows).toHaveCount(2);
    await page.reload();
    await expect(rows).toHaveCount(2);
    await expect(page.getByRole("heading", { name: `England — ${name}` })).toHaveCount(1);
    await expect(page.locator('[aria-controls="fixture-panel-admitted-representative"]')).toHaveCount(1);
    await expect(page.locator('[aria-controls="fixture-panel-separate-cup-leg"]')).toHaveCount(1);
  });
}

test.beforeEach(async ({ page }) => {
  await page.route("http://127.0.0.1:8080/**", async (route) => {
    const url = route.request().url();
    const payload = url.includes("/v1/competitions?") ? { competitions: [competition] }
      : url.includes("/v1/fixtures?") ? { groups: [{ competition, fixtures: [fixture] }] }
      : url.includes("/context") ? { fixture_id: fixture.id, home_form: [duplicateForm, duplicateForm], away_form: [], h2h: [], h2h_summary: { meetings: 0, home_wins: 0, draws: 0, away_wins: 0, home_goals: 0, away_goals: 0 }, home_team_statistics: null, away_team_statistics: null, standings: [], data_availability: {} }
      : url.includes("/forecasts/") ? { ...fixture.forecast, fixture_id: fixture.id, model_label: "MVP_FORECAST", model_algorithm_version: "transferable-rolling-goals-poisson-v1", created_at: "2026-09-29T06:00:00Z", football_cutoff: "2026-09-29T06:00:00Z", knowledge_cutoff: "2026-09-29T06:00:00Z", knowledge_mode: "bitemporal", publication_mode: "MVP_OWNER_AUTHORIZED", score_matrix: [{ home_goals: 1, away_goals: 0, probability: .14 }] }
      : { predictions: [] };
    await route.fulfill({ json: payload });
  });
});

test("fixture expands inline", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
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
  await expect(page.locator(".team-form").first().locator("b")).toHaveCount(2);
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
  expect(consoleErrors).toEqual([]);
  await page.screenshot({ path: `test-results/${test.info().project.name}-expanded.png`, fullPage: true });
});

for (const version of ["legacy-compact-index-v1", "compact-buckets-v2"]) {
  test(`${version} renders aggregate tail categories`, async ({ page }) => {
    await page.route("http://127.0.0.1:8080/v1/fixtures/*/forecasts/*", async (route) => {
      const cell = { home_goals: 5, away_goals: 5, probability: .14 };
      await route.fulfill({ json: {
        ...fixture.forecast, fixture_id: fixture.id, model_label: "MVP_FORECAST",
        model_algorithm_version: "transferable-rolling-goals-poisson-v1",
        created_at: "2026-09-29T06:00:00Z", football_cutoff: "2026-09-29T06:00:00Z",
        knowledge_cutoff: "2026-09-29T06:00:00Z", knowledge_mode: "bitemporal",
        publication_mode: "MVP_OWNER_AUTHORIZED", score_matrix_version: version,
        score_matrix: [version === "compact-buckets-v2" ? { ...cell,
          home_label: "5+", away_label: "5+", home_bucket_kind: "AT_LEAST",
          away_bucket_kind: "AT_LEAST" } : cell],
      } });
    });
    await page.goto("/");
    await page.getByRole("button", { name: /Arsenal.*Chelsea/ }).click();
    await expect(page.getByText("5+–5+", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("5–5", { exact: true })).toHaveCount(0);
    await expect(page.getByText(/Most likely score category is/)).toBeVisible();
  });
}

test("mobile uses the designed compact navigation and hides desktop rail", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "mobile-only assertion");
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Mobile navigation" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Competition coverage" })).toBeHidden();
  await expect(page.getByRole("button", { name: /Arsenal.*Chelsea/ })).toBeVisible();
  await page.screenshot({ path: "test-results/mobile-collapsed.png", fullPage: true });
});


test("production SSR date is stable and cleared or delayed dates cannot relabel old fixtures", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  let blockedDay = ""; let release!: () => void;
  const delayed = new Promise<void>((done) => { release = done; });
  await page.route("http://127.0.0.1:8080/v1/fixtures?**", async (route) => {
    const day = new URL(route.request().url()).searchParams.get("date")!;
    if (day === blockedDay) await delayed;
    await route.fulfill({ json: { date: day, groups: [{ competition, fixtures: [{ ...fixture, id: `fixture-${day}`, home: { ...fixture.home, name: `Home ${day}` }, kickoff_at: `${day}T15:00:00Z` }] }] } });
  });
  const document = await page.goto("/");
  const html = await document!.text();
  const serverDay = html.match(/type="date"[^>]*value="([0-9-]+)"/)![1];
  const input = page.getByLabel("Selected date");
  await expect(input).toHaveValue(serverDay);
  await expect(page.getByRole("button", { name: new RegExp(`Home ${serverDay}.*Chelsea`) })).toBeVisible();
  await input.fill(""); await expect(page.locator(".fixture-workbench").getByRole("alert")).toContainText("Choose a valid fixture date");
  await expect(input).toHaveValue(serverDay);
  const next = new Date(`${serverDay}T00:00:00Z`); next.setUTCDate(next.getUTCDate() + 1); blockedDay = next.toISOString().slice(0, 10);
  await input.fill(blockedDay);
  await expect(page.getByRole("button", { name: new RegExp(`Home ${serverDay}.*Chelsea`) })).toHaveCount(0);
  await expect(page.getByText("Loading fixtures", { exact: true })).toBeVisible();
  await input.fill(serverDay);
  await expect(page.getByRole("button", { name: new RegExp(`Home ${serverDay}.*Chelsea`) })).toBeVisible();
  release();
  await expect(page.getByRole("button", { name: new RegExp(`Home ${blockedDay}.*Chelsea`) })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("tab keys wrap, expose one active panel, and retrieve immutable forecast history", async ({ page }) => {
  const history = { forecasts: [{ forecast_id: fixture.forecast.id, fixture_id: fixture.id, issued_at: "2026-09-29T06:00:00Z", football_cutoff: "2026-09-29T06:00:00Z", knowledge_cutoff: "2026-09-29T06:00:00Z", forecast_horizon: "24H", supersedes_forecast_id: null, model_id: "transferable-rolling-goals-poisson-v1", artifact_sha256: "a".repeat(64), predictive_input_snapshot_sha256: "b".repeat(64), context_snapshot_sha256: "c".repeat(64), payload_sha256: "d".repeat(64), revision_reason_codes: ["INITIAL_FORECAST"], new_information_ids: [], probability_payload: { expected_home_goals: 1.5, expected_away_goals: 1.1, probabilities: fixture.forecast.probabilities, score_matrix_version: "legacy-compact-index-v1", score_matrix: [{ home_goals: 5, away_goals: 0, probability: .1 }] } }] };
  await page.route(`http://127.0.0.1:8080/v1/fixtures/${fixture.id}/forecasts`, (route) => route.fulfill({ json: history }));
  await page.goto("/"); await page.getByRole("button", { name: /Arsenal.*Chelsea/ }).click();
  const overview = page.getByRole("tab", { name: "Overview" }); await overview.focus();
  await page.keyboard.press("ArrowRight"); await expect(page.getByRole("tab", { name: "Markets" })).toBeFocused();
  await page.keyboard.press("End"); await expect(page.getByRole("tab", { name: "Forecast history" })).toBeFocused();
  await expect(page.getByRole("heading", { name: "Selected published revision" })).toBeVisible();
  await expect(page.getByRole("tabpanel")).toHaveCount(1);
  const selected = page.getByRole("tab", { selected: true });
  expect(await selected.getAttribute("aria-controls")).toBe(await page.getByRole("tabpanel").getAttribute("id"));
  await expect(page.getByRole("button", { name: `View revision ${fixture.forecast.id}` })).toHaveAttribute("aria-pressed", "true");
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.keyboard.press("Home"); await expect(page.getByRole("tab", { name: "Live Match" })).toBeFocused();
  await page.keyboard.press("ArrowLeft"); await expect(page.getByRole("tab", { name: "Forecast history" })).toBeFocused();
});
