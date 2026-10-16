-- +goose Up

ALTER TABLE football.product_competitions
    DROP CONSTRAINT product_competitions_geographic_scope_check;
ALTER TABLE football.product_competitions
    ADD CONSTRAINT product_competitions_geographic_scope_check
    CHECK (geographic_scope IS NULL OR
           (btrim(geographic_scope) <> '' AND
            lower(btrim(geographic_scope)) NOT IN ('unknown', 'world')));

-- +goose Down
ALTER TABLE football.product_competitions
    DROP CONSTRAINT product_competitions_geographic_scope_check;
ALTER TABLE football.product_competitions
    ADD CONSTRAINT product_competitions_geographic_scope_check
    CHECK (geographic_scope IS NULL OR
           (btrim(geographic_scope) <> '' AND
            lower(geographic_scope) NOT IN ('unknown', 'world')));
