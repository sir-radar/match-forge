import { ApiError } from "@/lib/api";

const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8080";

export type Classification = "PROTECTED" | "REVIEW_REQUIRED" | "ELIGIBLE";
export type StorageActionName = "DELETE" | "QUARANTINE" | "RESTORE" | "PURGE";
export type ManagedResource = {
  resource_id: string; backend: "postgres" | "filesystem" | "git"; kind: string; name: string; location: string;
  identity_key: string; purpose: string; logical_bytes: number | null; allocated_bytes: number | null;
  measurement_complete: boolean; observed_at: string; classification: Classification; role: string;
  reasons: string[]; remediation: string[]; actions: StorageActionName[]; active_consumers: number; recovery: string;
  evidence: { finding: string; unique_identity_rows: number | null; observed_at: string; current: boolean; stale_reason?: string; tables: Record<string, { present: boolean; rows?: number; absent_from_authoritative?: number; absent_samples?: string[]; schema?: string }> } | null;
  disposition: { disposition: string; rationale: string; recorded_at: string } | null;
  quarantine: { operation_id: string; original_location: string; quarantine_location: string; quarantined_at: string; retain_until: string } | null;
  details: Record<string, unknown>; evidence_sha256: string;
};
export type StorageSummary = {
  host_total_bytes: number | null; host_free_bytes: number | null; postgres_bytes: number; authoritative_bytes: number;
  other_database_bytes: number; database_count: number; worktree_bytes: number; managed_file_bytes: number;
  quarantined_bytes: number; bytes_by_classification: Record<string, number>; count_by_classification: Record<string, number>;
  estimated_reclaimable_bytes: number; verified_reclaimed_bytes: number; note: string;
};
export type StorageInventory = {
  observed_at: string; authority: { system_identifier: string; oid: number; database: string; verified: boolean; problem?: string };
  resources: ManagedResource[]; summary: StorageSummary; warnings: string[];
  policy: { configured: boolean; managed_roots: { path: string; class: string; description: string }[]; protected_paths: string[]; automatic_cleanup: { action: string; root: string; min_age_seconds: number; max_per_run: number }[]; quarantine_days: number };
};
export type CompareStatus = { resource_id: string; name: string; state: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED"; error?: string };
export type PlanItem = { resource_id: string; name: string; backend: string; location: string; classification: Classification; expected_bytes: number | null; reasons: string[]; remediation: string[]; overlaps?: string };
export type StoragePlan = {
  action: StorageActionName; items: PlanItem[]; blocked: PlanItem[]; plan_sha256: string; expected_unique_bytes: number;
  typed_confirmation: string; irreversible: boolean; consequences: string[]; authoritative_verified: boolean;
};
export type StorageOperation = {
  operation_id: string; batch_id: string; action: StorageActionName; resource_id: string; backend: string; location: string;
  state: "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "BLOCKED" | "CANCELLED"; approved_by: string;
  expected_bytes: number | null; reclaimed_bytes: number | null; measurement: Record<string, unknown>;
  error: string | null; created_at: string; finished_at: string | null;
};

const hex64 = /^[0-9a-f]{64}$/;
const classes: Classification[] = ["PROTECTED", "REVIEW_REQUIRED", "ELIGIBLE"];
const actionNames: StorageActionName[] = ["DELETE", "QUARANTINE", "RESTORE", "PURGE"];

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid storage management response");
  return value as Record<string, unknown>;
}
function list(value: unknown): unknown[] { if (!Array.isArray(value)) throw new Error("Invalid storage list"); return value; }
function text(value: unknown): string { if (typeof value !== "string") throw new Error("Invalid storage text"); return value; }
function bytes(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw new Error("Invalid storage bytes");
  return value;
}

