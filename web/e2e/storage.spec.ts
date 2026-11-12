import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixture from "../test-fixtures/storage-status.json";

test("storage dry-run protections, keyboard, reflow and accessibility", async ({ page }, info) => {
  await page.route("**/v1/admin/storage", (route) => route.fulfill({ json: fixture, headers: { "Access-Control-Allow-Origin": "http://127.0.0.1:3009" } }));
  await page.goto("/admin/storage");
  const refresh = page.getByRole("button", { name: "Refresh storage status" });
  await refresh.focus(); await page.keyboard.press("Enter");
  await expect(page.getByText("0 bytes")).toBeVisible();
  const resource = page.locator("summary").filter({ hasText: "cluster/football_rehearsal" });
  await resource.focus(); await page.keyboard.press("Enter");
  await expect(page.getByText("Current post-rehearsal recovery is unverified")).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: info.outputPath("storage-admin.png"), fullPage: true });
  await page.setViewportSize({ width: 320, height: 850 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.addStyleTag({ content: "p {line-height:1.5!important;margin-bottom:2em!important} * {letter-spacing:.12em!important;word-spacing:.16em!important}" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
  await expect(refresh).toBeVisible();
});
