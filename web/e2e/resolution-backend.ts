import { expect, type Locator, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

export async function useResolutionBackend(page: Page, backend: string) {
  await page.route("http://127.0.0.1:8080/v1/admin/resolution/**", async (route) => {
    const response = await route.fetch({ url: route.request().url().replace("http://127.0.0.1:8080", backend), headers: { ...route.request().headers(), host: new URL(backend).host } });
    await route.fulfill({ response });
  });
}

export async function approveResolutionDecision(page: Page, review: Locator, token: string) {
  await review.getByRole("button", { name: "Preview impact and evidence" }).click();
  await expect(review.getByRole("heading", { name: /^QUALIFIED:/ })).toBeVisible();
  await expect(review.getByRole("button", { name: "Approve and apply decision" })).toBeDisabled();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await review.getByLabel("Owner credential").fill(token);
  await review.getByRole("checkbox").check();
  await review.getByRole("button", { name: "Approve and apply decision" }).click();
  await expect(review.getByRole("status")).toContainText("Decision recorded", { timeout: 30_000 });
  await expect(review.getByLabel("Owner credential")).toHaveValue("");
}

export async function recheckResolution(page: Page, button: Locator, view: "detail" | "missing") {
  const refreshed = page.waitForResponse((response) => response.url().includes(`/resolution/${view}?`) && response.status() === 200);
  await button.click();
  await refreshed;
}
