package app

import "context"

// SQL permits a V2 route only during an approved isolated, currently leased trial.
func (store *PostgresProductStore) fixtureServingRelation(ctx context.Context) (string, error) {
	var installed bool
	if err := store.pool.QueryRow(ctx, `SELECT to_regprocedure('football.resolution_fixture_route()') IS NOT NULL`).Scan(&installed); err != nil {
		return "", err
	}
	if !installed {
		return fixtureRouteRelation("LEGACY")
	}
	var route string
	if err := store.pool.QueryRow(ctx, `SELECT football.resolution_fixture_route()`).Scan(&route); err != nil {
		return "", err
	}
	return fixtureRouteRelation(route)
}
func fixtureRouteRelation(route string) (string, error) {
	switch route {
	case "LEGACY":
		return "football.product_serving_fixtures", nil
	case "V2":
		return "football.fixture_read_model", nil
	default:
		return "", errProductUnavailable
	}
}

func (store *PostgresProductStore) validateFixtureRoute(ctx context.Context, relation string, queryErr error) error {
	if queryErr != nil {
		return queryErr
	}
	if relation != "football.fixture_read_model" {
		return nil
	}
	current, err := store.fixtureServingRelation(ctx)
	if err != nil {
		return err
	}
	if current != relation {
		return errProductUnavailable
	}
	return nil
}