export function parseResource(value: unknown): ManagedResource {
  const r = object(value);
  if (!hex64.test(text(r.resource_id))) throw new Error("Invalid resource identity");
  if (!classes.includes(r.classification as Classification)) throw new Error("Invalid classification");
  const actions = list(r.actions).map(text) as StorageActionName[];
  if (actions.some((a) => !actionNames.includes(a))) throw new Error("Invalid storage action");
  // Safety invariant mirrored from the server: only eligible or quarantined resources expose actions,
  // and a protected resource never exposes a destructive one.
  if (r.classification === "PROTECTED" && actions.some((a) => a !== "RESTORE")) throw new Error("Protected resource exposed a destructive action");
  if (r.classification === "REVIEW_REQUIRED" && actions.length && r.quarantine == null) throw new Error("Unreviewed resource exposed an action");
  return {
    ...(r as unknown as ManagedResource), actions,
    logical_bytes: bytes(r.logical_bytes), allocated_bytes: bytes(r.allocated_bytes),
    reasons: list(r.reasons).map(text), remediation: list(r.remediation).map(text),
  };
}

export function parseInventory(value: unknown): { inventory: StorageInventory; comparisons: CompareStatus[] } {
  const r = object(value), inventory = object(r.inventory);
  return {
    inventory: { ...(inventory as unknown as StorageInventory), resources: list(inventory.resources).map(parseResource), warnings: list(inventory.warnings).map(text) },
    comparisons: list(r.comparisons ?? []) as CompareStatus[],
  };
}

async function request<T>(path: string, parse: (value: unknown) => T, init: { method?: string; body?: unknown; token?: string; signal?: AbortSignal } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  if (init.token) headers.Authorization = `Bearer ${init.token}`;
  const response = await fetch(`${base}/v1/admin/storage/${path}`, {
    cache: "no-store", method: init.method ?? (init.body === undefined ? "GET" : "POST"), headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    signal: init.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(120_000)]) : AbortSignal.timeout(120_000),
  });
  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof (payload as { error?: unknown }).error === "string" ? (payload as { error: string }).error : `Storage request failed (HTTP ${response.status}).`;
    throw new ApiError(message, response.status);
  }
  return parse(payload);
}

export type LifecycleState = "ACTIVE" | "WAITING" | "ELIGIBLE" | "BLOCKED" | "DELETING" | "DELETED" | "ABSENT";
export type LifecycleRecord = {
  identity_key: string; resource_class: "TEST_DATABASE" | "WORKTREE" | "DISPOSABLE_PATH"; backend: string; location: string; owner_kind: string;
  identity: Record<string, unknown>; owner_ref: Record<string, unknown>; created_at: string; last_activity_at: string;
  completed_at: string | null; completion: string | null; state: LifecycleState; eligible_at: string | null; blockers: string[];
  checked_at: string | null; operation_id: string | null; reclaimed_bytes: number | null;
};
export type LifecycleStatus = {
  observed_at: string; deployed: boolean; reclaimed_bytes: number;
  policy: { inactivity_seconds: number; check_interval_seconds: number; max_per_run: number; test_databases: boolean;
    worktrees?: { target_ref: string; roots: string[] };
    paths?: { path: string; kind: "BUILD_OUTPUT" | "DEPENDENCY_CACHE" | "TEMPORARY"; consumers: string[]; min_idle_seconds?: number }[]; approved_by: string; approval_record: string } | null;
  resources: LifecycleRecord[]; events: { identity_key: string; event: string; detail: Record<string, unknown>; recorded_at: string }[];
  unregistered_test_databases: { name: string; oid: number; bytes: number }[];
};
export type MaintenanceFinding = { task: string; severity: "INFO" | "WARNING" | "CRITICAL"; message: string; count?: number; bytes?: number; items?: string[] };
export type MaintenanceReport = {
  run_id: string; cadence: "DAILY" | "WEEKLY" | "MONTHLY"; slot: string; state: "RUNNING" | "SUCCEEDED" | "FAILED";
  findings: MaintenanceFinding[]; alerts: number; error: string | null; started_at: string; finished_at: string | null;
};
export type MaintenanceStatus = {
  policy: { growth_warning_bytes_per_day: number; max_non_operating_databases: number; stale_after_days: number } | null;
  reports: MaintenanceReport[];
};

