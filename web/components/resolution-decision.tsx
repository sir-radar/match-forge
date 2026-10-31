"use client";

import { useState } from "react";
import { useResolutionOperation } from "@/components/use-resolution-operation";
import { resolutionApi, text, type Decision, type Preview, type RecordValue } from "@/lib/resolution";

const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Decision unavailable";
type Prepared = Preview & { request_id: string };

function objectList(value: unknown): RecordValue[] {
  return Array.isArray(value) ? value.filter((item): item is RecordValue => item !== null && typeof item === "object" && !Array.isArray(item)) : [];
}
function actionsFor(key: string, data: RecordValue): string[] {
  const kind = key.split(":")[0];
  const actions = ["REVALIDATE", "REQUEST_EVIDENCE", "BLOCK", "DEFER"];
  if (["team", "competition"].includes(kind)) actions.push("APPROVE", "QUARANTINE", "REJECT");
  if (kind === "team" && objectList(data.correction_options).length) actions.push("CORRECT");
  if (kind === "fixture") actions.push("RESOLVE_DUPLICATE");
  return actions;
}

export function ResolutionDecisionForm({ caseKey, data, onApplied }: { caseKey: string; data: RecordValue; onApplied: () => void }) {
  const [action, setAction] = useState("REVALIDATE"), [reason, setReason] = useState("");
  const [candidate, setCandidate] = useState<Record<string, string>>({});
  const [prepared, setPrepared] = useState<Prepared>(), [error, setError] = useState<string>();
  const [token, setToken] = useState(""), [approved, setApproved] = useState(false), [busy, setBusy] = useState(false);
  const [result, setResult] = useState<RecordValue>();
  const operation = useResolutionOperation();
  const invalidate = () => { operation.cancelRead(); setPrepared(undefined); setApproved(false); setResult(undefined); setError(undefined); };
  const preview = async () => {
    if (!operation.begin()) return;
    setBusy(true); invalidate();
    const abort = operation.newRead();
    try {
      const value = await resolutionApi.preview({ case_key: caseKey, action, candidate, reason }, abort.signal);
      if (operation.isMounted() && !abort.signal.aborted) setPrepared({ ...value, request_id: crypto.randomUUID() });
    } catch (cause) { if (operation.isMounted() && !abort.signal.aborted) setError(errorMessage(cause)); }
    finally { operation.finish(); if (operation.isMounted()) setBusy(false); }
  };
  const apply = async () => {
    if (!prepared?.allowed || !approved || !token || !operation.begin()) return;
    setBusy(true); setError(undefined);
    const decision: Decision = { case_key: prepared.case_key, action: prepared.action, reason: prepared.reason, candidate: prepared.candidate, evidence_version: prepared.evidence_version, request_id: prepared.request_id, approved: true };
    try {
      const value = await resolutionApi.apply(decision, token);
      if (operation.isMounted()) { setResult(value); setApproved(false); setToken(""); onApplied(); }
    } catch (cause) { if (operation.isMounted()) { setError(errorMessage(cause)); setApproved(false); } }
    finally { operation.finish(); if (operation.isMounted()) setBusy(false); }
  };
  return <section aria-label="Decision workflow">
    <form className="resolution-form" onSubmit={(event) => { event.preventDefault(); void preview(); }}>
      <label>Action<select disabled={busy} value={action} onChange={(event) => { invalidate(); setCandidate({}); setAction(event.target.value); }}>{actionsFor(caseKey, data).map((value) => <option key={value}>{value}</option>)}</select></label>
      <CandidateFields action={action} data={data} candidate={candidate} disabled={busy} update={(value) => { invalidate(); setCandidate(value); }} />
      <label>Reason<textarea required maxLength={2000} disabled={busy} value={reason} onChange={(event) => { invalidate(); setReason(event.target.value); }} /></label>
      <button disabled={busy || !reason.trim()} type="submit">Preview impact and evidence</button>
    </form>
    {error && <p role="alert">{error} Retry the same approval if its outcome is unknown; a changed proposal needs a new preview.</p>}
    {prepared && <section aria-label="Approval preview">
      <h3>{prepared.allowed ? "QUALIFIED" : "BLOCKED"}: {text(prepared.qualification.reason)}</h3>
      <p>Evidence version: {prepared.evidence_version}</p><p>Exact case: {prepared.case_key}. Action: {prepared.action}. Reason: {prepared.reason}.</p>
      <details><summary>Preview exact source and impact</summary><pre className="resolution-json">{JSON.stringify(prepared, null, 2)}</pre></details>
      <p>Earlier knowledge cutoffs stay unchanged. Reconciliation and downstream refresh can remain pending after this decision.</p>
      <label>Owner credential<input type="password" autoComplete="off" disabled={busy} value={token} onChange={(event) => setToken(event.target.value)} /></label>
      <label><input type="checkbox" disabled={busy || !prepared.allowed} checked={approved} onChange={(event) => setApproved(event.target.checked)} />I approve this exact evidence and impact.</label>
      <button disabled={busy || !approved || !token || !prepared.allowed} onClick={() => void apply()}>Approve and apply decision</button>
    </section>}
    {result && <div role="status">Decision recorded. Request: {text(result.request_id)}. Inspect history for the domain result and pending work.</div>}
  </section>;
}

function CandidateFields({ action, data, candidate, disabled, update }: { action: string; data: RecordValue; candidate: Record<string, string>; disabled: boolean; update: (value: Record<string, string>) => void }) {
  if (action === "CORRECT" || action === "REJECT") return <>
    <label>Target mapping<select required disabled={disabled} value={candidate.target_mapping_id ?? ""} onChange={(event) => update({ ...candidate, target_mapping_id: event.target.value })}><option value="">Choose retained candidate</option>{objectList(data.candidates).map((item) => <option key={text(item.mapping_id)} value={text(item.mapping_id)}>{text(item.name)} · {text(item.provider)} · {text(item.mapping_id)}</option>)}</select></label>
    {action === "CORRECT" && <label>Retained contradiction<select required disabled={disabled} value={candidate.original_decision_id ?? ""} onChange={(event) => { const context = objectList(data.correction_options).find((item) => item.original_decision_id === event.target.value); if (context) update({ ...candidate, original_decision_id: text(context.original_decision_id), fixture_registration_id: text(context.fixture_registration_id), orientation: text(context.orientation) }); }}><option value="">Choose fixture evidence</option>{objectList(data.correction_options).map((item) => <option key={text(item.original_decision_id)} value={text(item.original_decision_id)}>{text(item.orientation)} · {text(item.fixture_id)}</option>)}</select></label>}
  </>;
  if (action === "RESOLVE_DUPLICATE") {
    const decision = data.decision as RecordValue, observation = data.observation as RecordValue | null;
    return <label>Retained fixture candidate<select required disabled={disabled} value={candidate.fixture_id ?? ""} onChange={(event) => update({ fixture_id: event.target.value, source_snapshot_id: text(observation?.source_snapshot_id) })}><option value="">Choose retained fixture</option><option value={text(decision?.candidate_fixture_id)}>{text(decision?.candidate_fixture_id)}</option></select></label>;
  }
  return null;
}
