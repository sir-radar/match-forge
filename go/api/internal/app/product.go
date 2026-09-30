package app

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"time"
)

var errProductUnavailable = errors.New("product data unavailable")

type CompetitionFilters struct {
	Continent         string
	Country           string
	Division          int
	ForecastAvailable *bool
}

type FixtureFilters struct {
	Date                 time.Time
	CompetitionID        string
	Country              string
	Continent            string
	ForecastAvailability string
}

type ExternalPredictionFilters struct {
	Date        time.Time
	Source      string
	Competition string
	Market      string
	Agreement   string
	FixtureID   string
}

type ProductStore interface {
	Competitions(context.Context, CompetitionFilters) ([]Competition, error)
	Fixtures(context.Context, FixtureFilters) ([]FixtureGroup, error)
	FixtureContext(context.Context, string) (MatchContext, error)
	Forecast(context.Context, string, string) (Forecast, error)
	Standings(context.Context, string) ([]StandingRow, error)
	Performance(context.Context, string) (Performance, error)
	ExternalPredictions(context.Context, ExternalPredictionFilters) ([]ExternalPrediction, error)
	ExternalPredictionSources(context.Context) ([]ExternalPredictionSource, error)
}

type unavailableProductStore struct{}

func (unavailableProductStore) Competitions(context.Context, CompetitionFilters) ([]Competition, error) {
	return nil, errProductUnavailable
}
func (unavailableProductStore) Fixtures(context.Context, FixtureFilters) ([]FixtureGroup, error) {
	return nil, errProductUnavailable
}
func (unavailableProductStore) FixtureContext(context.Context, string) (MatchContext, error) {
	return MatchContext{}, errProductUnavailable
}
func (unavailableProductStore) Forecast(context.Context, string, string) (Forecast, error) {
	return Forecast{}, errProductUnavailable
}
func (unavailableProductStore) Standings(context.Context, string) ([]StandingRow, error) {
	return nil, errProductUnavailable
}
func (unavailableProductStore) Performance(context.Context, string) (Performance, error) {
	return Performance{}, errProductUnavailable
}
func (unavailableProductStore) ExternalPredictions(context.Context, ExternalPredictionFilters) ([]ExternalPrediction, error) {
	return nil, errProductUnavailable
}
func (unavailableProductStore) ExternalPredictionSources(context.Context) ([]ExternalPredictionSource, error) {
	return nil, errProductUnavailable
}

type Competition struct {
	ID                 string              `json:"id"`
	Name               string              `json:"name"`
	Country            string              `json:"country"`
	Continent          string              `json:"continent"`
	Division           *int                `json:"division"`
	Type               string              `json:"type"`
	Season             string              `json:"season"`
	Availability       Availability        `json:"availability"`
	AvailabilityStatus string              `json:"availability_status"`
	Sources            map[string][]string `json:"sources"`
}

type Availability struct {
	Fixtures  bool `json:"fixtures"`
	Results   bool `json:"results"`
	Standings bool `json:"standings"`
	H2H       bool `json:"h2h"`
	Forecast  bool `json:"forecast"`
	XG        bool `json:"xg"`
	TeamStats bool `json:"team_stats"`
}

type FixtureGroup struct {
	Competition Competition `json:"competition"`
	Fixtures    []Fixture   `json:"fixtures"`
}

type Fixture struct {
	ID                   string           `json:"id"`
	KickoffAt            time.Time        `json:"kickoff_at"`
	Status               string           `json:"status"`
	Home                 Team             `json:"home"`
	Away                 Team             `json:"away"`
	HomeScore            *int             `json:"home_score"`
	AwayScore            *int             `json:"away_score"`
	Venue                *string          `json:"venue"`
	Round                *string          `json:"round"`
	ForecastAvailability string           `json:"forecast_availability"`
	Forecast             *ForecastSummary `json:"forecast"`
}

type Team struct {
	ID       string  `json:"id"`
	Name     string  `json:"name"`
	CrestURL *string `json:"crest_url"`
}

type ForecastSummary struct {
	ID                string             `json:"id"`
	ExpectedHomeGoals float64            `json:"expected_home_goals"`
	ExpectedAwayGoals float64            `json:"expected_away_goals"`
	Probabilities     map[string]float64 `json:"probabilities"`
}

type Forecast struct {
	ForecastSummary
	FixtureID       string                   `json:"fixture_id"`
	ModelLabel      string                   `json:"model_label"`
	ModelAlgorithm  string                   `json:"model_algorithm_version"`
	CreatedAt       time.Time                `json:"created_at"`
	FootballCutoff  time.Time                `json:"football_cutoff"`
	KnowledgeCutoff time.Time                `json:"knowledge_cutoff"`
	KnowledgeMode   string                   `json:"knowledge_mode"`
	PublicationMode string                   `json:"publication_mode"`
	ScoreMatrix     []map[string]interface{} `json:"score_matrix"`
}

