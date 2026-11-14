import type { ExternalAssociation, ExternalPrediction } from "@/lib/contracts";

const REVIEW_LABELS: Record<string, string> = {
  MULTIPLE_CANDIDATES: "Multiple possible fixtures",
  COMPETITION_MISMATCH: "Competition mismatch",
  DATE_OFFSET: "Date or kickoff mismatch",
  KICKOFF_MISMATCH: "Date or kickoff mismatch",
  RESCHEDULED_KICKOFF: "Date or kickoff mismatch",
  HOME_AWAY_REVERSED: "Home and away reversed",
  SOURCE_EVIDENCE_CONFLICT: "Source evidence conflicts",
};
const UNMATCHED_LABELS: Record<string, string> = {
  NO_FIXTURES_FOR_DATE: "No fixtures recorded for this date",
  SOURCE_CONTEXT_MISSING: "Source evidence unavailable",
  NOT_EVALUATED: "Source fixture reference missing",
  REVIEWED_REJECTION: "Association rejected on review",
};
const EXPLANATIONS: Record<string, string> = {
  VERIFIED_PROVIDER_ID: "The source's fixture ID matches a verified provider mapping.",
  UNIQUE_SAME_DAY: "Teams, home/away order, competition and the source's day point to exactly one fixture.",
  UNIQUE_MIDNIGHT_ADJACENT: "One fixture fits; it kicks off within three hours of the source day's midnight.",
  UNIQUE_EXACT_KICKOFF: "The source's kickoff time and teams point to exactly one fixture.",
  UNIQUE_VERIFIED_TWIN: "One verified fixture fits; the other records are provisional copies at the same kickoff.",
  REVIEWED_ASSOCIATION: "An owner chose this fixture from the retained candidates.",
  REVIEWED_REJECTION: "An owner rejected the proposed fixture.",
  MULTIPLE_CANDIDATES: "More than one fixture fits the source's teams and date.",
  COMPETITION_MISMATCH: "The fixture's country, tier or cup/league type contradicts the source's competition.",
  DATE_OFFSET: "The teams play on a neighbouring day, outside the source's publication day.",
  KICKOFF_MISMATCH: "The source's kickoff time contradicts the fixture's kickoff.",
  RESCHEDULED_KICKOFF: "The fixture was moved from the source's day; the pick may refer to the original date.",
  HOME_AWAY_REVERSED: "The teams play, but with home and away reversed.",
  SOURCE_EVIDENCE_CONFLICT: "The source page gives conflicting fixture references.",
  CANONICAL_IDENTITY_UNRESOLVED: "The only candidate fixture has an unresolved identity.",
  WEAK_CORROBORATION: "The source gives no competition and a team name is abbreviated, so a person must confirm.",
  OPPONENT_UNCONFIRMED: "One team matches a fixture on the day; the other name is not recognised.",
  ONE_TEAM_ONLY: "Only one of the two teams appears near the source's date.",
  NO_CORRESPONDING_FIXTURE: "No fixture between these teams is recorded near the source's date.",
  NO_FIXTURES_FOR_DATE: "MatchForge has no fixtures recorded around the source's date yet.",
  SOURCE_CONTEXT_MISSING: "The source does not give usable team names.",
  NOT_EVALUATED: "Matching has not run for this pick yet.",
};

export function associationLabel(association: ExternalAssociation): string {
  if (association.classification === "VERIFIED") return "Verified fixture";
  if (association.classification === "CONTEXTUAL_MATCH") {
    if (association.evaluation === "RETROSPECTIVE") return "Retrospectively associated";
    return association.basis === "REVIEW" ? "Reviewed association" : "Contextually matched";
  }
  if (association.classification === "NEEDS_REVIEW") return REVIEW_LABELS[association.reason] ?? "Awaiting fixture review";
  return UNMATCHED_LABELS[association.reason] ?? "No corresponding fixture found";
}

function readable(value: string): string {
  return value.toLowerCase().replaceAll("_", " ").replace(/^./, (character) => character.toUpperCase());
}

export function AssociationSummary({ item }: { item: ExternalPrediction }) {
  const association = item.association;
  if (!association) return item.match_status === "MATCHED" ? null : <p className="text-[#bbcabf]">{readable(item.match_status)} fixture</p>;
  const linked = association.fixture_home_team && association.fixture_away_team;
  const reviewable = association.classification === "NEEDS_REVIEW" || association.classification === "UNMATCHED";
  return <details className="text-[#bbcabf]">
    <summary className="cursor-pointer">{associationLabel(association)}</summary>
    <dl className="mt-1 grid max-w-md grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 whitespace-normal">
      <dt className="text-[#86948a]">Source</dt><dd>{item.competition} · {item.prediction_date}</dd>
      {linked && <><dt className="text-[#86948a]">MatchForge fixture</dt><dd>{association.fixture_home_team} vs {association.fixture_away_team}{association.fixture_competition ? ` · ${association.fixture_competition}` : ""}</dd></>}
      <dt className="text-[#86948a]">How</dt><dd>{EXPLANATIONS[association.reason] ?? readable(association.reason)}{association.candidate_count > 1 ? ` ${association.candidate_count} candidate fixtures retained.` : ""}</dd>
      <dt className="text-[#86948a]">Settlement</dt><dd>{association.settlement_eligible ? "Eligible" : association.settlement_blocker ? `Waiting: ${readable(association.settlement_blocker)}` : "Not eligible yet"}</dd>
      {association.evaluation && <><dt className="text-[#86948a]">Accuracy</dt><dd>{association.evaluation === "PROSPECTIVE" ? "Counts as a pre-kickoff prediction" : "Retrospective only; excluded from prospective accuracy"}</dd></>}
      {reviewable && <><dt className="text-[#86948a]">Action</dt><dd>An owner can review this pick in Admin › Resolution Center › External Predictions.</dd></>}
    </dl>
  </details>;
}
