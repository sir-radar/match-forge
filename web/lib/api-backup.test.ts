import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import fixture from "@/test-fixtures/backup-status.json";

describe("backup status requests", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each([
    [404, /running API does not support Backup & Recovery/],
    [403, /configured Admin origin/],
    [500, /API could not check backup status \(HTTP 500\)/],
    [503, /API could not check backup status \(HTTP 503\)/],
    [504, /timed out/],
  ] as const)("reports HTTP %i without exposing its body", async (status, message) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("private backend detail", { status })));
    const result = await api.backup(undefined, "http://127.0.0.1:3000");
    expect(result).toEqual({ view: null, error: expect.stringMatching(message) });
    expect(result.error).not.toContain("private backend detail");
  });

  it.each([false, true])("diagnoses a network or CORS failure (browser=%s)", async (browser) => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("private network detail")));
    const result = await api.backup(undefined, browser ? undefined : "http://127.0.0.1:3000");
    expect(result.error).toMatch(browser ? /cross-origin/ : /web server could not reach/);
    expect(result.error).not.toContain("private network detail");
  });

  it("distinguishes a deadline from a network failure", async () => {
    const deadline = new AbortController();
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(deadline.signal);
    vi.stubGlobal("fetch", vi.fn(async (_url: string, { signal }: RequestInit) => {
      return new Promise((_resolve, reject) => {
        signal?.addEventListener("abort", () => reject(signal.reason), { once: true });
      });
    }));
    const request = api.backup();
    deadline.abort(new DOMException("private timeout detail", "TimeoutError"));
    expect((await request).error).toMatch(/timed out/);
  });

  it.each(["not JSON", JSON.stringify({ availability: { state: "READY" } })])("rejects incompatible data", async (body) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(body)));
    expect((await api.backup()).error).toMatch(/incompatible backup status/);
  });

  it("keeps authorized SSR requests uncached and preserves valid status", async () => {
    const origin = "http://127.0.0.1:3000";
    const fetch = vi.fn(async () => Response.json(fixture));
    vi.stubGlobal("fetch", fetch);
    const result = await api.backup(undefined, origin);
    expect(result).toMatchObject({ view: { availability: { state: "READY" } }, error: null });
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/v1\/admin\/backup$/), expect.objectContaining({
      cache: "no-store", headers: { Accept: "application/json", Origin: origin },
    }));
  });
});
