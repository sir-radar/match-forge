import { parseSyncRun, type SyncRun } from "@/lib/contracts";

export type BackupScope = "FULL_RECOVERY" | "GOVERNED_SCOPE" | "RECOVERABLE_ONLY";
const SCOPE_LABELS: Record<BackupScope, string> = {
  FULL_RECOVERY: "Full recovery",
  GOVERNED_SCOPE: "Governed scope (approved exclusions)",
  RECOVERABLE_ONLY: "Recoverable only",
};
export const backupScopeLabel = (scope: unknown) =>
  typeof scope === "string" && scope in SCOPE_LABELS ? SCOPE_LABELS[scope as BackupScope] : "Scope unrecorded";
export const restoreLabel = (scope: unknown, fullRecovery: unknown) =>
  fullRecovery === true ? "Full recovery verified" : scope === "GOVERNED_SCOPE" ? "Every original verified; approved exclusions absent" : "Recoverable data verified";

type BackupPoint = { scope: BackupScope; snapshot_id: string; captured_at: string; verified_at: string; full_recovery: boolean; unavailable_dependencies: number; logical_bytes: number; data_added_packed_bytes: number; repository_file_bytes: number; volume_free_space_change_bytes?: number };
type BackupDrive = { volume_uuid: string; filesystem: string; filesystem_encrypted: boolean; free_bytes: number; capacity_bytes: number };
export type BackupAvailability = { scope?: BackupScope; known_unavailable_dependencies: number | null; prior_verified: BackupPoint | null; unavailable_sha256: string | null; governed_sha256: string | null; excluded_dependencies: number | null; state: string; message: string; drive?: BackupDrive; repository_unlocked: boolean; referenced_files: number; referenced_bytes: number; estimated_staging_bytes: number; impact: string };
export type BackupView = { availability: BackupAvailability; runs: SyncRun[]; last_verified: SyncRun | null; last_full_recovery: SyncRun | null; next_due_at: string | null; backup_age_seconds: number | null; reminder_due: boolean; safe_to_eject: boolean };

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

function parseScope(value: unknown): BackupScope | undefined {
  if (value === undefined || value === "FULL_RECOVERY" || value === "GOVERNED_SCOPE" || value === "RECOVERABLE_ONLY") return value;
  throw new Error("Unknown backup scope");
}

function parsePrior(value: unknown): BackupPoint | null {
  if (value === null) return null;
  const point = object(value);
  const scope = parseScope(point.scope);
  if (!scope) throw new Error("Missing receipt scope");
  const snapshot = text(point.snapshot_id);
  if (!/^[0-9a-f]{64}$/.test(snapshot) || !validRecoveryTimes(point) || point.verified !== true ||
      point.full_recovery !== (scope === "FULL_RECOVERY")) throw new Error("Invalid prior recovery receipt");
  return {
    scope, snapshot_id: snapshot, captured_at: text(point.captured_at), verified_at: text(point.verified_at),
    full_recovery: flag(point.full_recovery), unavailable_dependencies: count(point.unavailable_dependencies),
    logical_bytes: count(point.logical_bytes), data_added_packed_bytes: count(point.data_added_packed_bytes),
    repository_file_bytes: count(point.repository_file_bytes),
    volume_free_space_change_bytes: typeof point.volume_free_space_change_bytes === "number" ? point.volume_free_space_change_bytes : undefined,
  };
}

const SHA256 = /^[0-9a-f]{64}$/;
function optionalDigest(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const digest = text(value);
  if (!SHA256.test(digest)) throw new Error("Invalid recovery binding");
  return digest;
}

