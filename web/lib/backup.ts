import { parseSyncRun, type SyncRun } from "@/lib/contracts";

export type BackupDrive = { volume_uuid: string; filesystem: string; filesystem_encrypted: boolean; free_bytes: number; capacity_bytes: number };
export type BackupAvailability = { state: string; message: string; drive?: BackupDrive; repository_unlocked: boolean; referenced_files: number; referenced_bytes: number; estimated_staging_bytes: number; impact: string };
export type BackupView = { availability: BackupAvailability; runs: SyncRun[]; last_verified: SyncRun | null; next_due_at: string | null; backup_age_seconds: number | null; reminder_due: boolean; safe_to_eject: boolean };

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid backup response");
  return value as Record<string, unknown>;
}
function text(value: unknown): string { if (typeof value !== "string") throw new Error("Invalid backup text"); return value; }
function flag(value: unknown): boolean { if (typeof value !== "boolean") throw new Error("Invalid backup flag"); return value; }
function count(value: unknown): number { if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw new Error("Invalid backup measurement"); return value; }
function backupRun(value: unknown): SyncRun {
  const run = parseSyncRun(value);
  if (run.sync_type !== "MANUAL_BACKUP") throw new Error("Invalid backup run type");
  return run;
}

function parseDrive(value: unknown): BackupDrive {
  const drive = object(value);
  const result = { volume_uuid: text(drive.volume_uuid), filesystem: text(drive.filesystem), filesystem_encrypted: flag(drive.filesystem_encrypted), free_bytes: count(drive.free_bytes), capacity_bytes: count(drive.capacity_bytes) };
  if (result.free_bytes > result.capacity_bytes) throw new Error("Invalid drive capacity");
  return result;
}

function parseAvailability(value: unknown): BackupAvailability {
  const item = object(value), state = text(item.state);
  if (!["READY", "DISABLED", "UNCONFIGURED", "DISCONNECTED", "WRONG_DRIVE", "READ_ONLY", "FILESYSTEM_UNKNOWN", "CREDENTIALS", "REPOSITORY_MISSING", "WRONG_REPOSITORY", "REPOSITORY_VERSION", "TOOL_VERSION", "INTERRUPTED", "VERIFICATION_FAILED", "LOW_SPACE", "MISSING_FILES", "SNAPSHOT_FAILED", "INCOMPLETE", "MIGRATION_PENDING"].includes(state)) throw new Error("Unknown backup state");
  const result: BackupAvailability = { state, message: text(item.message), repository_unlocked: flag(item.repository_unlocked), referenced_files: count(item.referenced_files), referenced_bytes: count(item.referenced_bytes), estimated_staging_bytes: count(item.estimated_staging_bytes), impact: text(item.impact) };
  if (item.drive !== undefined) result.drive = parseDrive(item.drive);
  return result;
}

function parseRuns(value: unknown): SyncRun[] {
  if (!Array.isArray(value)) throw new Error("Invalid backup history");
  const runs = value.map(backupRun);
  if (runs.length > 20 || new Set(runs.map((run) => run.run_id)).size !== runs.length) throw new Error("Invalid backup history identity");
  return runs;
}

function parseVerified(value: unknown): SyncRun | null {
  if (value === null) return null;
  const last = backupRun(value);
  if (last.status !== "SUCCEEDED" || last.summary.verified !== true || !validRecoveryTimes(last.summary)) throw new Error("Invalid verified recovery point");
  return last;
}

function validRecoveryTimes(summary: Record<string, unknown>): boolean {
  if (typeof summary.verified_at !== "string" || typeof summary.captured_at !== "string") return false;
  const verified = Date.parse(summary.verified_at), captured = Date.parse(summary.captured_at);
  return Number.isFinite(verified) && Number.isFinite(captured) && captured <= verified;
}

function parseDueDate(value: unknown): string | null {
  if (value === null) return null;
  const next = text(value);
  if (!Number.isFinite(Date.parse(next))) throw new Error("Invalid backup due date");
  return next;
}

function validateEject(view: BackupView): void {
  if (view.safe_to_eject && (view.availability.state !== "READY" || !view.availability.repository_unlocked || view.runs.some((run) => ["RUNNING", "QUEUED"].includes(run.status)))) throw new Error("Inconsistent safe-to-eject status");
}

export function parseBackupView(value: unknown): BackupView {
  const root = object(value);
  const result = { availability: parseAvailability(root.availability), runs: parseRuns(root.runs), last_verified: parseVerified(root.last_verified), next_due_at: parseDueDate(root.next_due_at), backup_age_seconds: root.backup_age_seconds === null ? null : count(root.backup_age_seconds), reminder_due: flag(root.reminder_due), safe_to_eject: flag(root.safe_to_eject) };
  validateEject(result);
  if ((result.last_verified === null) !== (result.backup_age_seconds === null) || (result.last_verified === null) !== (result.next_due_at === null)) throw new Error("Inconsistent recovery point age");
  return result;
}
