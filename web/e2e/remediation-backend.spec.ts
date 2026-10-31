import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// Forward the browser's configured origin to the disposable real API. No response
// data is synthesized here; ordinary production routers, workers and SQL run.
test("normal scheduler publishes reports consumed by all public routes", async ({ page, request }) => {
  const backend = process.env.MATCHFORGE_REMEDIATION_BACKEND;
  test.skip(!backend, "started by the disposable database integration harness");
  test.setTimeout(90_000);
  await page.route("http://127.0.0.1:8080/**", async (route) => {
    const response = await route.fetch({ url: route.request().url().replace("http://127.0.0.1:8080", backend!) });
    await route.fulfill({ response });
  });
  // The integration harness observes a successful scheduled worker before
  // launching this browser. Its frozen fixture must already have a report.
  const response = await request.get(`${backend}/v1/performance?page_size=20`);
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  expect(data.performance?.[0]?.report_status).toBe("READY");
  await page.goto("/performance");
  await expect(page.getByRole("rowheader", { name: /Test League$/ })).toBeVisible();
  await page.goto("/");
  await page.getByLabel("Selected date").fill("2030-01-01");
  const fixture = page.getByRole("button", { name: /Home.*Away/ });
  await expect(fixture).toBeVisible();
  await fixture.click();
  await expect(page.getByRole("heading", { name: "Recent form" })).toBeVisible();
  for (const tab of ["H2H context", "Team statistics", "Markets", "Score matrix", "Diagnostics"]) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    await expect(page.getByRole("tabpanel")).toBeVisible();
    await expect(page.getByRole("tabpanel").getByRole("alert")).toHaveCount(0);
  }
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  const selectionsResponse = await request.get(`${backend}/v1/external-predictions?page_size=20`);
  expect(selectionsResponse.ok()).toBeTruthy();
  const selections = await selectionsResponse.json();
  expect(selections.predictions).toHaveLength(1);
  const emptyDay = new Date(`${selections.predictions[0].prediction_date}T00:00:00Z`);
  emptyDay.setUTCDate(emptyDay.getUTCDate() - 1);
  await page.goto("/predictions");
  await page.getByLabel("Prediction day").fill(emptyDay.toISOString().slice(0, 10));
  await expect(page.getByRole("heading", { name: "No approved external selections" })).toBeVisible();
  // PostgreSQL CURRENT_DATE and the display timezone can cross midnight on
  // different days. Select retained fixture data rather than the host's today.
  await page.getByLabel("Prediction day").fill(selections.predictions[0].prediction_date);
  await expect(page.getByRole("cell", { name: "Home vs Away" })).toBeVisible();
  await expect(page.getByText("Records: Loaded")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: /First capture/ })).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
