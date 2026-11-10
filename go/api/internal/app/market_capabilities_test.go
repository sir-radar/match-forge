package app

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type marketReaderStub struct {
	syncRunnerStub
	calls  int
	result json.RawMessage
}

func (reader *marketReaderStub) MarketCapabilities(_ context.Context, scope marketScope) (json.RawMessage, error) {
	reader.calls++
	if reader.result != nil {
		return reader.result, nil
	}
	return json.RawMessage(fmt.Sprintf(`{"contract":"MarketCapabilitySummary","contract_version":"1","competition_id":%q,"season_id":%q,"knowledge_cutoff":%q,"recorded_at":"2026-10-31T00:00:01Z","read_only":"on","authoritative":false,"markets":[],"provider_candidates":[],"limitations":[],"automatic_promotion":false,"monitoring_scope":"EXISTING_PUBLISHED_GOAL_FORECASTS_ONLY","new_market_settlement":"NOT_IMPLEMENTED"}`, scope.CompetitionID, scope.SeasonID, scope.KnowledgeCutoff.Format(time.RFC3339Nano))), nil
}

const marketQuery = "competition_id=00000000-0000-4000-8000-000000000001&season_id=00000000-0000-4000-8000-000000000002&knowledge_cutoff=2026-10-31T00:00:00Z"

func TestMarketCapabilitiesAdminProtectionAndScope(t *testing.T) {
	reader := &marketReaderStub{}
	app := newAdminTestApp(reader)
	response := httptest.NewRecorder()
	app.Handler().ServeHTTP(response, httptest.NewRequest("GET", "/v1/admin/market-capabilities?"+marketQuery, nil))
	if response.Code != 403 || reader.calls != 0 {
		t.Fatal("admin protection bypassed")
	}
	response = httptest.NewRecorder()
	app.Handler().ServeHTTP(response, localAdminTestRequest("GET", "/v1/admin/market-capabilities?"+marketQuery, nil))
	if response.Code != 200 || reader.calls != 1 || response.Header().Get("Cache-Control") != "no-store" {
		t.Fatalf("%d %s", response.Code, response.Body)
	}
}
func TestMarketCapabilitiesInvalidScopesNeverRunPython(t *testing.T) {
	for _, query := range []string{"", marketQuery + "&extra=x", strings.Replace(marketQuery, "00:00:00Z", "00:00:00.123456789Z", 1), marketQuery + "&season_id=duplicate", "competition_id=native-name&season_id=1&knowledge_cutoff=2026-10-31T00:00:00Z", "competition_id=00000000-0000-4000-8000-000000000001&season_id=00000000-0000-4000-8000-000000000002&knowledge_cutoff=2999-01-01T00:00:00Z"} {
		reader := &marketReaderStub{}
		response := httptest.NewRecorder()
		newAdminTestApp(reader).Handler().ServeHTTP(response, localAdminTestRequest("GET", "/v1/admin/market-capabilities?"+query, nil))
		if response.Code != 400 || reader.calls != 0 {
			t.Fatalf("invalid query executed: %d %s", response.Code, query)
		}
	}
}
func TestMarketCapabilitiesRejectUnboundOrAuthoritativeOutputs(t *testing.T) {
	for _, payload := range []string{`{}`, `{"contract":"MarketCapabilitySummary","authoritative":true}`, `[]`} {
		reader := &marketReaderStub{result: json.RawMessage(payload)}
		response := httptest.NewRecorder()
		newAdminTestApp(reader).Handler().ServeHTTP(response, localAdminTestRequest("GET", "/v1/admin/market-capabilities?"+marketQuery, nil))
		if response.Code != 503 {
			t.Fatalf("invalid report accepted: %d", response.Code)
		}
	}
}
func TestMarketCapabilitiesDatabaseBridge(t *testing.T) {
	pool := servingDatabasePool(t)
	competition, _, _, season := seedServingFixtureIdentities(t, pool, "Market bridge")
	root, err := filepath.Abs("../../../..")
	if err != nil {
		t.Fatal(err)
	}
	runner := &CommandSyncRunner{pool: pool, repoRoot: root}
	scope := marketScope{CompetitionID: competition, SeasonID: season, KnowledgeCutoff: time.Now().UTC().Truncate(time.Microsecond)}
	ctx, cancel := context.WithTimeout(context.Background(), 25*time.Second)
	defer cancel()
	data, err := runner.MarketCapabilities(ctx, scope)
	if err != nil {
		t.Fatal(err)
	}
	if err = validateMarketSummary(data, scope); err != nil {
		t.Fatal(err)
	}
	var report struct {
		Markets []json.RawMessage `json:"markets"`
	}
	if json.Unmarshal(data, &report) != nil || len(report.Markets) < 67 {
		t.Fatal("catalogue missing")
	}
	// Retain exact real bridge output for OpenAPI and browser contract verification.
	if path := os.Getenv("TEST_MARKET_SUMMARY_PATH"); path != "" {
		if err = os.WriteFile(path, data, 0600); err != nil {
			t.Fatal(err)
		}
	}
}
