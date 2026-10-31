import type { Page } from "@playwright/test";

export async function useResolutionBackend(page: Page, backend: string) {
  await page.route("http://127.0.0.1:8080/v1/admin/resolution/**", async (route) => {
    const response = await route.fetch({ url: route.request().url().replace("http://127.0.0.1:8080", backend), headers: { ...route.request().headers(), host: new URL(backend).host } });
    await route.fulfill({ response });
  });
}
