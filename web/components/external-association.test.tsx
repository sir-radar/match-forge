import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { AssociationSummary, associationLabel } from "@/components/external-association";
import { parsePredictions, type ExternalAssociation, type ExternalPrediction } from "@/lib/contracts";
import { ResolutionDecisionForm } from "@/components/resolution-decision";

const association: ExternalAssociation = {
  classification: "CONTEXTUAL_MATCH", reason: "UNIQUE_SAME_DAY", basis: "POLICY",
  policy_version: "EXTERNAL_PREDICTION_CONTEXTUAL_MATCHING_V1", decided_at: "2026-11-14T10:00:00Z",
  candidate_count: 1, fixture_home_team: "Everton", fixture_away_team: "Chelsea",
  fixture_competition: "Premier League", settlement_eligible: true, settlement_blocker: null, evaluation: "PROSPECTIVE",
};
const raw = {
  id: "p1", source: "MatchOutlook", source_page: "https://example.test", prediction_date: "2026-10-17",
  original_date_text: "Today", collected_at: "2026-10-17T09:00:00Z", fixture_id: "f1", kickoff_at: "2026-10-17T14:00:00Z",
  competition: "England Premier League", home_team: "Everton", away_team: "Chelsea", market: "RESULT_1X2",
  selection: "HOME_WIN", match_status: "CONTEXTUAL", matchforge_probability: null, agreement: "UNABLE_TO_EVALUATE",
  settlement_state: "WON", actual_home_score: 2, actual_away_score: 1, result_score_basis: "REGULATION_90",
  result_provider: null, result_updated_at: null, association,
};

it("parses the association and explains a contextual match in plain language", () => {
  const [item] = parsePredictions({ predictions: [raw] });
  render(<AssociationSummary item={item} />);
  fireEvent.click(screen.getByText("Contextually matched"));
  expect(screen.getByText("Everton vs Chelsea · Premier League")).toBeInTheDocument();
  expect(screen.getByText("Eligible")).toBeInTheDocument();
  expect(screen.getByText("Counts as a pre-kickoff prediction")).toBeInTheDocument();
  expect(() => parsePredictions({ predictions: [{ ...raw, association: { ...association, classification: "MAYBE" } }] })).toThrow("invalid association.classification");
});

it.each([
  [{ classification: "NEEDS_REVIEW", reason: "MULTIPLE_CANDIDATES" }, "Multiple possible fixtures"],
  [{ classification: "NEEDS_REVIEW", reason: "DATE_OFFSET" }, "Date or kickoff mismatch"],
  [{ classification: "NEEDS_REVIEW", reason: "OPPONENT_UNCONFIRMED" }, "Awaiting fixture review"],
  [{ classification: "UNMATCHED", reason: "NO_CORRESPONDING_FIXTURE" }, "No corresponding fixture found"],
  [{ classification: "UNMATCHED", reason: "NOT_EVALUATED" }, "Source fixture reference missing"],
  [{ classification: "CONTEXTUAL_MATCH", reason: "REVIEWED_ASSOCIATION", basis: "REVIEW", evaluation: "RETROSPECTIVE" }, "Retrospectively associated"],
  [{ classification: "VERIFIED", reason: "VERIFIED_PROVIDER_ID" }, "Verified fixture"],
] as const)("labels %o as %s", (change, label) => {
  expect(associationLabel({ ...association, ...change } as ExternalAssociation)).toBe(label);
});

it("shows review guidance and a blocker for an unresolved pick", () => {
  const item = { ...raw, association: { ...association, classification: "NEEDS_REVIEW", reason: "MULTIPLE_CANDIDATES", candidate_count: 2, fixture_home_team: null, fixture_away_team: null, settlement_eligible: false, settlement_blocker: "FIXTURE_IDENTITY", evaluation: null } } as unknown as ExternalPrediction;
  render(<AssociationSummary item={item} />);
  fireEvent.click(screen.getByText("Multiple possible fixtures"));
  expect(screen.getByText(/2 candidate fixtures retained/)).toBeInTheDocument();
  expect(screen.getByText("Waiting: Fixture identity")).toBeInTheDocument();
  expect(screen.getByText(/Resolution Center › External Predictions/)).toBeInTheDocument();
});

it("offers only external-only actions and retained candidates for review", () => {
  const key = "external_prediction:00000000-0000-4000-8000-000000000001";
  const candidate = { effective_fixture_id: "f1", home_team: "Everton", away_team: "Chelsea", competition: "Premier League", kickoff_at: "2026-10-17T14:00:00Z", identity_status: "VERIFIED" };
  render(<ResolutionDecisionForm caseKey={key} data={{ case_key: key, candidates: [candidate, candidate] }} onApplied={() => undefined} />);
  expect(screen.getAllByRole("option").map((option) => option.textContent).slice(0, 3)).toEqual(["APPROVE", "REJECT", "REVALIDATE"]);
  expect(screen.getByLabelText("Retained candidate fixture").querySelectorAll("option")).toHaveLength(2);
});
