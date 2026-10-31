"use client";

import { useState } from "react";
import { useResolutionOperation } from "@/components/use-resolution-operation";
import { resolutionApi, text, type Decision, type Preview, type RecordValue } from "@/lib/resolution";

type Prepared = Preview & { request_id: string };
const message = (error: unknown) => error instanceof Error ? error.message : "Batch unavailable";
export function ResolutionBatch({ keys, onApplied }: { keys: string[]; onApplied: () => void }) {
  const [action, setAction] = useState("REVALIDATE"), [reason, setReason] = useState("");
  const [targets, setTargets] = useState<Record<string, string>>({}), [candidates, setCandidates] = useState<Record<string, RecordValue[]>>({});
  const [prepared, setPrepared] = useState<Prepared[]>([]), [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false), [approved, setApproved] = useState(false), [token, setToken] = useState("");
  const [result, setResult] = useState<RecordValue[]>();
  const operation = useResolutionOperation();
  const invalidate = () => { operation.cancelRead(); setPrepared([]); setApproved(false); setErrors([]); setResult(undefined); };
  const actions = batchActions(keys);
  const preview = async () => {
    if (!operation.begin()) return;
    setBusy(true); invalidate();
    const abort = operation.newRead();
    try {
      const requests = keys.map((case_key): Decision => ({ case_key, action, reason, candidate: action === "REJECT" && targets[case_key] ? { target_mapping_id: targets[case_key] } : {} }));
      const response = await resolutionApi.batchPreview(requests, abort.signal);
      if (operation.isMounted() && !abort.signal.aborted) {
        setPrepared(response.previews.map((item) => ({ ...item, request_id: crypto.randomUUID() })));
        setErrors(response.errors);
        setCandidates(Object.fromEntries(response.previews.map((item) => [item.case_key, Array.isArray(item.detail.candidates) ? item.detail.candidates as RecordValue[] : []])));
      }
    } catch (cause) { if (operation.isMounted() && !abort.signal.aborted) setErrors([message(cause)]); }
    finally { operation.finish(); if (operation.isMounted()) setBusy(false); }
  };
  const qualified = prepared.filter((item) => item.allowed);
  const apply = async () => {
    if (!approved || !token || !qualified.length || !operation.begin()) return;
    setBusy(true); setErrors([]);
    const requests: Decision[] = qualified.map((item) => ({ case_key: item.case_key, action: item.action, reason: item.reason, candidate: item.candidate, evidence_version: item.evidence_version, request_id: item.request_id, approved: true }));
    try { const response = await resolutionApi.batchApply(requests, token); if (operation.isMounted()) { setResult(response.items); setToken(""); setApproved(false); onApplied(); } }
    catch (cause) { if (operation.isMounted()) { setErrors([message(cause)]); setApproved(false); } }
    finally { operation.finish(); if (operation.isMounted()) setBusy(false); }
  };
  return <section aria-label="Batch review" className="resolution-review">
    <h2>Review {keys.length} selected cases (maximum 20)</h2><p>Selection spans pages. Each case requires independent proof; overlapping effects require separate reviews.</p>
    <form className="resolution-form" onSubmit={(event) => { event.preventDefault(); void preview(); }}>
      <label>Batch action<select disabled={busy} value={action} onChange={(event) => { invalidate(); setAction(event.target.value); setTargets({}); }}>{actions.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Batch reason<textarea required maxLength={2000} disabled={busy} value={reason} onChange={(event) => { invalidate(); setReason(event.target.value); }} /></label>
      <ul>{keys.map((key) => <li key={key}>{key}{action === "REJECT" && <label>Reject candidate for {key}<select disabled={busy} value={targets[key] ?? ""} onChange={(event) => { invalidate(); setTargets((old) => ({ ...old, [key]: event.target.value })); }}><option value="">Gather evidence, then choose a candidate</option>{(candidates[key] ?? []).map((item) => <option key={text(item.mapping_id)} value={text(item.mapping_id)}>{text(item.name)} · {text(item.mapping_id)}</option>)}</select></label>}</li>)}</ul>
      <button disabled={busy || !reason.trim()} type="submit">Gather evidence and preview batch</button>
    </form>
    {!!errors.length && <div role="alert">{errors.map((error) => <p key={error}>{error}</p>)}</div>}
    {!!prepared.length && <section aria-label="Batch approval previews"><h3>{qualified.length} qualified; {prepared.length - qualified.length} blocked</h3>{prepared.map((item) => <details key={item.case_key}><summary>{item.case_key}: {item.allowed ? "QUALIFIED" : "BLOCKED"} — {text(item.qualification.reason)}</summary><pre className="resolution-json">{JSON.stringify(item, null, 2)}</pre></details>)}
      <p>Approval applies only the qualified cases listed above. Other cases remain unchanged. Pending downstream work remains explicit.</p>
      <label>Batch owner credential<input type="password" autoComplete="off" disabled={busy} value={token} onChange={(event) => setToken(event.target.value)} /></label>
      <label><input type="checkbox" disabled={busy || !qualified.length} checked={approved} onChange={(event) => setApproved(event.target.checked)} />I approve the exact evidence for these {qualified.length} qualified cases.</label>
      <button disabled={busy || !approved || !token || !qualified.length} onClick={() => void apply()}>Approve and apply {qualified.length} decisions</button>
    </section>}
    {result && <div role="status">{result.map((item) => <p key={text(item.case_key)}>{text(item.case_key)}: {text(item.status)}. {text(item.error)}</p>)}</div>}
  </section>;
}

function batchActions(keys: string[]) {
  const mapping = keys.every((key) => ["team", "competition"].includes(key.split(":")[0]));
  return ["REVALIDATE", "REQUEST_EVIDENCE", "BLOCK", "DEFER", ...(mapping ? ["APPROVE", "QUARANTINE"] : []), ...(keys.every((key) => key.startsWith("team:")) ? ["REJECT"] : [])];
}
