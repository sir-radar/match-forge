"""Machine-readable contract for immutable descriptive evaluation records."""

from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from football.contracts.source import canonical_json_bytes, sha256_bytes


def postmatch_schema() -> dict[str, Any]:
    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    identity = {"type": "string", "format": "uuid"}
    text = {"type": "string", "minLength": 1}
    clock = {"type": "string", "format": "date-time"}
    inputs = {
        "contract": {"const": "PostMatchEvaluationInput"},
        "policy_version": {"const": "postmatch-monitoring-v1"},
        "code_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
        "dependency_lock_sha256": sha,
        "forecast_id": identity,
        "fixture_id": identity,
        "competition_id": identity,
        "forecast_payload_sha256": sha,
        "model_artifact_sha256": sha,
        "model_id": text,
        "season": text,
        "horizon": {"enum": ["LATEST", "7D", "3D", "24H", "6H", "1H", "15M"]},
        "data_quality_tier": {"const": "UNKNOWN"},
        **{
            key: clock
            for key in (
                "kickoff_at",
                "issued_at",
                "football_cutoff",
                "knowledge_cutoff",
                "outcome_known_at",
            )
        },
        **{key: {"type": "integer", "minimum": 0} for key in ("home_goals", "away_goals")},
    }
    metrics = {
        key: {"type": "number", "minimum": 0}
        for key in ("log_loss", "brier", "rps", "sharpness_entropy")
    }
    metrics["crps"] = {"type": ["number", "null"], "minimum": 0}
    properties = {
        "contract": {"const": "PostMatchEvaluation"},
        "policy_version": {"const": "postmatch-monitoring-v1"},
        "input_sha256": sha,
        "input": {
            "type": "object",
            "required": list(inputs),
            "additionalProperties": False,
            "properties": inputs,
        },
        "outcome": {"enum": ["HOME", "DRAW", "AWAY"]},
        "status": {"enum": ["COMPLETE", "PARTIAL", "UNSCORABLE"]},
        "probabilities": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 3,
                    "items": {"type": "number", "minimum": 0, "maximum": 1},
                },
            ]
        },
        "metrics": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "required": list(metrics),
                    "additionalProperties": False,
                    "properties": metrics,
                },
            ]
        },
        "reasons": {
            "type": "array",
            "uniqueItems": True,
            "items": {"enum": ["INVALID_FORECAST", "COUNT_DISTRIBUTION_UNAVAILABLE"]},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:matchforge:post-match-evaluation",
        "title": "PostMatchEvaluation",
        "type": "object",
        "required": list(properties),
        "additionalProperties": False,
        "properties": properties,
        "allOf": [
            {
                "if": {"properties": {"status": {"const": "UNSCORABLE"}}},
                "then": {
                    "properties": {
                        "metrics": {"type": "null"},
                        "probabilities": {"type": "null"},
                        "reasons": {"minItems": 1},
                    }
                },
                "else": {
                    "properties": {
                        "metrics": {"type": "object"},
                        "probabilities": {"type": "array"},
                    }
                },
            },
            {
                "if": {"properties": {"status": {"const": "COMPLETE"}}},
                "then": {
                    "properties": {
                        "metrics": {"properties": {"crps": {"type": "number"}}},
                        "reasons": {"maxItems": 0},
                    }
                },
            },
            {
                "if": {"properties": {"status": {"const": "PARTIAL"}}},
                "then": {
                    "properties": {
                        "metrics": {"properties": {"crps": {"type": "null"}}},
                        "reasons": {"minItems": 1},
                    }
                },
            },
        ],
    }


_VALIDATOR = Draft202012Validator(postmatch_schema(), format_checker=FormatChecker())


def validate_postmatch_record(record: dict[str, Any]) -> None:
    try:
        _VALIDATOR.validate(record)
    except ValidationError as error:
        raise ValueError("invalid post-match evaluation: " + error.message) from error
    if sha256_bytes(canonical_json_bytes(record["input"])) != record["input_sha256"]:
        raise ValueError("post-match evaluation input checksum mismatch")
