// @vitest-environment node
import { describe, expect, it, vi, afterEach } from "vitest";
import { readFileSync } from "node:fs";
import { parseResolutionPage, resolutionApi, resolutionViews } from "@/lib/resolution";
const page = { items: [{ case_key: "team:one", status: "UNRESOLVED" }], page: 1, page_size: 20, total: 1, counts: { UNRESOLVED: 1 }, groups: [] };
afterEach(() => vi.unstubAllGlobals());
describe("read-only resolution transport", () => {
  it("rejects malformed identities, counts and pagination", () => {
    expect(parseResolutionPage(page).total).toBe(1);
    expect(parseResolutionPage({ ...page, groups: [{ provider: "test", kind: "team", status: "UNRESOLVED", reason: "proof required", count: 1, country: null }] }).groups).toHaveLength(1);
    for (const invalid of [{ ...page, counts: { UNRESOLVED: -1 } }, { ...page, items: [{}] }, { ...page, page: 0 }, { ...page, total: NaN }, { ...page, blockers: [false] }, { ...page, scope: false }, { ...page, items: [{ case_key: "team:one", status: null }] }, { ...page, groups: [{ provider: "test", kind: "team", reason: "test", status: "UNRESOLVED", count: 2 }] }]) expect(() => parseResolutionPage(invalid)).toThrow();
  });
  it("exposes only reads, forwards cancellation, and disables private response caching", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(async () => new Response(JSON.stringify(page), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    const controller = new AbortController();
    await resolutionApi.page("identity", new URLSearchParams({ q: "team" }), controller.signal);
    expect(Object.keys(resolutionApi)).toEqual(["page", "detail", "preview", "apply", "batchPreview", "batchApply"]);
    const options = fetch.mock.calls[0][1];
    expect(options?.signal).toBe(controller.signal);
    expect(options?.cache).toBe("no-store");
    expect(options?.method).toBeUndefined();
    expect(options?.body).toBeUndefined();
  });
});

it("keeps the documented view names aligned with the client", () => {
  const specification = readFileSync(new URL("../../docs/api/openapi.yaml", import.meta.url), "utf8");
  const route = specification.split("  /v1/admin/resolution/{view}:")[1].split("\n  /v1/")[0];
  const views = route.match(/name: view.*enum: \[([^\]]+)\]/)![1].split(", ");
  expect(views.sort()).toEqual([...resolutionViews, "detail"].sort());
});