function parseCoverage(item: Record<string, unknown>, state: string): Pick<BackupAvailability, "scope" | "known_unavailable_dependencies" | "unavailable_sha256" | "governed_sha256" | "excluded_dependencies"> {
  const scope = parseScope(item.scope);
  const unavailable = item.known_unavailable_dependencies === null ? null : count(item.known_unavailable_dependencies);
  const digest = optionalDigest(item.unavailable_sha256);
  const governed = optionalDigest(item.governed_sha256);
  const excluded = item.excluded_dependencies === null || item.excluded_dependencies === undefined ? null : count(item.excluded_dependencies);
  const scoped = scope === "RECOVERABLE_ONLY" || scope === "GOVERNED_SCOPE";
  if ((digest === null) !== (unavailable === null) || (scoped && state === "READY" && digest === null)) throw new Error("Missing recovery inventory");
  // A governed scope has no unexplained gap and binds at least one approved exclusion.
  if (scope === "GOVERNED_SCOPE" && state === "READY" && (governed === null || unavailable !== 0 || !excluded)) throw new Error("Missing governed recovery approvals");
  if (scope !== "GOVERNED_SCOPE" && governed !== null) throw new Error("Unexpected governed recovery binding");
  return { scope, known_unavailable_dependencies: unavailable, unavailable_sha256: digest, governed_sha256: governed, excluded_dependencies: excluded };
}

function parseAvailability(value: unknown): BackupAvailability {
  const item = object(value), state = text(item.state);
  if (!["READY", "DISABLED", "UNCONFIGURED", "DISCONNECTED", "WRONG_DRIVE", "READ_ONLY", "FILESYSTEM_UNKNOWN", "CREDENTIALS", "REPOSITORY_MISSING", "WRONG_REPOSITORY", "REPOSITORY_VERSION", "TOOL_VERSION", "INTERRUPTED", "VERIFICATION_FAILED", "LOW_SPACE", "MISSING_FILES", "SNAPSHOT_FAILED", "INCOMPLETE", "IN_PROGRESS", "MIGRATION_PENDING"].includes(state)) throw new Error("Unknown backup state");
  const coverage = parseCoverage(item, state);
  const result: BackupAvailability = { ...coverage, prior_verified: parsePrior(item.prior_verified), state, message: text(item.message), repository_unlocked: flag(item.repository_unlocked), referenced_files: count(item.referenced_files), referenced_bytes: count(item.referenced_bytes), estimated_staging_bytes: count(item.estimated_staging_bytes), impact: text(item.impact) };
  if (item.drive !== undefined) result.drive = parseDrive(item.drive);
  return result;
}

function parseRuns(value: unknown): SyncRun[] {
  if (!Array.isArray(value)) throw new Error("Invalid backup history");
  const runs = value.map(backupRun);
  if (runs.length > 20 || new Set(runs.map((run) => run.run_id)).size !== runs.length) throw new Error("Invalid backup history identity");
  return runs;
}

function parseVerified(value: unknown, scope: BackupScope | undefined): SyncRun | null {
  if (value === null) return null;
  const last = backupRun(value);
  if (!scope || last.status !== "SUCCEEDED" || last.summary.verified !== true ||
      last.summary.scope !== scope || last.parameters.scope !== scope ||
      last.summary.full_recovery !== (scope === "FULL_RECOVERY") || !validRecoveryTimes(last.summary)) {
    throw new Error("Invalid verified recovery point");
  }
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
  const availability = parseAvailability(root.availability);
  const result = { availability, runs: parseRuns(root.runs), last_verified: parseVerified(root.last_verified, availability.scope), last_full_recovery: parseVerified(root.last_full_recovery, "FULL_RECOVERY"), next_due_at: parseDueDate(root.next_due_at), backup_age_seconds: root.backup_age_seconds === null ? null : count(root.backup_age_seconds), reminder_due: flag(root.reminder_due), safe_to_eject: flag(root.safe_to_eject) };
  validateEject(result);
  const hasPoint = !!result.last_verified || availability.prior_verified?.scope === availability.scope && !!availability.prior_verified;
  if (hasPoint !== (result.backup_age_seconds !== null) || hasPoint !== (result.next_due_at !== null)) throw new Error("Inconsistent recovery point age");
  return result;
}
