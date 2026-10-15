import { expect, test } from "@playwright/test";
import { writeFile } from "node:fs/promises";

type FixtureResponse = { groups: { competition: { id: string; name: string }; fixtures: { id: string; status: string }[] }[] };

for (const scenario of [
  { id: "ceb568b3-31fc-5740-93de-a4cc9bbad960", competition: "UEFA Europa League", date: "2026-10-15", count: 18 },
  { id: "09a4d8a1-2c8c-5c11-8dc8-2075b4203236", competition: "UEFA Europa Conference League", date: "2026-10-15", count: 18 },
  { id: "104fa69b-4af3-53a3-b866-d3a4c0ce1025", competition: "Botola Pro", date: "2026-10-14", count: 1 },
]) {
  test(`real serving representatives: ${scenario.competition}`, async ({ page }, testInfo) => {
    test.skip(process.env.MATCHFORGE_REAL_PROVIDER_E2E !== "true", "requires the migrated local operational database");
    await page.clock.install();
    const responses: { url: string; payload: FixtureResponse }[] = [];
    page.on("response", async (response) => {
      if (response.url().includes("/v1/fixtures?") && response.ok()) {
        responses.push({ url: response.url(), payload: await response.json() as FixtureResponse });
      }
    });
    await page.goto("/");
    await page.getByLabel("Selected date").fill(scenario.date);
    const league = scenario.id;
    await expect(page.getByRole("combobox", { name: "League", exact: true }).locator(`option[value="${league}"]`)).toHaveText(scenario.competition);
    await page.getByRole("combobox", { name: "League", exact: true }).selectOption(league);
    await expect(page.locator(".fixture-group")).toHaveCount(1);
    await expect(page.locator("article.fixture")).toHaveCount(scenario.count);
    await expect.poll(() => responses.some((item) => item.url.includes(`competition=${league}`))).toBe(true);
    const selected = responses.filter((item) => item.url.includes(`competition=${league}`)).at(-1)!;
    expect(selected.payload.groups).toHaveLength(1);
    expect(selected.payload.groups[0].fixtures).toHaveLength(scenario.count);
    const ids = selected.payload.groups[0].fixtures.map((fixture) => fixture.id);
    expect(new Set(ids).size).toBe(scenario.count);
    const controls = await page.locator(".fixture-summary").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("aria-controls")));
    expect(controls.sort()).toEqual(ids.map((id) => `fixture-panel-${id}`).sort());
    await page.getByRole("button", { name: "Next day" }).click();
    await page.getByRole("button", { name: "Previous day" }).click();
    await expect(page.locator("article.fixture")).toHaveCount(scenario.count);
    await page.clock.fastForward(45_000);
    await expect(page.locator(".fixture-group")).toHaveCount(1);
    await expect(page.locator("article.fixture")).toHaveCount(scenario.count);
    await page.screenshot({ path: testInfo.outputPath("representatives.png"), fullPage: true });
    await writeFile(testInfo.outputPath("api-responses.json"), JSON.stringify(responses, null, 2));
    await page.reload();
    await page.getByLabel("Selected date").fill(scenario.date);
    await page.getByRole("combobox", { name: "League", exact: true }).selectOption(league);
    await expect(page.locator("article.fixture")).toHaveCount(scenario.count);
  });
}
