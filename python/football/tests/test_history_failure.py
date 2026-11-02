from email.message import Message
from urllib.error import HTTPError

import psycopg
import pytest
from football.product.api_football import ApiFootballError, CapabilityStatus
from football.product.football_data_org import FootballDataOrgError
from football.product.history_work import classify_history_failure
from football.work.contracts import RetryClassification


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (psycopg.errors.SerializationFailure(), "RETRYABLE"),
        (psycopg.errors.DeadlockDetected(), "RETRYABLE"),
        (psycopg.errors.ConnectionFailure(), "RETRYABLE"),
        (psycopg.OperationalError("connection lost"), "RETRYABLE"),
        (TimeoutError(), "RETRYABLE"),
        (
            ApiFootballError("API-Football quota or cooldown active; request suppressed"),
            "RETRYABLE",
        ),
        (ApiFootballError("unclassified provider failure"), "NON_RETRYABLE"),
        (ApiFootballError("API-Football quota reservation is missing"), "NON_RETRYABLE"),
        (ApiFootballError("API_FOOTBALL_API_KEY is required"), "BLOCKED_EXTERNAL"),
        (
            FootballDataOrgError("FOOTBALL_DATA_DOT_ORG_API_TOKEN is required"),
            "BLOCKED_EXTERNAL",
        ),
        (
            FootballDataOrgError("football-data.org transport returned non-bytes data"),
            "NON_RETRYABLE",
        ),
        (
            psycopg.errors.RaiseException(
                "unresolved canonical fixture identity conflict at team/timestamp"
            ),
            "BLOCKED_EXTERNAL",
        ),
        (
            ApiFootballError(
                "plan restricted", capability_status=CapabilityStatus.PLAN_RESTRICTION
            ),
            "BLOCKED_EXTERNAL",
        ),
        (psycopg.errors.RaiseException("unknown integrity guard"), "NON_RETRYABLE"),
        (psycopg.errors.RaiseException(), "NON_RETRYABLE"),
        (psycopg.errors.UniqueViolation(), "NON_RETRYABLE"),
        (psycopg.errors.UndefinedFunction(), "NON_RETRYABLE"),
        (psycopg.errors.ProtocolViolation(), "NON_RETRYABLE"),
        (ApiFootballError("API-Football returned invalid JSON"), "NON_RETRYABLE"),
        (ApiFootballError("API-Football response must contain a list"), "NON_RETRYABLE"),
        (FileNotFoundError(), "NON_RETRYABLE"),
        (PermissionError(), "NON_RETRYABLE"),
        (ValueError(), "NON_RETRYABLE"),
    ],
)
def test_history_failure_classification(error: Exception, expected: str) -> None:
    assert classify_history_failure(error) == RetryClassification(expected)


@pytest.mark.parametrize(
    ("status", "expected"),
    [(403, "BLOCKED_EXTERNAL"), (429, "RETRYABLE"), (503, "RETRYABLE"), (404, "NON_RETRYABLE")],
)
def test_provider_http_cause_controls_retry(status: int, expected: str) -> None:
    error = ApiFootballError("API-Football request failed for /fixtures")
    error.__cause__ = HTTPError("https://example.invalid", status, "failed", Message(), None)
    assert classify_history_failure(error) == RetryClassification(expected)


@pytest.mark.parametrize("error_type", [ApiFootballError, FootballDataOrgError])
def test_provider_network_cause_remains_retryable(
    error_type: type[ApiFootballError | FootballDataOrgError],
) -> None:
    error = error_type("provider request failed")
    error.__cause__ = TimeoutError("network timed out")
    assert classify_history_failure(error) == RetryClassification.RETRYABLE


def test_quota_body_rejection_remains_retryable_with_a_deadline() -> None:
    from football.product.api_football import ApiFootballClient

    client = ApiFootballClient(
        "test", transport=lambda _url, _headers: b'{"errors":{"rateLimit":"reached"},"response":[]}'
    )
    with pytest.raises(ApiFootballError) as caught:
        client.competitions()
    assert caught.value.retry_after is not None
    assert classify_history_failure(caught.value) == RetryClassification.RETRYABLE
