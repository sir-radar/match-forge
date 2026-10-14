export const DISPLAY_TIME_ZONE = process.env.NEXT_PUBLIC_TIME_ZONE ?? "Africa/Lagos";

export function displayDay(instant = new Date(), timeZone = DISPLAY_TIME_ZONE): string {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone, calendar: "iso8601", numberingSystem: "latn", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(instant);
  const part = (type: string) => parts.find((item) => item.type === type)!.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function validDay(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

// A selected day is a civil date in the display timezone, not a UTC instant.
// Explicit names/punctuation keep server and browser hydration identical.
export function dayLabel(value: string): string {
  if (!validDay(value)) return "Choose a valid date";
  const date = new Date(`${value}T00:00:00Z`);
  const weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  return `${weekdays[date.getUTCDay()]}, ${value.slice(8)} ${months[date.getUTCMonth()]} ${value.slice(0, 4)}`;
}
