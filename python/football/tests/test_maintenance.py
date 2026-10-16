from football.product.maintenance import quiescence_result, verified_health_probe


def test_socket_owner_blocks_even_when_process_name_is_unrecognized() -> None:
    report = quiescence_result(
        {"api_listeners": [{"pid": 42, "command": "renamed"}], "writer_processes": []},
        {"sessions": [], "active_jobs": {}},
    )
    assert report["R3_DATABASE_WRITERS_QUIESCENT"] is False
    assert report["status"] == "BLOCKED_ACTIVE_WRITER_UNCONTROLLED"


def test_idle_database_session_and_durable_lease_block_mutation() -> None:
    for database in (
        {"sessions": [{"pid": 12, "state": "idle"}], "active_jobs": {}},
        {"sessions": [], "active_jobs": {"product_sync_runs": [{"status": "RUNNING"}]}},
    ):
        assert not quiescence_result({}, database)["R3_DATABASE_WRITERS_QUIESCENT"]


def test_unavailable_signal_fails_closed() -> None:
    assert not quiescence_result({"errors": ["lsof failed"]}, {})["R3_DATABASE_WRITERS_QUIESCENT"]


def test_quiet_host_and_database_pass() -> None:
    report = quiescence_result(
        {"api_listeners": [], "writer_processes": [], "errors": []},
        {"sessions": [], "active_jobs": {"product_sync_runs": []}},
    )
    assert report["R3_DATABASE_WRITERS_QUIESCENT"] is True


def test_health_probe_requires_local_socket_no_transaction_and_no_sql() -> None:
    probe = {
        "application_name": "pg_isready",
        "client_addr": None,
        "xact_start": None,
        "empty_query": True,
    }
    assert verified_health_probe(probe)
    assert not verified_health_probe({**probe, "client_addr": "127.0.0.1"})
    assert not verified_health_probe({**probe, "empty_query": False})
    assert not verified_health_probe({**probe, "xact_start": "2026-10-14T03:00:00Z"})
    assert not verified_health_probe({**probe, "application_name": ""})
