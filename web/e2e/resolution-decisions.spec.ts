import { approveResolutionDecision, useResolutionBackend } from "./resolution-backend";
import { expect, test } from "@playwright/test";

test("owner approves retained correction through real Go and Python", async ({ page }) => {
  const backend = process.env.MATCHFORGE_RESOLUTION_BACKEND;
  test.skip(!backend || !process.env.MATCHFORGE_RESOLUTION_TARGET, "disposable decision database required");
  test.setTimeout(90_000);
  page.setDefaultTimeout(15_000);
  await useResolutionBackend(page, backend!);
  await page.goto("/admin/resolution");
  const row = page.getByRole("row").filter({ hasText: process.env.MATCHFORGE_RESOLUTION_SOURCE! });
  await row.getByRole("button", { name: /Inspect case/ }).click();
  const review = page.getByRole("region", { name: "Case review" });
  await review.getByRole("combobox", { name: "Action", exact: true }).selectOption("CORRECT");
  await review.getByRole("combobox", { name: "Target mapping", exact: true }).selectOption(process.env.MATCHFORGE_RESOLUTION_TARGET!);
  await review.getByRole("combobox", { name: "Retained contradiction", exact: true }).selectOption({ index: 1 });
  await review.getByLabel("Reason", { exact: true }).fill("Owner reviewed exact retained identifiers and prospective impact");
  await approveResolutionDecision(page, review, "resolution-disposable-owner");
  await review.getByRole("button", { name: "Show resolution history" }).click();
  await expect(page.getByRole("cell", { name: "CORRECT", exact: true })).toBeVisible();
});
