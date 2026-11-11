package app

import (
	"encoding/json"
	"reflect"
	"testing"
)

func TestFormMissingnessReportsDefaultWindowState(t *testing.T) {
	if got := formMissingness(nil); !reflect.DeepEqual(got, []string{"RECENT_FORM_POLICY_UNKNOWN"}) {
		t.Fatalf("legacy report: %v", got)
	}
	form := &FormContext{
		DefaultWindow: "OFFICIAL_ALL_5",
		Home: TeamForm{Windows: map[string]FormWindow{
			"OFFICIAL_ALL_5": {Coverage: "COMPLETE", Flags: []string{"STALE", "AWARDED_INCLUDED"}},
			"PLAYED_ALL_5":   {Coverage: "EMPTY", Flags: []string{"RESULT_PENDING"}},
		}},
		Away: TeamForm{Windows: map[string]FormWindow{
			"OFFICIAL_ALL_5": {Coverage: "PARTIAL", Flags: []string{"STALE", "UNQUALIFIED_RESULT"}},
		}},
	}
	want := []string{"RECENT_FORM_INCOMPLETE", "RECENT_FORM_STALE", "RECENT_FORM_UNVERIFIED"}
	if got := formMissingness(form); !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v want %v", got, want)
	}
}

func TestLegacyContextReportDecodesWithoutFormMetadata(t *testing.T) {
	var item MatchContext
	payload := []byte(`{"fixture_id":"f","home_form":[{"kickoff_at":"2026-11-01T12:00:00Z","opponent":"A","venue":"HOME","goals_for":1,"goals_against":0,"result":"W"}],"away_form":[]}`)
	if err := json.Unmarshal(payload, &item); err != nil || item.Form != nil || item.HomeForm[0].FixtureID != "" {
		t.Fatalf("%+v %v", item, err)
	}
	encoded, err := json.Marshal(item.HomeForm[0])
	if err != nil {
		t.Fatal(err)
	}
	var fields map[string]any
	if err := json.Unmarshal(encoded, &fields); err != nil || len(fields) != 6 {
		t.Fatalf("legacy form match changed shape: %s", encoded)
	}
}