type FormMatch struct {
	KickoffAt    time.Time `json:"kickoff_at"`
	Opponent     string    `json:"opponent"`
	Venue        string    `json:"venue"`
	GoalsFor     int       `json:"goals_for"`
	GoalsAgainst int       `json:"goals_against"`
	Result       string    `json:"result"`
}

type H2HMatch struct {
	KickoffAt time.Time `json:"kickoff_at"`
	HomeTeam  string    `json:"home_team"`
	AwayTeam  string    `json:"away_team"`
	HomeGoals int       `json:"home_goals"`
	AwayGoals int       `json:"away_goals"`
}

type MatchContext struct {
	FixtureID  string          `json:"fixture_id"`
	HomeForm   []FormMatch     `json:"home_form"`
	AwayForm   []FormMatch     `json:"away_form"`
	H2H        []H2HMatch      `json:"h2h"`
	Standings  []StandingRow   `json:"standings"`
	DataStatus map[string]bool `json:"data_availability"`
}

type StandingRow struct {
	Position       int    `json:"position"`
	TeamID         string `json:"team_id"`
	Team           string `json:"team"`
	Played         int    `json:"played"`
	Won            int    `json:"won"`
	Drawn          int    `json:"drawn"`
	Lost           int    `json:"lost"`
	GoalsFor       int    `json:"goals_for"`
	GoalsAgainst   int    `json:"goals_against"`
	GoalDifference int    `json:"goal_difference"`
	Points         int    `json:"points"`
}

type Performance struct {
	CompetitionID    string   `json:"competition_id"`
	Rating           string   `json:"rating"`
	Forecasts        int      `json:"forecasts"`
	OutcomeHitRate   *float64 `json:"outcome_hit_rate"`
	Brier            *float64 `json:"brier"`
	LogLoss          *float64 `json:"log_loss"`
	BaselineBrier    *float64 `json:"baseline_brier"`
	BaselineLogLoss  *float64 `json:"baseline_log_loss"`
	ExactScoreRate   *float64 `json:"exact_score_rate"`
	TopThreeRate     *float64 `json:"top_three_score_rate"`
	TopFiveRate      *float64 `json:"top_five_score_rate"`
	TotalsHitRate    *float64 `json:"total_goals_hit_rate"`
	BTTSHitRate      *float64 `json:"btts_hit_rate"`
	LatestFiftyBrier *float64 `json:"latest_fifty_brier"`
	LatestFiftyLog   *float64 `json:"latest_fifty_log_loss"`
	LatestBaseBrier  *float64 `json:"latest_fifty_baseline_brier"`
	LatestBaseLog    *float64 `json:"latest_fifty_baseline_log_loss"`
}

type ExternalPrediction struct {
	ID                    string     `json:"id"`
	Source                string     `json:"source"`
	SourcePage            string     `json:"source_page"`
	PredictionDate        string     `json:"prediction_date"`
	OriginalDateText      string     `json:"original_date_text"`
	CollectedAt           time.Time  `json:"collected_at"`
	FixtureID             *string    `json:"fixture_id"`
	KickoffAt             *time.Time `json:"kickoff_at"`
	Competition           string     `json:"competition"`
	HomeTeam              string     `json:"home_team"`
	AwayTeam              string     `json:"away_team"`
	Market                string     `json:"market"`
	Selection             string     `json:"selection"`
	MatchStatus           string     `json:"match_status"`
	MatchForgeProbability *float64   `json:"matchforge_probability"`
	Agreement             string     `json:"agreement"`
}

type ExternalPredictionSource struct {
	Code                  string    `json:"code"`
	Name                  string    `json:"name"`
	URL                   string    `json:"url"`
	PublicPredictions     bool      `json:"public_predictions"`
	PredictionDate        bool      `json:"prediction_date_available"`
	LoginRequired         bool      `json:"login_required"`
	PaidContent           bool      `json:"paid_content"`
	AutomatedAccessStatus string    `json:"automated_access_status"`
	AdapterStatus         string    `json:"adapter_status"`
	KnownIssues           string    `json:"known_issues"`
	CheckedAt             time.Time `json:"checked_at"`
	TrackedSelections     int       `json:"tracked_selections"`
	SettledHitRate        *float64  `json:"settled_hit_rate"`
}

