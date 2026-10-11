import { expect, test } from "@playwright/test";

test("real mapped PitchAPI result reaches the browser", async ({ page }) => {
  test.skip(
    process.env.MATCHFORGE_REAL_PROVIDER_E2E !== "true",
    "requires the local Go API and migrated development database",
  );
  await page.goto("/");
  await page.getByLabel("Selected date").fill("2026-10-09");
  const fixture = page.getByRole("button", { name: /Fluminense.*Coritiba/ });
  await expect(fixture).toBeVisible();
  await expect(fixture).toContainText("4–0");
  await expect(fixture).toContainText("FT");
  await fixture.click();
  await expect(page.getByText(/pitchapi · stale · updated/)).toBeVisible();
});
