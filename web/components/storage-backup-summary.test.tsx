import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { StorageBackupSummary } from "@/components/storage-backup-summary";
import fixture from "@/test-fixtures/backup-status.json";

afterEach(() => vi.unstubAllGlobals());

it("shows the dated backup receipt when the enrolled drive is disconnected", async () => {
  const payload = {
    ...fixture,
    safe_to_eject: false,
    backup_age_seconds: 3600,
    next_due_at: "2025-01-31T13:00:00Z",
    reminder_due: false,
    availability: {
      ...fixture.availability,
      state: "DISCONNECTED",
      message: "Connect the enrolled backup drive.",
      drive: undefined,
      prior_verified: {
        scope: "RECOVERABLE_ONLY",
        snapshot_id: "a".repeat(64),
        verified: true,
        full_recovery: false,
        captured_at: "2025-01-01T12:00:00Z",
        verified_at: "2025-01-01T13:00:00Z",
        unavailable_dependencies: 2,
        logical_bytes: 42e9,
        data_added_packed_bytes: 3e9,
        repository_file_bytes: 41e9,
      },
    },
  };
  vi.stubGlobal("fetch", vi.fn(async () => Response.json(payload)));
  render(await StorageBackupSummary());
  expect(screen.getByText("Connect the enrolled backup drive.")).toBeVisible();
  expect(screen.getByText("41 GB")).toBeVisible();
  expect(screen.getByText("3 GB")).toBeVisible();
  expect(screen.getByText("Not measured")).toBeVisible();
  expect(screen.getByText(/Recoverable only.*2/)).toBeVisible();
});

it("shows backup status failure without implying a new recovery point", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 503 })));
  render(await StorageBackupSummary());
  expect(screen.getByRole("alert")).toHaveTextContent("503");
  expect(screen.queryByText(/Last verified/)).not.toBeInTheDocument();
});
