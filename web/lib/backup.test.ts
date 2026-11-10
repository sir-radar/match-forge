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