const lifecycleStates: LifecycleState[] = ["ACTIVE", "WAITING", "ELIGIBLE", "BLOCKED", "DELETING", "DELETED", "ABSENT"];

export function parseLifecycle(value: unknown): LifecycleStatus {
  const r = object(value);
  const resources = list(r.resources).map((item) => {
    const record = object(item);
    if (!lifecycleStates.includes(record.state as LifecycleState)) throw new Error("Invalid lifecycle state");
    if (!["TEST_DATABASE", "WORKTREE", "DISPOSABLE_PATH"].includes(record.resource_class as string)) throw new Error("Invalid lifecycle class");
    return { ...(record as unknown as LifecycleRecord), blockers: list(record.blockers ?? []).map(text), reclaimed_bytes: bytes(record.reclaimed_bytes) };
  });
  return { ...(r as unknown as LifecycleStatus), resources, events: list(r.events) as LifecycleStatus["events"],
    unregistered_test_databases: list(r.unregistered_test_databases) as LifecycleStatus["unregistered_test_databases"] };
}

export function parseMaintenance(value: unknown): MaintenanceStatus {
  const r = object(value);
  const reports = list(r.reports).map((item) => {
    const report = object(item);
    const findings = list(report.findings).map((f) => {
      const finding = object(f);
      if (!["INFO", "WARNING", "CRITICAL"].includes(finding.severity as string)) throw new Error("Invalid maintenance severity");
      return finding as unknown as MaintenanceFinding;
    });
    return { ...(report as unknown as MaintenanceReport), findings };
  });
  return { policy: (r.policy ?? null) as MaintenanceStatus["policy"], reports };
}

export const storageManagement = {
  lifecycle: () => request("lifecycle", parseLifecycle),
  maintenance: () => request("maintenance", parseMaintenance),
  inventory: (refresh = false, signal?: AbortSignal) => request(`resources${refresh ? "?refresh=1" : ""}`, parseInventory, { signal }),
  preview: (action: StorageActionName, ids: string[]) => request("actions/preview", (v) => object(v) as unknown as StoragePlan, { body: { action, resource_ids: ids } }),
  execute: (plan: StoragePlan, confirmation: string, token: string) => request("actions", (v) => object(v) as { batch_id: string; operations: number }, {
    body: { action: plan.action, resource_ids: plan.items.map((i) => i.resource_id), plan_sha256: plan.plan_sha256, confirmation, confirmed: true }, token,
  }),
  operations: () => request("operations", (v) => list(object(v).operations) as StorageOperation[]),
  cancel: (batch: string) => request(`operations/${batch}/cancel`, object, { body: {} }),
  compare: (ids: string[]) => request("compare", object, { body: { resource_ids: ids } }),
  dispose: (resource: ManagedResource, disposition: "UNIQUE_DATA_NOT_REQUIRED" | "PRESERVE", rationale: string, token: string) =>
    request("dispositions", object, { body: { resource_id: resource.resource_id, evidence_sha256: resource.evidence_sha256, disposition, rationale }, token }),
  protect: (resource: ManagedResource, reason: string, token: string) => request("protections", object, { body: { resource_id: resource.resource_id, reason }, token }),
};

export const classificationLabel: Record<Classification, string> = {
  PROTECTED: "Protected", REVIEW_REQUIRED: "Review required", ELIGIBLE: "Eligible",
};
export const recoveryLabel: Record<string, string> = {
  FULLY_RECOVERABLE: "Fully recoverable", RECOVERABLE_WITH_DECLARED_GAPS: "Recoverable with declared gaps",
  INDEPENDENTLY_DISPOSABLE: "Independently disposable", RECOVERY_VERIFICATION_PENDING: "Recovery verification pending",
  PROTECTED_OR_UNRECOVERABLE: "Protected or unrecoverable",
};
