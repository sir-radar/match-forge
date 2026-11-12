import { describe, expect, it } from "vitest";
import fixture from "@/test-fixtures/backup-status.json";
import { parseBackupView } from "@/lib/backup";

describe("backup contract", () => {
  it("accepts the shared Go/schema fixture", () => { expect(parseBackupView(fixture).availability.state).toBe("READY"); });
  it.each([NaN, -1, "100", Infinity])("rejects invalid measurement %s", (measurement) => {
    expect(() => parseBackupView({ ...fixture, backup_age_seconds: measurement })).toThrow();
  });
  it("rejects malformed, unknown, and unverified success responses", () => {
    expect(() => parseBackupView({})).toThrow();
    expect(() => parseBackupView({ ...fixture, availability: { ...fixture.availability, state: "NEW_STATE" } })).toThrow();
    expect(() => parseBackupView({ ...fixture, next_due_at: "not-a-date" })).toThrow();
    expect(() => parseBackupView({ ...fixture, last_verified: {} })).toThrow();
    expect(() => parseBackupView({ ...fixture, availability: { ...fixture.availability, state: "DISCONNECTED" } })).toThrow("safe-to-eject");
  });
});

describe("governed recovery scope", () => {
  const empty = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945";
  const governed = (changes: Record<string, unknown> = {}) => ({
    ...fixture,
    availability: {
      ...fixture.availability, scope: "GOVERNED_SCOPE", known_unavailable_dependencies: 0,
      unavailable_sha256: empty, governed_sha256: "d".repeat(64), excluded_dependencies: 159, ...changes,
    },
  });
  it("accepts a governed scope with zero gaps and bound approvals, labelled apart from full recovery", async () => {
    const { backupScopeLabel, restoreLabel } = await import("@/lib/backup");
    const view = parseBackupView(governed());
    expect(view.availability.excluded_dependencies).toBe(159);
    expect(backupScopeLabel("GOVERNED_SCOPE")).toBe("Governed scope (approved exclusions)");
    expect(restoreLabel("GOVERNED_SCOPE", false)).not.toMatch(/full recovery/i);
    expect(restoreLabel("FULL_RECOVERY", true)).toBe("Full recovery verified");
  });
  it.each([
    ["missing approval binding", { governed_sha256: null }],
    ["unexplained gaps", { known_unavailable_dependencies: 2 }],
    ["no exclusions", { excluded_dependencies: 0 }],
    ["malformed binding", { governed_sha256: "nope" }],
  ])("rejects a governed scope with %s", (_, changes) => {
    expect(() => parseBackupView(governed(changes))).toThrow();
  });
  it("rejects a governed binding on other policies", () => {
    expect(() => parseBackupView({ ...fixture, availability: { ...fixture.availability, governed_sha256: "d".repeat(64) } })).toThrow("Unexpected governed");
  });
});
