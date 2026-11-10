import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixture from "../test-fixtures/backup-status.json";

test("manual backup confirmation, progress, cancellation and accessible reflow", async ({ page }, testInfo) => {
  let status = "";
  let submissions = 0;
  let requestId = "10000000-0000-4000-8000-000000000001";
  const run = () => ({ run_id: requestId, sync_type: "MANUAL_BACKUP", status, requested_at: "2026-11-10T11:00:00Z", started_at: null, finished_at: null, requested_date: null, parameters: {}, summary: { current_phase: "Verifying snapshot files" }, error_message: null, log_path: null });
  await page.route("http://127.0.0.1:8080/v1/admin/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/stop")) { status = "CANCELLED"; await route.fulfill({ json: run() }); return; }
    if (route.request().method() === "POST" && url.endsWith("/backup")) {
      expect(route.request().postDataJSON().confirmed).toBe(true);
      requestId = route.request().postDataJSON().request_id;
      status = "QUEUED"; submissions++; await route.fulfill({ status: 202, json: run() }); return;
    }
    await route.fulfill({ json: { ...fixture, runs: status ? [run()] : [], safe_to_eject: !status } });
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/admin/backup");
  await page.getByRole("button", { name: "Refresh drive status" }).click();
  const backup = page.getByRole("button", { name: "Back Up Now" });
  await expect(backup).toBeEnabled();
  expect(submissions).toBe(0);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({ path: `../.local/foundation/backup-admin-${testInfo.project.name}.png`, fullPage: true });
  await backup.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Confirm manual backup" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Confirm backup" })).toBeFocused();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Backup in progress" })).toBeVisible();
  expect(submissions).toBe(1);
  await expect(backup).toBeDisabled();
  await page.getByRole("button", { name: "Cancel backup" }).click();
  await expect(page.getByRole("cell", { name: "CANCELLED", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 320, height: 850 });
  await expect(backup).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.addStyleTag({ content: "p {line-height:1.5!important;margin-bottom:2em!important} * {letter-spacing:.12em!important;word-spacing:.16em!important}" });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.emulateMedia({ forcedColors: "active" });
  await expect(backup).toBeVisible();
});
