import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { BackupReminder } from "@/components/backup-reminder";
import { backupReminder, parseBackupView } from "@/lib/backup";
import fixture from "@/test-fixtures/backup-status.json";

const verifiedAt = "2025-01-01T13:00:00Z";
const dueAt = "2025-01-31T13:00:00Z";
const disconnected = {
  ...fixture,
  safe_to_eject: false,
  backup_age_seconds: 3600,
  next_due_at: dueAt,
  reminder_due: false,
  availability: {
    ...fixture.availability, state: "DISCONNECTED", message: "Connect the enrolled backup drive.", drive: undefined,
    prior_verified: { scope: "RECOVERABLE_ONLY", snapshot_id: "a".repeat(64), verified: true, full_recovery: false, captured_at: "2025-01-01T12:00:00Z", verified_at: verifiedAt, unavailable_dependencies: 2, logical_bytes: 1, data_added_packed_bytes: 1, repository_file_bytes: 1 },
  },
};

function memoryStorage() {
  const items = new Map<string, string>();
  return { getItem: (key: string) => items.get(key) ?? null, setItem: (key: string, value: string) => { items.set(key, value); } };
}

beforeEach(() => vi.stubGlobal("localStorage", memoryStorage()));
afterEach(() => vi.unstubAllGlobals());

it("stays quiet until a day before the backup is due", () => {
  const view = parseBackupView(disconnected);
  expect(backupReminder(view, new Date("2025-01-30T12:59:59Z"))).toBeNull();
  expect(backupReminder(view, new Date("2025-01-30T13:00:00Z"))).toMatchObject({ overdue: false, driveConnected: false, dismissKey: dueAt });
});

it("reminds every day while the backup is overdue", () => {
  const view = parseBackupView({ ...disconnected, reminder_due: true });
  expect(backupReminder(view, new Date("2025-02-02T08:00:00Z"))).toMatchObject({ overdue: true, dismissKey: `${dueAt}|2025-02-02` });
});

it("asks for the drive on the landing page and stays closed after dismissal", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json(disconnected)));
  const { unmount } = render(await BackupReminder({ now: new Date("2025-01-31T09:00:00Z") }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Connect the backup drive.");
  expect(screen.getByRole("link", { name: "Backup & Recovery" })).toHaveAttribute("href", "/admin/backup");
  await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  unmount();
  render(await BackupReminder({ now: new Date("2025-01-31T10:00:00Z") }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("shows nothing when backup status is unavailable", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 503 })));
  const { container } = render(await BackupReminder({}));
  expect(container).toBeEmptyDOMElement();
});
