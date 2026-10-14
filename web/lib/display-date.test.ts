import { describe, expect, it } from "vitest";
import { dayLabel, displayDay, validDay } from "@/lib/display-date";

describe("display dates", () => {
  it("uses configured civil-day boundaries including Lagos midnight and DST", () => {
    expect(displayDay(new Date("2026-10-13T23:30:00Z"), "Africa/Lagos")).toBe("2026-10-14");
    expect(displayDay(new Date("2026-10-13T22:30:00Z"), "Africa/Lagos")).toBe("2026-10-13");
    expect(displayDay(new Date("2026-03-08T07:30:00Z"), "America/New_York")).toBe("2026-03-08");
    expect(displayDay(new Date("2026-11-01T03:30:00Z"), "America/New_York")).toBe("2026-10-31");
    expect(displayDay(new Date("2026-10-13T12:30:00Z"), "Pacific/Kiritimati")).toBe("2026-10-14");
  });
  it("validates calendar dates and formats selected civil dates deterministically", () => {
    for (const value of ["", "bad", "2026-02-30", "2026-13-01", "2026-1-01"]) expect(validDay(value)).toBe(false);
    expect(validDay("2024-02-29")).toBe(true);
    expect(dayLabel("2026-10-13")).toBe("Tuesday, 13 October 2026");
    expect(dayLabel("")).toBe("Choose a valid date");
  });
});
