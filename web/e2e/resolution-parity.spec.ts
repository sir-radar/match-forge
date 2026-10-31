import { approveResolutionDecision, recheckResolution, useResolutionBackend } from "./resolution-backend";
import { expect, test } from "@playwright/test";

test("owner rechecks parity and inspects durable blocked verification", async ({ page }) => {
  const backend = process.env.MATCHFORGE_RESOLUTION_BACKEND;
  test.skip(!backend || !process.env.MATCHFORGE_RESOLUTION_PARITY, "disposable parity database required");
  test.setTimeout(90_000);
  await useResolutionBackend(page, backend!);
  await page.goto("/admin/resolution");
  await page.getByRole("button", { name: "Migration Parity", exact: true }).click();
  await page.getByRole("row").filter({ hasText: "parity:identity_and_canonical_state" }).getByRole("button", { name: /Inspect case/ }).click();
  const review = page.getByRole("region", { name: "Case review" });
  await expect(review.getByRole("combobox", { name: "Action", exact: true })).toHaveValue("RECHECK_PARITY");
  await review.getByLabel("Reason", { exact: true }).fill("Recheck retained evidence; preserve incomplete production scopes and known conflicts");
  await approveResolutionDecision(page, review, "resolution-disposable-owner");
  await expect(async () => {
    await recheckResolution(page, review.getByRole("button", { name: "Recheck case evidence" }), "detail");
    const history = review.getByText("Inspect verification history", { exact: true });
    if (await history.getAttribute("aria-expanded") !== "true") {
      const open = await history.evaluate((element) => (element.parentElement as HTMLDetailsElement).open);
      if (!open) await history.click();
    }
    await expect(history.locator("..").getByText("SUCCEEDED", { exact: true }).first()).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 30_000 });
  await expect(review.locator("p").filter({ hasText: /^Status: / })).not.toHaveText("Status: PASS");
  await page.unrouteAll({ behavior: "wait" });
});
