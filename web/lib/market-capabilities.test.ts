// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it, afterEach, vi } from "vitest";
import fixture from "@/test-fixtures/market-capability-summary.json";
import { MARKET_STATUSES, parseMarketCapabilitySummary } from "@/lib/contracts";
import { api } from "@/lib/api";

describe("market capability boundary", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("accepts diagnostic metadata with explicit unqualified inputs and no production claim", () => {
    const value = parseMarketCapabilitySummary(fixture);
    expect(value.authoritative).toBe(false);
    expect(value.markets[0].publication_status).toBe("UNKNOWN");
    expect(value.markets[0].unqualified_inputs).toEqual(["regulation_score"]);
  });
  it.each([
    { authoritative: true }, { read_only: "off" }, { automatic_promotion: true }, { contract_version: "2" },
    { knowledge_cutoff: "2026-10-31" }, { markets: [fixture.markets[0], fixture.markets[0]] },
    { markets: [{ ...fixture.markets[0], status: "APPROVED" }] },
    { markets: [{ ...fixture.markets[0], model_artifact_sha256: "invalid" }] },
    { markets: [{ ...fixture.markets[0], model_version: null }] },
    { markets: [{ ...fixture.markets[0], semantic_version: "another_target-v1" }] },
  ])("rejects malformed or misleading diagnostics %j", (change) => {
    expect(() => parseMarketCapabilitySummary({ ...fixture, ...change })).toThrow();
  });
  it("binds the response to all requested scope and cutoff values", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(fixture))));
    const scope = { competition_id: fixture.competition_id, season_id: fixture.season_id, knowledge_cutoff: fixture.knowledge_cutoff };
    await expect(api.marketCapabilities(scope)).resolves.toMatchObject(scope);
    await expect(api.marketCapabilities({ ...scope, season_id: "other" })).rejects.toThrow(/scope mismatch/);
    await expect(api.marketCapabilities({ ...scope, knowledge_cutoff: "2026-10-30T00:00:00Z" })).rejects.toThrow(/scope mismatch/);
  });
  it("binds diagnostic statuses to Python and OpenAPI", () => {
    const python = readFileSync(new URL("../../python/football/src/football/product/market_capabilities.py", import.meta.url), "utf8");
    const block = python.split("class MarketStatus(StrEnum):")[1].split("class SourceCompatibility")[0];
    const statuses = [...block.matchAll(/= "([A-Z_]+)"/g)].map((match) => match[1]);
    expect([...MARKET_STATUSES]).toEqual(statuses);
    const openapi = readFileSync(new URL("../../docs/api/openapi.yaml", import.meta.url), "utf8");
    const documented = openapi.split("    MarketDiagnostic:\n")[1].split("    MarketCapabilitySummary:")[0];
    for (const status of statuses) expect(documented).toContain(`"${status}"`);
  });
});
