package app

import "testing"

func TestFixtureMigrationRoutesAreClosed(t *testing.T) {
	for route, relation := range map[string]string{"LEGACY": "football.product_serving_fixtures", "V2": "football.fixture_read_model"} {
		got, err := fixtureRouteRelation(route)
		if err != nil || got != relation {
			t.Fatal("wrong stage-backed serving relation")
		}
	}
	for _, route := range []string{"", "fixture_read_model", "V2;DROP TABLE football.matches", "SHADOW"} {
		if relation, err := fixtureRouteRelation(route); err == nil || relation != "" {
			t.Fatal("unqualified route accepted")
		}
	}
}
