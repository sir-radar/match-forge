"""Statistical targets and their required evidence; no prices or probabilities."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from types import MappingProxyType

from football.contracts.source import canonical_json_bytes


@dataclass(frozen=True, slots=True)
class MarketInput:
    resources: tuple[str, ...]
    fields: tuple[str, ...]
    meaning: str
    coverage_unit: str = "canonical_fixture_id"


INPUTS = MappingProxyType(
    {
        "regulation_score": MarketInput(
            ("results", "summary", "scoreboard", "fixtures", "league"),
            ("home_goals", "away_goals", "score_basis"),
            (
                "Official team goals in regulation including added time; exclude"
                " extra time and shootouts."
            ),
        ),
        "period_score": MarketInput(
            ("summary", "results"),
            ("period", "home_goals", "away_goals", "period_complete", "score_basis"),
            "Directly qualified scores for the named period; never halve full-match intensity.",
        ),
        "goal_events": MarketInput(
            ("events", "summary"),
            ("event_type", "period", "minute", "player", "team"),
            (
                "Qualified ordered goals with scorer, own-goal beneficiary and"
                " period; exclude disallowed goals."
            ),
        ),
        "corners": MarketInput(
            ("statistics", "summary", "results", "fixtures"),
            ("corners", "period"),
            "Corners taken by the named team/period; awarded-but-untaken corners are excluded.",
        ),
        "corner_events": MarketInput(
            ("events", "summary"),
            ("corner_event_id", "team", "period", "event_clock"),
            (
                "Ordered, identity-qualified corner-taking events; aggregates"
                " cannot establish race order."
            ),
        ),
        "cards": MarketInput(
            ("events", "summary"),
            (
                "event_type",
                "source_card_type",
                "player",
                "recipient_role",
                "team",
                "period",
                "minute",
            ),
            (
                "Yellow, second-yellow and straight-red events remain distinct;"
                " eligibility and weights require a verified card rule."
            ),
        ),
        "shots": MarketInput(
            ("statistics", "summary", "results", "fixtures"),
            ("total_shots", "period"),
            "Goal attempts under an explicitly bound source/target definition.",
        ),
        "shots_on_target": MarketInput(
            ("statistics", "summary", "results", "fixtures"),
            ("shots_on_target", "period"),
            (
                "On-target attempts under a verified definition, including its"
                " blocked-shot and woodwork treatment."
            ),
        ),
        "fouls": MarketInput(
            ("statistics", "summary", "results", "fixtures"),
            ("fouls", "period"),
            (
                "Fouls committed; advantage, penalties and administrative"
                " infringements require definition agreement."
            ),
        ),
        "offsides": MarketInput(
            ("statistics", "summary", "results", "fixtures"),
            ("offsides", "period"),
            "Offsides credited under the bound definition.",
        ),
        "saves": MarketInput(
            ("statistics", "summary", "results", "fixtures"),
            ("saves", "period"),
            "Goalkeeper saves under the bound definition; not inferred from shots minus goals.",
        ),
        "tackles": MarketInput(
            ("statistics", "summary", "results", "fixtures"),
            ("tackles", "period"),
            (
                "Tackles under the bound definition; won and attempted tackles"
                " are not interchangeable."
            ),
        ),
        "throw_ins": MarketInput(
            ("statistics", "summary", "results", "fixtures"),
            ("throw_ins", "period"),
            "Throw-ins taken under the bound definition.",
        ),
        "goal_kicks": MarketInput(
            ("statistics", "summary", "results", "fixtures"),
            ("goal_kicks", "period"),
            "Goal kicks taken under the bound definition.",
        ),
        "woodwork": MarketInput(
            ("statistics", "summary", "results", "fixtures"),
            ("woodwork", "period"),
            (
                "Woodwork incidents under the bound definition, including"
                " repeat-contact and scoring-shot policy."
            ),
        ),
        "player_identity": MarketInput(
            ("players", "lineups", "player_statistics", "shots", "summary"),
            ("player", "canonical_identity_decision"),
            "Stable native-to-canonical player identity; names alone are insufficient.",
        ),
        "membership": MarketInput(
            ("players", "lineups", "player_statistics", "shots", "summary"),
            ("player", "team", "valid_from", "valid_to", "known_at"),
            (
                "Time-aware team/season membership and transfer evidence; fixture"
                " lineups do not establish continuous tenure."
            ),
        ),
        "participation": MarketInput(
            ("lineups", "summary"),
            ("lineup_mode", "role", "minutes_played", "position"),
            (
                "Start, substitute and nonappearance uncertainty with minutes"
                " exposure; a roster entry does not prove playing time."
            ),
        ),
        "player_statistics": MarketInput(
            ("player_statistics", "summary", "shots"),
            ("player", "team", "minutes_played", "target_statistic"),
            "Player events/counts under the exact named statistic and participation definition.",
        ),
        "assists": MarketInput(
            ("events", "summary"),
            ("player", "assisting_player", "goal_event", "assist_definition"),
            (
                "Credited goal assists with explicit deflection, rebound,"
                " penalty, own-goal and fantasy-assist rules; these definitions"
                " are not interchangeable."
            ),
        ),
    }
)


@dataclass(frozen=True, slots=True)
class MarketDefinition:
    market_id: str
    group: str
    period: str
    entity: str
    quantity: str
    requirements: tuple[str, ...]
    parameters: tuple[str, ...] = ()
    implementation: str | None = None
    model_product: str | None = None

    def __post_init__(self) -> None:
        if not self.market_id or not self.quantity.strip():
            raise ValueError("market identity and target meaning are required")
        if self.period not in {"REGULATION_90", "FIRST_HALF", "SECOND_HALF"}:
            raise ValueError("market period must be explicit")
        requirements, parameters = tuple(self.requirements), tuple(self.parameters)
        if not requirements or any(key not in INPUTS for key in requirements):
            raise ValueError("market needs explicit supported input requirements")
        if len(set(requirements)) != len(requirements) or len(set(parameters)) != len(parameters):
            raise ValueError("market inputs and target parameter names must be unique")
        object.__setattr__(self, "requirements", requirements)
        object.__setattr__(self, "parameters", parameters)

    @property
    def semantic_version(self) -> str:
        return self.market_id.lower() + "-v1"

    def to_dict(self) -> dict[str, object]:
        requirements = {key: asdict(INPUTS[key]) for key in self.requirements}
        if "player_statistics" in requirements and self.entity == "PLAYER":
            statistic = self.market_id.lower().removeprefix("player_").removeprefix("goalkeeper_")
            requirements["player_statistics"]["fields"] = (
                "player",
                "team",
                "minutes_played",
                statistic,
            )
        return {
            **asdict(self),
            "semantic_contract": {
                "version": self.semantic_version,
                "canonical_meaning": self.quantity,
                "period": self.period,
                "extra_time": "EXCLUDED",
                "shootout": "EXCLUDED",
                "penalties": "Scored in-period penalties count as goals; shootout attempts do not.",
                "own_goals": "Credit beneficiary team; exclude from named-player scorer targets.",
                "player_participation": (
                    "Explicit target nonappearance/void rule and participation evidence required."
                    if "participation" in self.requirements
                    else "NOT_APPLICABLE"
                ),
                "card_counting": "Explicit second-yellow, bench/staff, timing and weight rule."
                if "cards" in self.requirements
                else "NOT_APPLICABLE",
                "incomplete_or_void": (
                    "UNSCORABLE without complete outcomes and an explicit verified"
                    " target rule; missing is never zero."
                ),
                "corrections": (
                    "Append a revision with its real knowledge time; preserve prior"
                    " outcomes and forecasts."
                ),
                "source_compatibility": (
                    "UNKNOWN until source/target/period/rule versions are independently qualified."
                ),
                "sportsbook_equivalence": "UNVERIFIED; no automatic SportyBet or Opta equivalence.",
            },
            "data_requirements": requirements,
        }

    @property
    def sha256(self) -> str:
        value = self.to_dict()
        target = {
            key: value[key]
            for key in (
                "market_id",
                "entity",
                "semantic_contract",
                "data_requirements",
                "parameters",
            )
        }
        return hashlib.sha256(canonical_json_bytes(target)).hexdigest()


def _goal_markets() -> tuple[MarketDefinition, ...]:
    rows: list[MarketDefinition] = []
    goals = {
        "RESULT_1X2": "Compare home and away regulation goals.",
        "DOUBLE_CHANCE": "Union of two disjoint regulation result outcomes.",
        "DRAW_NO_BET": "Selected team wins, loses or pushes on a draw.",
        "CORRECT_SCORE": "Exact pair of regulation team goals; unresolved tail remains explicit.",
        "TOTAL_GOALS": "Sum of regulation team goals against the explicit line.",
        "TEAM_GOALS": "Named team's regulation goals against the explicit line.",
        "BTTS": "Both regulation team goal counts are positive.",
        "CLEAN_SHEET": "Named team's opponent has zero regulation goals.",
        "GOAL_RANGE": "Regulation goal sum within the explicit inclusive bounds.",
        "WINNING_MARGIN": "Signed home-minus-away regulation goal difference.",
        "ASIAN_GOAL_HANDICAP": (
            "Selected side's goal difference plus explicit handicap, with"
            " push and split-stake outcomes."
        ),
        "EUROPEAN_GOAL_HANDICAP": "Three-way comparison after the explicit goal handicap.",
        "RESULT_GOALS": (
            "Joint regulation result and goal-total condition from one score distribution."
        ),
    }
    implemented = {
        "RESULT_1X2",
        "DOUBLE_CHANCE",
        "CORRECT_SCORE",
        "TOTAL_GOALS",
        "TEAM_GOALS",
        "BTTS",
        "CLEAN_SHEET",
    }
    parameters = {
        "RESULT_1X2": ("selection",),
        "DOUBLE_CHANCE": ("selection",),
        "DRAW_NO_BET": ("team",),
        "CORRECT_SCORE": ("home_goals", "away_goals"),
        "TOTAL_GOALS": ("line", "selection"),
        "TEAM_GOALS": ("team", "line", "selection"),
        "BTTS": ("selection",),
        "CLEAN_SHEET": ("team", "selection"),
        "GOAL_RANGE": ("minimum", "maximum"),
        "WINNING_MARGIN": ("margin",),
        "ASIAN_GOAL_HANDICAP": ("team", "handicap"),
        "EUROPEAN_GOAL_HANDICAP": ("home_handicap", "selection"),
        "RESULT_GOALS": ("result", "goal_line", "goal_selection"),
    }
    for key, meaning in goals.items():
        rows.append(
            MarketDefinition(
                key,
                "GOALS",
                "REGULATION_90",
                "MATCH",
                meaning,
                ("regulation_score",),
                parameters[key],
                "football.forecasting.products.score_products" if key in implemented else None,
                "SCORE_DISTRIBUTION",
            )
        )
    return tuple(rows)


def _period_markets() -> tuple[MarketDefinition, ...]:
    rows: list[MarketDefinition] = []
    for period in ("FIRST_HALF", "SECOND_HALF"):
        for suffix, meaning in (
            ("RESULT", "Compare directly qualified period team goals."),
            ("TOTALS", "Sum directly qualified period goals against the line."),
            ("BTTS", "Both directly qualified period goal counts are positive."),
        ):
            rows.append(
                MarketDefinition(
                    period + "_" + suffix,
                    "PERIODS",
                    period,
                    "MATCH",
                    meaning,
                    ("period_score",),
                    ("line", "selection") if suffix == "TOTALS" else ("selection",),
                )
            )
    for key, meaning, required in (
        (
            "HT_FT",
            "Joint first-half and regulation result; dependence must be represented.",
            ("period_score", "regulation_score"),
        ),
        (
            "HIGHEST_SCORING_HALF",
            "Compare first- and second-half goal sums, including ties.",
            ("period_score",),
        ),
        (
            "SCORING_INTERVALS",
            (
                "Goals in explicit period-aware clock intervals; added-time"
                " attribution must be declared."
            ),
            ("goal_events",),
        ),
    ):
        rows.append(
            MarketDefinition(
                key,
                "PERIODS",
                "REGULATION_90",
                "MATCH",
                meaning,
                required,
                {
                    "HT_FT": ("first_half_result", "full_time_result"),
                    "HIGHEST_SCORING_HALF": ("half_or_tie",),
                    "SCORING_INTERVALS": ("start", "end", "boundary_rule", "line", "selection"),
                }[key],
            )
        )
    return tuple(rows)


def _count_markets() -> tuple[MarketDefinition, ...]:
    rows: list[MarketDefinition] = []
    for group, metric in (("CORNERS", "corners"), ("CARDS", "cards")):
        for suffix in ("TOTAL", "TEAM", "HANDICAP", "RANGE"):
            rows.append(
                MarketDefinition(
                    group + "_" + suffix,
                    group,
                    "REGULATION_90",
                    "TEAM" if suffix == "TEAM" else "MATCH",
                    INPUTS[metric].meaning
                    + " Apply the explicit selection/line/range and target rule.",
                    (metric,),
                    {
                        "TOTAL": ("selection", "line", "target_rule_version"),
                        "TEAM": ("team", "selection", "line", "target_rule_version"),
                        "HANDICAP": ("team", "handicap", "handicap_style", "target_rule_version"),
                        "RANGE": ("minimum", "maximum", "target_rule_version"),
                    }[suffix],
                    "football.forecasting.corner.CornerModels" if group == "CORNERS" else None,
                    "CORNER_COUNT" if group == "CORNERS" else None,
                )
            )
        for period in ("FIRST_HALF", "SECOND_HALF"):
            rows.append(
                MarketDefinition(
                    group + "_" + period,
                    group,
                    period,
                    "MATCH",
                    INPUTS[metric].meaning,
                    (metric,),
                    ("selection", "line", "target_rule_version"),
                )
            )
    rows.extend(
        (
            MarketDefinition(
                "CORNER_RACE",
                "CORNERS",
                "REGULATION_90",
                "MATCH",
                "First team to reach an explicit corner count using qualified event order.",
                ("corner_events",),
                ("team", "count", "target_rule_version"),
            ),
            MarketDefinition(
                "YELLOW_CARDS",
                "CARDS",
                "REGULATION_90",
                "MATCH",
                "Eligible yellow events under explicit second-yellow and participant rules.",
                ("cards",),
                ("selection", "line", "target_rule_version"),
            ),
            MarketDefinition(
                "RED_CARDS",
                "CARDS",
                "REGULATION_90",
                "MATCH",
                "Eligible straight-red and second-yellow dismissals under the declared rule.",
                ("cards",),
                ("selection", "line", "target_rule_version"),
            ),
            MarketDefinition(
                "CARD_POINTS",
                "CARDS",
                "REGULATION_90",
                "MATCH",
                (
                    "Weighted sum of eligible card events with explicit weights and"
                    " second-yellow rules."
                ),
                ("cards",),
                ("selection", "line", "yellow_points", "red_points", "target_rule_version"),
            ),
        )
    )
    return tuple(rows)


def _team_markets() -> tuple[MarketDefinition, ...]:
    rows: list[MarketDefinition] = []
    for metric in (
        "shots",
        "shots_on_target",
        "fouls",
        "offsides",
        "saves",
        "tackles",
        "throw_ins",
        "goal_kicks",
        "woodwork",
    ):
        rows.append(
            MarketDefinition(
                "TEAM_" + metric.upper(),
                "TEAM_STATISTICS",
                "REGULATION_90",
                "TEAM",
                INPUTS[metric].meaning,
                (metric,),
                ("team", "selection", "line", "target_rule_version"),
            )
        )
    return tuple(rows)


def _player_markets() -> tuple[MarketDefinition, ...]:
    rows: list[MarketDefinition] = []
    for statistic in (
        "GOALS",
        "ASSISTS",
        "SHOTS",
        "SHOTS_ON_TARGET",
        "PASSES",
        "TACKLES",
        "FOULS",
        "CARDS",
        "SAVES",
    ):
        required = (
            "goal_events"
            if statistic == "GOALS"
            else "assists"
            if statistic == "ASSISTS"
            else "cards"
            if statistic == "CARDS"
            else "player_statistics"
        )
        rows.append(
            MarketDefinition(
                "GOALKEEPER_SAVES" if statistic == "SAVES" else "PLAYER_" + statistic,
                "PLAYERS",
                "REGULATION_90",
                "PLAYER",
                f"Named player's {statistic.lower().replace('_', ' ')} "
                "with qualified identity, exposure and exact event definition.",
                ("player_identity", "membership", "participation", required),
                ("player", "selection", "line", "nonappearance_rule", "target_rule_version"),
            )
        )
    for order in ("ANYTIME", "FIRST", "LAST"):
        rows.append(
            MarketDefinition(
                order + "_SCORER",
                "PLAYERS",
                "REGULATION_90",
                "PLAYER",
                f"{order.title()} credited player scorer among eligible ordered goals; "
                "own goals excluded.",
                ("player_identity", "membership", "participation", "goal_events"),
                ("player", "nonappearance_rule", "no_scorer_rule", "target_rule_version"),
            )
        )
    return tuple(rows)


def _joint_markets() -> tuple[MarketDefinition, ...]:
    rows: list[MarketDefinition] = []
    for key, required in (
        ("GOALS_CORNERS", ("regulation_score", "corners")),
        ("GOALS_CARDS", ("regulation_score", "cards")),
        ("CORNERS_CARDS", ("corners", "cards")),
        ("SHOTS_SHOTS_ON_TARGET", ("shots", "shots_on_target")),
        ("TEAM_PLAYER", ("player_identity", "membership", "participation", "player_statistics")),
    ):
        rows.append(
            MarketDefinition(
                key,
                "JOINT",
                "REGULATION_90",
                "JOINT",
                (
                    "Qualified joint outcomes with represented dependence; marginal"
                    " multiplication requires independently validated justification."
                ),
                required,
                ("component_selections", "target_rule_versions"),
            )
        )
    return tuple(rows)


def market_catalogue() -> tuple[MarketDefinition, ...]:
    """Parameterised families use explicit lines/sides/rules, never default guesses."""
    return (
        *_goal_markets(),
        *_period_markets(),
        *_count_markets(),
        *_team_markets(),
        *_player_markets(),
        *_joint_markets(),
    )
