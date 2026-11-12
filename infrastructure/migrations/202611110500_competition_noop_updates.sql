-- +goose Up
-- updated_at is the read model's last material change, not a provider observation clock.
-- Provider snapshots/capabilities retain their own observation and source timestamps.
-- Runs after the geography guards. Does not rewrite, vacuum or touch existing rows.
-- +goose StatementBegin
CREATE FUNCTION football.skip_unchanged_product_competition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.updated_at IS NOT NULL AND (to_jsonb(NEW)-'updated_at') IS NOT DISTINCT FROM (to_jsonb(OLD)-'updated_at') THEN
  RETURN NULL;
 END IF;
 RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER zz_storage_skip_unchanged_competition BEFORE UPDATE ON football.product_competitions
 FOR EACH ROW EXECUTE FUNCTION football.skip_unchanged_product_competition();

-- +goose Down
DROP TRIGGER zz_storage_skip_unchanged_competition ON football.product_competitions;
DROP FUNCTION football.skip_unchanged_product_competition();
