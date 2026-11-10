// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("public fixture status contract", () => {
  it("binds live ordering evidence to OpenAPI and the Go response", () => {
    const specification = readFileSync(new URL("../../docs/api/openapi.yaml", import.meta.url), "utf8");
    const response = readFileSync(new URL("../../go/api/internal/app/product.go", import.meta.url), "utf8");
    expect(specification).toMatch(/ordering_basis:.*enum: \[UNKNOWN, MATCH_CLOCK, PROVIDER_TIMESTAMP\]/);
    for (const field of ["ordering_basis", "source_updated_at", "score_conflict"]) {
      expect(specification).toContain(`${field}:`);
      expect(response).toContain(`json:"${field},omitempty"`);
    }
  });
  it("documents both fixture responses using the canonical SQL states", () => {
    const migration = readFileSync(new URL("../../infrastructure/migrations/202610090300_operational_provider_sync.sql", import.meta.url), "utf8");
    const constraint = migration.match(/ADD CONSTRAINT product_fixtures_status_check CHECK \(status IN \(([\s\S]*?)\)\)/)![1];
    const canonical = [...constraint.matchAll(/'([A-Z_]+)'/g)].map((match) => match[1]).sort();
    expect(canonical).toHaveLength(10);
    const specification = readFileSync(new URL("../../docs/api/openapi.yaml", import.meta.url), "utf8");
    for (const name of ["Fixture", "LiveMatch"]) {
      const status = specification.match(new RegExp(`^    ${name}:\\n[\\s\\S]*?^        status: \\{ type: string, enum: \\[([^\\]]+)\\] \\}`, "m"))![1];
      expect(status.split(", ").sort()).toEqual(canonical);
    }
  });
});
