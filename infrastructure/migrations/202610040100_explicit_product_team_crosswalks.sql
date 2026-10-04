-- +goose Up

CREATE TEMP TABLE product_team_crosswalk_repair (
    source_provider_code text NOT NULL,
    source_provider_team_id text NOT NULL,
    target_provider_code text NOT NULL,
    target_provider_team_id text NOT NULL
) ON COMMIT DROP;

INSERT INTO product_team_crosswalk_repair VALUES
    ('openfootball', 'Hull City', 'football_data_org', '322'),
    ('openfootball', 'Hull City AFC', 'football_data_org', '322'),
    ('football_data_uk', 'Hull', 'football_data_org', '322'),
    ('openfootball', 'Ipswich Town', 'football_data_org', '349'),
    ('openfootball', 'Ipswich Town FC', 'football_data_org', '349'),
    ('football_data_uk', 'Ipswich', 'football_data_org', '349'),
    ('football_data_uk', 'Cordoba', 'api_football', '713'),
    ('football_data_uk', 'Girona', 'api_football', '547'),
    ('football_data_uk', 'Granada', 'api_football', '715'),
    ('football_data_uk', 'Las Palmas', 'api_football', '534'),
    ('football_data_uk', 'Mallorca', 'api_football', '798'),
    ('football_data_uk', 'Tenerife', 'api_football', '719'),
    ('football_data_uk', 'Valladolid', 'api_football', '720'),
    ('openfootball', 'Real Sociedad B', 'api_football', '9585'),
    ('football_data_uk', 'Sociedad B', 'api_football', '9585'),
    ('football_data_uk', 'Sp Gijon', 'api_football', '731'),
    ('football_data_uk', 'Celta B', 'api_football', '9571'),
    ('openfootball', 'CD Castellón', 'api_football', '5254'),
    ('football_data_uk', 'Castellon', 'api_football', '5254'),
    ('openfootball', 'AD Ceuta FC', 'api_football', '10139'),
    ('football_data_uk', 'Ceuta', 'api_football', '10139');

CREATE TEMP TABLE product_team_id_repair ON COMMIT DROP AS
SELECT DISTINCT source_alias.team_id AS source_team_id,
       target_alias.team_id AS target_team_id
FROM product_team_crosswalk_repair repair
JOIN football.product_team_aliases source_alias
  ON source_alias.provider_code = repair.source_provider_code
 AND source_alias.provider_team_id = repair.source_provider_team_id
JOIN football.product_team_aliases target_alias
  ON target_alias.provider_code = repair.target_provider_code
 AND target_alias.provider_team_id = repair.target_provider_team_id
WHERE source_alias.team_id <> target_alias.team_id;

UPDATE football.product_team_match_history history
SET home_team_id = repair.target_team_id
FROM product_team_id_repair repair
WHERE history.home_team_id = repair.source_team_id;

UPDATE football.product_team_match_history history
SET away_team_id = repair.target_team_id
FROM product_team_id_repair repair
WHERE history.away_team_id = repair.source_team_id;

UPDATE football.product_fixtures fixture
SET home_team_id = repair.target_team_id
FROM product_team_id_repair repair
WHERE fixture.home_team_id = repair.source_team_id;

UPDATE football.product_fixtures fixture
SET away_team_id = repair.target_team_id
FROM product_team_id_repair repair
WHERE fixture.away_team_id = repair.source_team_id;

UPDATE football.product_team_aliases alias
SET team_id = repair.target_team_id
FROM product_team_id_repair repair
WHERE alias.team_id = repair.source_team_id;

UPDATE football.team_provider_mappings mapping
SET team_id = repair.target_team_id,
    mapping_method = 'explicit_crosswalk'
FROM product_team_id_repair repair
WHERE mapping.team_id = repair.source_team_id;

UPDATE football.team_provider_mappings mapping
SET mapping_method = 'explicit_crosswalk'
FROM football.providers provider,
     product_team_crosswalk_repair repair
WHERE mapping.provider_id = provider.id
  AND provider.code = repair.target_provider_code
  AND mapping.provider_team_id = repair.target_provider_team_id
  AND mapping.valid_to IS NULL;

-- +goose Down

-- Canonical identity corrections are intentionally retained on rollback.
