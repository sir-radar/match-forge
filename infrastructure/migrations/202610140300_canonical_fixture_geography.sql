-- +goose Up

-- country remains the legacy provider-origin identity input. Geographic scope
-- classifies the competition, independently of venue or participant geography.
ALTER TABLE football.product_competitions ADD COLUMN geographic_scope text
    CHECK (geographic_scope IS NULL OR
           (btrim(geographic_scope) <> '' AND lower(geographic_scope) NOT IN ('unknown', 'world')));

UPDATE football.product_competitions SET geographic_scope = CASE
    WHEN lower(country) = 'unknown' THEN NULL
    WHEN country = 'World' THEN 'International'
    WHEN country = 'Czech Republic' THEN 'Czech-Republic'
    ELSE country END;

-- +goose StatementBegin
CREATE FUNCTION football.initialize_product_geography() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.geographic_scope IS NULL AND lower(NEW.country) <> 'unknown' THEN
        NEW.geographic_scope := CASE NEW.country
            WHEN 'World' THEN 'International'
            WHEN 'Czech Republic' THEN 'Czech-Republic'
            ELSE NEW.country END;
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER initialize_product_geography BEFORE INSERT OR UPDATE OF country
    ON football.product_competitions FOR EACH ROW
    EXECUTE FUNCTION football.initialize_product_geography();

-- +goose StatementBegin
CREATE FUNCTION football.require_product_fixture_geography() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM football.product_competitions c
                   WHERE c.competition_id=NEW.competition_id AND c.geographic_scope IS NOT NULL) THEN
        RAISE EXCEPTION 'CANONICAL_FIXTURE_GEOGRAPHY_REQUIRED';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER require_product_fixture_geography BEFORE INSERT OR UPDATE OF competition_id
    ON football.product_fixtures FOR EACH ROW
    EXECUTE FUNCTION football.require_product_fixture_geography();

-- +goose StatementBegin
CREATE FUNCTION football.preserve_product_fixture_geography() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.geographic_scope IS NULL AND EXISTS (
        SELECT 1 FROM football.product_fixtures f WHERE f.competition_id=NEW.competition_id) THEN
        RAISE EXCEPTION 'CANONICAL_FIXTURE_GEOGRAPHY_REQUIRED';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER preserve_product_fixture_geography BEFORE UPDATE OF geographic_scope
    ON football.product_competitions FOR EACH ROW
    EXECUTE FUNCTION football.preserve_product_fixture_geography();

-- +goose Down
-- Preserve classifications and canonical fixture requirements.
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'canonical fixture geography is a forward-only migration'; END $$;
-- +goose StatementEnd
