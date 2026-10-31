import { afterEach, expect, it, vi } from "vitest";
import { api } from "@/lib/api";

afterEach(() => vi.unstubAllGlobals());

it("keeps hostile external filters inside the fixed API origin and query", async () => {
  const fetchMock = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ predictions: [], consensus: [], pagination: { page: 1, page_size: 20, total_items: 0, total_pages: 0 } }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const source = "//attacker.invalid/%2f?redirect=https://attacker.invalid#fragment";
  await api.predictions(new URLSearchParams({ source, competition: "../other?x=y&z=1" }));
  const target = new URL(String(fetchMock.mock.calls[0][0]));
  expect(target.origin).toBe(new URL(process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8080").origin);
  expect(target.pathname).toBe("/v1/external-predictions");
  expect(target.searchParams.get("source")).toBe(source);
  expect(target.searchParams.get("competition")).toBe("../other?x=y&z=1");
});
