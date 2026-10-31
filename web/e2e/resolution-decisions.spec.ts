import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("owner approves retained correction through real Go and Python", async ({ page }) => {
  const backend = process.env.MATCHFORGE_RESOLUTION_BACKEND;
  test.skip(!backend || !process.env.MATCHFORGE_RESOLUTION_TARGET, "disposable decision database required");
  test.setTimeout(90_000);
  page.setDefaultTimeout(15_000);
  await page.route("http://127.0.0.1:8080/v1/admin/resolution/**", async (route) => {
    const response = await route.fetch({ url: route.request().url().replace("http://127.0.0.1:8080", backend!), headers: { ...route.request().headers(), host: new URL(backend!).host } });
    await route.fulfill({ response });
  });
  await page.goto("/admin/resolution");
  const row = page.getByRole("row").filter({ hasText: process.env.MATCHFORGE_RESOLUTION_SOURCE! });
  await row.getByRole("button", { name: /Inspect case/ }).click();
  const review = page.getByRole("region", { name: "Case review" });
  await review.getByRole("combobox", { name: "Action", exact: true }).selectOption("CORRECT");
  await review.getByRole("combobox", { name: "Target mapping", exact: true }).selectOption(process.env.MATCHFORGE_RESOLUTION_TARGET!);
  await review.getByRole("combobox", { name: "Retained contradiction", exact: true }).selectOption({ index: 1 });
  await review.getByLabel("Reason", { exact: true }).fill("Owner reviewed exact retained identifiers and prospective impact");
  await review.getByRole("button", { name: "Preview impact and evidence" }).click();
  await expect(review.getByRole("heading", { name: /^QUALIFIED:/ })).toBeVisible();
  const apply = review.getByRole("button", { name: "Approve and apply decision" });
  await expect(apply).toBeDisabled();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await review.getByLabel("Owner credential").fill("resolution-disposable-owner");
  await review.getByRole("checkbox").check();
  await apply.click();
  await expect(review.getByRole("status")).toContainText("Decision recorded", { timeout: 30_000 });
  await expect(review.getByLabel("Owner credential")).toHaveValue("");
  await review.getByRole("button", { name: "Show resolution history" }).click();
  await expect(page.getByRole("cell", { name: "CORRECT", exact: true })).toBeVisible();
});
