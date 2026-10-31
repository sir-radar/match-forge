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
  await expect.poll(async () => {
    const response = await request.get(`${backend}/v1/performance?page_size=20`);
    const data = await response.json();
    return data.performance?.[0]?.report_status;
  }, { timeout: 60_000 }).toBe("READY");
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
  await page.goto("/predictions");
  await expect(page.getByRole("cell", { name: "Home vs Away" })).toBeVisible();
  await expect(page.getByText("Records: Loaded")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: /First capture/ })).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});
