import { ApiError } from "@/lib/api";

export type Decision = { case_key: string; action: string; reason: string; candidate?: Record<string, string>; evidence_version?: string; request_id?: string; approved?: boolean };
export type Preview = { case_key: string; action: string; detail: RecordValue; candidate: Record<string, string>; reason: string; allowed: boolean; evidence_version: string; qualification: RecordValue };
export type RecordValue = Record<string, unknown>;
export type ResolutionPage = { items: RecordValue[]; page: number; page_size: number; total: number; counts: Record<string, number>; groups: RecordValue[]; scope?: string; blockers?: string[] };
export const resolutionViews = ["identity", "fixtures", "missing", "parity", "cutover", "history"] as const;
export type ResolutionView = (typeof resolutionViews)[number];
const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8080";

function record(value: unknown): RecordValue {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid resolution response");
  return value as RecordValue;
}
function records(value: unknown): RecordValue[] {
  if (!Array.isArray(value)) throw new Error("Invalid resolution list");
  return value.map(record);
}
export function text(value: unknown): string { return typeof value === "string" && value.length ? value : "—"; }
function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) throw new Error("Invalid resolution count");
  return value;
}
function digest(value: unknown): string {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value)) throw new Error("Invalid evidence version");
  return value;
}
function parseCases(value: unknown): RecordValue[] {
  const items = records(value);
  for (const item of items) {
    if (typeof item.case_key !== "string" || !item.case_key || typeof item.status !== "string" || !item.status) throw new Error("Missing case identity or status");
  }
  return items;
}
function parseGroups(value: unknown, total: number): RecordValue[] {
  const groups = records(value);
  if (groups.length > 100) throw new Error("Too many resolution groups");
  for (const group of groups) {
    if (typeof group.provider !== "string" || typeof group.kind !== "string" || typeof group.status !== "string" || typeof group.reason !== "string") throw new Error("Invalid resolution group");
    const count = integer(group.count);
    if (count < 1 || count > total) throw new Error("Invalid group count");
  }
  return groups;
}
function parseBlockers(value: unknown): string[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) throw new Error("Invalid blockers");
  return value as string[];
}
export function parseResolutionPage(value: unknown): ResolutionPage {
  const data = record(value), items = parseCases(data.items);
  const counts = Object.fromEntries(Object.entries(record(data.counts)).map(([key, count]) => [key, integer(count)]));
  const page = integer(data.page), size = integer(data.page_size), total = integer(data.total);
  if (Object.values(counts).reduce((sum, count) => sum + count, 0) !== total) throw new Error("Inconsistent resolution counts");
  if (!page || ![20, 50, 100].includes(size) || items.length > size) throw new Error("Invalid resolution pagination");
  if (data.scope !== undefined && typeof data.scope !== "string") throw new Error("Invalid verification scope");
  return { items, page, page_size: size, total, counts, groups: parseGroups(data.groups, total), scope: data.scope, blockers: parseBlockers(data.blockers) };
}
function parsePreview(value: unknown): Preview {
  const data = record(value);
  if (typeof data.allowed !== "boolean" || typeof data.case_key !== "string" || typeof data.action !== "string" || typeof data.reason !== "string") throw new Error("Invalid approval preview");
  const candidate = record(data.candidate);
  if (Object.values(candidate).some((value) => typeof value !== "string")) throw new Error("Invalid candidate");
  if (data.allowed !== (record(data.qualification).status === "QUALIFIED") || record(data.detail).case_key !== data.case_key) throw new Error("Preview proof mismatch");
  return { case_key: data.case_key, action: data.action, reason: data.reason, candidate: candidate as Record<string, string>, detail: record(data.detail), allowed: data.allowed, qualification: record(data.qualification), evidence_version: digest(data.evidence_version) };
}
function bindPreview(value: unknown, decision: Decision): Preview {
  const data = parsePreview(value);
  if (data.case_key !== decision.case_key || data.action !== decision.action || data.reason !== decision.reason || Object.keys(data.candidate).length !== Object.keys(decision.candidate ?? {}).length || Object.entries(data.candidate).some(([key, value]) => decision.candidate?.[key] !== value)) throw new Error("Preview inputs mismatch");
  return data;
}
function batchItems(value: unknown, decisions: Decision[]): RecordValue[] {
  const items = records(record(value).items);
  if (items.length !== decisions.length || new Set(items.map((item) => item.case_key)).size !== items.length || items.some((item) => !decisions.some((decision) => decision.case_key === item.case_key))) throw new Error("Batch case identities mismatch");
  return items;
}
function parseBatchPreview(value: unknown, decisions: Decision[]) {
  const items = batchItems(value, decisions), previews: Preview[] = [], errors: string[] = [];
  for (const item of items) {
    if (item.status === "PREVIEWED") previews.push(bindPreview(item.preview, decisions.find((decision) => decision.case_key === item.case_key)!));
    else if (item.status === "BLOCKED" && typeof item.error === "string") errors.push(`${item.case_key}: ${item.error}`);
    else throw new Error("Invalid batch preview result");
  }
  return { previews, errors };
}
function parseBatchResult(value: unknown, decisions: Decision[]) {
  const data = record(value), items = batchItems(value, decisions);
  if (integer(data.succeeded) !== items.filter((item) => item.status === "SUCCEEDED").length || integer(data.blocked) !== items.filter((item) => item.status === "BLOCKED").length || Number(data.succeeded) + Number(data.blocked) !== items.length) throw new Error("Invalid batch totals");
  for (const item of items) {
    if (item.status === "SUCCEEDED") parseDecisionEvent(item.event, decisions.find((decision) => decision.case_key === item.case_key)!);
    else if (typeof item.error !== "string") throw new Error("Invalid blocked result");
  }
  return { items };
}

function parseDecisionEvent(value: unknown, decision: Decision) {
  const data = record(value);
  if (data.request_id !== decision.request_id || data.case_key !== decision.case_key || data.action !== decision.action) throw new Error("Decision result mismatch; recheck history");
  record(data.detail);
  return data;
}

async function request<T>(path: string, parse: (value: unknown) => T, signal?: AbortSignal, body?: unknown, token?: string): Promise<T> {
  const response = await fetch(`${base}/v1/admin/resolution/${path}`, { cache: "no-store", signal, method: body === undefined ? undefined : "POST", headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }), ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) {
    let message = `Resolution request failed (${response.status})`;
    try { const error = record(await response.json()); if (typeof error.error === "string") message = error.error; } catch { /* Preserve the HTTP status when no JSON error is available. */ }
    throw new ApiError(message, response.status);
  }
  return parse(await response.json());
}
export const resolutionApi = {
  page: (view: ResolutionView, query: URLSearchParams, signal?: AbortSignal) => request(`${view}?${query}`, parseResolutionPage, signal),
  detail: (key: string, signal?: AbortSignal) => request(`detail?case_key=${encodeURIComponent(key)}`, (value) => { const data = record(value); if (data.case_key !== key) throw new Error("Case identity mismatch"); digest(data.evidence_version); return data; }, signal),
  preview: (decision: Decision, signal?: AbortSignal) => request("preview", (value) => bindPreview(value, decision), signal, decision),
  apply: (decision: Decision, token: string) => request("apply", (value) => parseDecisionEvent(value, decision), undefined, decision, token),
  batchPreview: (decisions: Decision[], signal?: AbortSignal) => request("batch-preview", (value) => parseBatchPreview(value, decisions), signal, { requests: decisions }),
  batchApply: (decisions: Decision[], token: string) => request("batch-apply", (value) => parseBatchResult(value, decisions), undefined, { requests: decisions }, token),
};
