import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def test_shared_backup_fixture_matches_transport_schema() -> None:
    schema = json.loads(Path("schemas/contracts/backup-status.schema.json").read_text())
    fixture = json.loads(Path("web/test-fixtures/backup-status.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(fixture)
