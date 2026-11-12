import { ApiError } from "@/lib/api";
import { DISPLAY_TIME_ZONE } from "@/lib/display-date";

type ArchiveSizes = { packed_bytes: number; unique_bytes: number; verified_at: string };
type StorageAction = { resource_id: string; action: "PRESERVE" | "QUARANTINE_REVIEW_REQUIRED"; expected_physical_savings: number | null; rollback: string };
export type StorageResource = { resource_id: string; backend: "filesystem" | "postgres" | "git"; location: string; kind: string; subsystem: string; owner: string; logical_bytes: number; allocated_bytes: number | null; protected: boolean; complete: boolean; state: string; blockers: string[]; archive?: ArchiveSizes };
export type StorageReview = { observed_at: string; dry_run: true; reclaimed_bytes: 0; capacity: { total_bytes: number; free_bytes: number }; resources: StorageResource[]; alerts: string[]; actions: StorageAction[]; policy_sha256: string };
export type StorageView = { state: "READY" | "EMPTY" | "MIGRATION_PENDING"; message: string; destructive_cleanup_enabled: false; latest: StorageReview | null; work_id: string | null; manifest_sha256: string | null; history: StorageReview[]; approvals: Record<string, unknown>[] };

function object(value: unknown): Record<string, unknown> { if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid storage response"); return value as Record<string, unknown>; }
function text(value: unknown): string { if (typeof value !== "string") throw new Error("Invalid storage text"); return value; }
function count(value: unknown): number { if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw new Error("Invalid storage bytes"); return value; }
function flag(value: unknown): boolean { if (typeof value !== "boolean") throw new Error("Invalid storage flag"); return value; }
function strings(value: unknown): string[] { if (!Array.isArray(value)) throw new Error("Invalid storage messages"); return value.map(text); }
function hash(value: unknown): string { const result = text(value); if (!/^[0-9a-f]{64}$/.test(result)) throw new Error("Invalid storage checksum"); return result; }
function date(value: unknown): string { const result = text(value); if (!Number.isFinite(Date.parse(result))) throw new Error("Invalid storage date"); return result; }
function archiveSizes(value: unknown, logical: number): ArchiveSizes {
  const details = object(value);
  const packed = count(details.packed_bytes), unique = count(details.unique_bytes);
  if (packed >= unique || unique > logical) throw new Error("Invalid archive sizes");
  return { packed_bytes: packed, unique_bytes: unique, verified_at: date(details.verified_at) };
}
function storageAction(value: unknown): StorageAction {
  const action = object(value);
  if (action.action !== "PRESERVE" && action.action !== "QUARANTINE_REVIEW_REQUIRED") throw new Error("Invalid storage action");
  return {
    resource_id: hash(action.resource_id), action: action.action,
    expected_physical_savings: action.expected_physical_savings === null ? null : count(action.expected_physical_savings),
    rollback: text(action.rollback),
  };
}
function resource(value: unknown): StorageResource {
  const r = object(value), backend = text(r.backend);
  if (!["filesystem", "postgres", "git"].includes(backend)) throw new Error("Invalid storage backend");
  if (!["PROTECTED", "ACTIVE", "ELIGIBLE", "VERIFIED", "QUARANTINED", "DELETED"].includes(text(r.state))) throw new Error("Invalid storage lifecycle state");
  const kind = text(r.kind), logical = count(r.logical_bytes);
  return { resource_id: hash(r.resource_id), backend: backend as StorageResource["backend"], location: text(r.location), kind, subsystem: text(r.subsystem), owner: text(r.owner), logical_bytes: logical, allocated_bytes: r.allocated_bytes === null ? null : count(r.allocated_bytes), protected: flag(r.protected), complete: flag(r.complete), state: text(r.state), blockers: strings(r.blockers), archive: kind === "archive" ? archiveSizes(r.details, logical) : undefined };
}
function reviewActions(value: unknown): StorageAction[] {
  if (value == null) return [];
  if (!Array.isArray(value)) throw new Error("Invalid storage actions");
  return value.map(storageAction);
}
function review(value: unknown): StorageReview {
  const r = object(value), capacity = object(r.capacity);
  if (r.dry_run !== true || r.reclaimed_bytes !== 0 || !Array.isArray(r.resources)) throw new Error("Invalid lifecycle safety state");
  const total = count(capacity.total_bytes), free = count(capacity.free_bytes);
  if (free > total) throw new Error("Invalid storage capacity");
  return { observed_at: date(r.observed_at), dry_run: true, reclaimed_bytes: 0, capacity: { total_bytes: total, free_bytes: free }, resources: r.resources.map(resource), alerts: strings(r.alerts), actions: reviewActions(r.actions), policy_sha256: hash(r.policy_sha256) };
}
export function parseStorageView(value: unknown): StorageView {
  const r = object(value), state = text(r.state);
  if (!["READY", "EMPTY", "MIGRATION_PENDING"].includes(state) || r.destructive_cleanup_enabled !== false || !Array.isArray(r.history) || !Array.isArray(r.approvals)) throw new Error("Invalid storage lifecycle response");
  const latest = r.latest === null ? null : review(r.latest);
  if (latest && (r.work_id === null || r.manifest_sha256 === null)) throw new Error("Missing storage review identity");
  return { state: state as StorageView["state"], message: text(r.message), destructive_cleanup_enabled: false, latest, work_id: r.work_id === null ? null : text(r.work_id), manifest_sha256: r.manifest_sha256 === null ? null : hash(r.manifest_sha256), history: r.history.map(review), approvals: r.approvals.map(object) };
}

export async function storageStatus(signal?: AbortSignal, origin?: string): Promise<StorageView> {
  const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8080"}/v1/admin/storage`, { signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15_000)]) : AbortSignal.timeout(15_000), headers: origin ? { Origin: origin } : {}, cache: "no-store" });
  if (!response.ok) throw new ApiError(`Storage status unavailable (HTTP ${response.status}). Check Admin access and retry.`, response.status);
  return parseStorageView(await response.json());
}
export async function startStorageReview(signal: AbortSignal): Promise<void> {
  const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8080"}/v1/admin/storage/reviews`, { method: "POST", signal: AbortSignal.any([signal, AbortSignal.timeout(15_000)]), headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dry_run: true }) });
  if (!response.ok) throw new ApiError(response.status === 409 ? "A review is blocked or already active. Refresh status before retrying." : `Storage review could not be submitted (HTTP ${response.status}).`, response.status);
}

export function formatStorageBytes(value?: number | null): string {
  if (value == null) return "Not measured";
  const units = value >= 1_000_000_000 ? ["GB", 1e9] as const
    : value >= 1_000_000 ? ["MB", 1e6] as const : ["bytes", 1] as const;
  return `${(value / units[1]).toLocaleString("en-GB", { maximumFractionDigits: 2 })} ${units[0]}`;
}
export function formatStorageTime(value: string): string {
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: DISPLAY_TIME_ZONE }).format(new Date(value));
}
