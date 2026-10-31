import { approveResolutionDecision, recheckResolution, useResolutionBackend } from "./resolution-backend";
import { expect, test } from "@playwright/test";

test("owner rehearses the actual isolated projection and sees restored legacy routing", async ({ page }) => {
  const backend = process.env.MATCHFORGE_RESOLUTION_BACKEND;
  test.skip(!backend || !process.env.MATCHFORGE_RESOLUTION_STAGES, "disposable stage database required");
  test.setTimeout(90_000);
  await useResolutionBackend(page, backend!);
  await page.goto("/admin/resolution");
  await page.getByRole("button", { name: "Cutover Controls", exact: true }).click();
  await page.getByRole("row").filter({ hasText: "stage:8" }).getByRole("button", { name: /Inspect case/ }).click();
  const review = page.getByRole("region", { name: "Case review" });
  await review.getByLabel("Reason", { exact: true }).fill("Rehearse real fixture projection and restore prior route; production remains blocked");
  await approveResolutionDecision(page, review, "resolution-disposable-owner");
  await expect(async () => {
    await recheckResolution(page, review.getByRole("button", { name: "Recheck case evidence" }), "detail");
    await expect(review.getByText("REHEARSAL_PASS_ROLLED_BACK", { exact: true }).first()).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 30_000 });
  await expect(review.locator("p").filter({ hasText: /^Status: / })).toHaveText("Status: BLOCKED");
  await page.unrouteAll({ behavior: "wait" });
});