func (application *App) listCompetitions(response http.ResponseWriter, request *http.Request) {
	filters := CompetitionFilters{
		Continent: request.URL.Query().Get("continent"),
		Country:   request.URL.Query().Get("country"),
	}
	if value := request.URL.Query().Get("division"); value != "" {
		parsed, err := strconv.Atoi(value)
		if err != nil || parsed <= 0 {
			application.publicError(response, http.StatusBadRequest, "invalid division")
			return
		}
		filters.Division = parsed
	}
	if value := request.URL.Query().Get("forecast_available"); value != "" {
		parsed, err := strconv.ParseBool(value)
		if err != nil {
			application.publicError(response, http.StatusBadRequest, "invalid forecast_available")
			return
		}
		filters.ForecastAvailable = &parsed
	}
	items, err := application.product.Competitions(request.Context(), filters)
	application.respondProduct(response, map[string]any{"competitions": items}, err)
}

func (application *App) listFixtures(response http.ResponseWriter, request *http.Request) {
	value := request.URL.Query().Get("date")
	requestedDate, err := time.Parse("2006-01-02", value)
	if err != nil {
		application.publicError(response, http.StatusBadRequest, "date must use YYYY-MM-DD")
		return
	}
	filters := FixtureFilters{
		Date: requestedDate, CompetitionID: request.URL.Query().Get("competition"),
		Country: request.URL.Query().Get("country"), Continent: request.URL.Query().Get("continent"),
		ForecastAvailability: request.URL.Query().Get("forecast_availability"),
	}
	items, err := application.product.Fixtures(request.Context(), filters)
	application.respondProduct(response, map[string]any{"date": value, "groups": items}, err)
}

func (application *App) fixtureContext(response http.ResponseWriter, request *http.Request) {
	item, err := application.product.FixtureContext(request.Context(), request.PathValue("fixture_id"))
	application.respondProduct(response, item, err)
}

func (application *App) forecast(response http.ResponseWriter, request *http.Request) {
	item, err := application.product.Forecast(
		request.Context(), request.PathValue("fixture_id"), request.PathValue("forecast_id"),
	)
	application.respondProduct(response, item, err)
}

func (application *App) standings(response http.ResponseWriter, request *http.Request) {
	items, err := application.product.Standings(request.Context(), request.PathValue("competition_id"))
	application.respondProduct(response, map[string]any{"standings": items}, err)
}

func (application *App) performance(response http.ResponseWriter, request *http.Request) {
	item, err := application.product.Performance(request.Context(), request.PathValue("competition_id"))
	application.respondProduct(response, item, err)
}

func (application *App) externalPredictions(response http.ResponseWriter, request *http.Request) {
	filters, err := externalFilters(request)
	if err != nil {
		application.publicError(response, http.StatusBadRequest, err.Error())
		return
	}
	items, err := application.product.ExternalPredictions(request.Context(), filters)
	application.respondProduct(response, map[string]any{"predictions": items}, err)
}

func (application *App) fixtureExternalPredictions(response http.ResponseWriter, request *http.Request) {
	items, err := application.product.ExternalPredictions(
		request.Context(), ExternalPredictionFilters{FixtureID: request.PathValue("fixture_id")},
	)
	application.respondProduct(response, map[string]any{"predictions": items}, err)
}

func (application *App) externalPredictionSources(response http.ResponseWriter, request *http.Request) {
	items, err := application.product.ExternalPredictionSources(request.Context())
	application.respondProduct(response, map[string]any{"sources": items}, err)
}

func externalFilters(request *http.Request) (ExternalPredictionFilters, error) {
	filters := ExternalPredictionFilters{
		Source: request.URL.Query().Get("source"), Competition: request.URL.Query().Get("competition"),
		Market: request.URL.Query().Get("market"), Agreement: request.URL.Query().Get("agreement"),
		FixtureID: request.URL.Query().Get("fixture_id"),
	}
	if value := request.URL.Query().Get("date"); value != "" {
		parsed, err := time.Parse("2006-01-02", value)
		if err != nil {
			return ExternalPredictionFilters{}, fmt.Errorf("date must use YYYY-MM-DD")
		}
		filters.Date = parsed
	}
	return filters, nil
}

func (application *App) respondProduct(response http.ResponseWriter, value any, err error) {
	if err == nil {
		application.writeJSON(response, http.StatusOK, value)
		return
	}
	if errors.Is(err, errProductUnavailable) {
		application.publicError(response, http.StatusServiceUnavailable, "product data unavailable")
		return
	}
	application.logger.Error("product API", "error", err)
	application.publicError(response, http.StatusInternalServerError, "internal error")
}

func (application *App) publicError(response http.ResponseWriter, status int, message string) {
	application.writeJSON(response, status, map[string]string{"error": message})
}
