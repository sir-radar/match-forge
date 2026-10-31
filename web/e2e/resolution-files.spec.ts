import { approveResolutionDecision, recheckResolution, useResolutionBackend } from "./resolution-backend";
import { expect, test } from "@playwright/test";

test("owner recovers original registered bytes through real Admin", async ({ page }) => {
  const backend = process.env.MATCHFORGE_RESOLUTION_BACKEND;
  test.skip(!backend || !process.env.MATCHFORGE_RESOLUTION_FILE_CASE, "disposable file recovery database required");
  test.setTimeout(90_000);
  await useResolutionBackend(page, backend!);
  await page.goto("/admin/resolution");
  await page.getByRole("button", { name: "Missing Data", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: process.env.MATCHFORGE_RESOLUTION_FILE_CASE! });
  await row.getByRole("button", { name: /Inspect case/ }).click();
  const review = page.getByRole("region", { name: "Case review" });
  await review.getByRole("combobox", { name: "Action", exact: true }).selectOption("RECOVER");
  await review.getByRole("combobox", { name: "Original registered target", exact: true }).selectOption(process.env.MATCHFORGE_RESOLUTION_FILE_TARGET!);
  await review.getByRole("textbox", { name: /Retained recovery path/ }).fill("recovery/original.json");
  await review.getByLabel("Reason", { exact: true }).fill("Owner verified original retained bytes and checksum");
  await approveResolutionDecision(page, review, "resolution-disposable-owner");
  await expect(async () => {
    await recheckResolution(page, page.getByRole("button", { name: "Recheck current view" }), "missing");
    await expect(page.getByRole("row").filter({ hasText: process.env.MATCHFORGE_RESOLUTION_FILE_CASE! })).toHaveCount(0, { timeout: 1500 });
  }).toPass({ timeout: 30_000 });
  await page.unrouteAll({ behavior: "wait" });
});
