import io
from contextlib import contextmanager
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ssl import SSLCertVerificationError
from threading import Thread
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from football.product.probability_benchmarks import _http_get as benchmark_http_get
from football.providers.base import (
    ProviderFetchError,
    ProviderIncompleteBodyError,
    UrllibHttpTransport,
    _ClosedRedirectBodyHandler,
    read_bounded,
    retry_after_seconds,
)


def test_body_size_content_length_and_elapsed_work_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ProviderFetchError, match="exceeds"):
        read_bounded(io.BytesIO(b"12345"), max_bytes=4, timeout_seconds=1)
    response = io.BytesIO(b"small")
    response.headers = {"Content-Length": "100000"}  # type: ignore[attr-defined]
    with pytest.raises(ProviderFetchError, match="exceeds"):
        read_bounded(response, max_bytes=10, timeout_seconds=1)
    clocks = iter([0.0, 2.0])
    monkeypatch.setattr("football.providers.base.monotonic", lambda: next(clocks))
    with pytest.raises(ProviderFetchError, match="deadline"):
        read_bounded(io.BytesIO(b"valid"), max_bytes=10, timeout_seconds=1)


def test_redirect_closes_unbounded_body_without_reading_and_strips_cross_origin_credentials() -> (
    None
):
    class Body(io.BytesIO):
        def read(self, *_args: Any, **_kwargs: Any) -> bytes:
            raise AssertionError("redirect body must never be drained")

    class Opener:
        request: Request | None = None

        def open(self, request: Request, **_kwargs: object) -> bytes:
            self.request = request
            return b"redirected"

    original = Request(
        "https://origin.example/source",
        headers={
            "Authorization": "dummy",
            "x-apisports-key": "dummy",
            "Accept": "application/json",
        },
    )
    original.timeout = 1
    body = Body(b"oversized redirect body")
    headers = Message()
    headers["Location"] = "https://destination.example/next"
    handler = _ClosedRedirectBodyHandler()
    opener = Opener()
    handler.parent = opener  # type: ignore[assignment]
    assert handler.http_error_302(original, body, 302, "redirect", headers) == b"redirected"
    assert body.closed
    assert opener.request is not None
    assert opener.request.get_header("Authorization") is None
    assert opener.request.get_header("X-apisports-key") is None
    assert opener.request.get_header("Accept") == "application/json"


class _Root(str):
    """Server base URL that also exposes the request paths the server received."""

    __slots__ = ("requests",)
    requests: list[str]

    def __new__(cls, value: str, requests: list[str]) -> "_Root":
        root = super().__new__(cls, value)
        root.requests = requests
        return root


@contextmanager
def server() -> Any:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_GET(self) -> None:
            requests.append(self.path)
            if self.path == "/truncated" or (
                self.path == "/recovers" and requests.count("/recovers") == 1
            ):
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Length", "1000")
                self.end_headers()
                self.wfile.write(b"a,b\n1,2\n")
                return
            if self.path == "/declared":
                self.send_response(200)
                self.send_header("Content-Length", "100000")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            if self.path == "/chunked":
                self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                self.wfile.write(b"5\r\n12345\r\n0\r\n\r\n" if self.path == "/chunked" else b"[]")
            except (BrokenPipeError, ConnectionResetError):
                # Expected when a bounded client rejects a body and closes its socket.
                return

    listener = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=listener.serve_forever, daemon=True)
    thread.start()
    try:
        yield _Root(f"http://127.0.0.1:{listener.server_port}", requests)
    finally:
        listener.shutdown()
        listener.server_close()
        thread.join(timeout=1)


def test_real_valid_declared_and_chunked_downloads_are_bounded() -> None:
    with server() as root:
        transport = UrllibHttpTransport()
        assert transport.get(root + "/valid", timeout_seconds=1, max_bytes=4) == b"[]"
        for path in ["/declared", "/chunked"]:
            with pytest.raises(ProviderFetchError, match="exceeds"):
                transport.get(root + path, timeout_seconds=1, max_bytes=4)


def test_body_shorter_than_content_length_is_rejected() -> None:
    response = io.BytesIO(b"a,b\n1,2\n")
    response.headers = {"Content-Length": "1000"}  # type: ignore[attr-defined]
    with pytest.raises(ProviderIncompleteBodyError, match="8 of 1000 declared bytes"):
        read_bounded(response, max_bytes=10_000, timeout_seconds=1)

    complete = io.BytesIO(b"a,b\n1,2\n")
    complete.headers = {"Content-Length": "8"}  # type: ignore[attr-defined]
    assert read_bounded(complete, max_bytes=10_000, timeout_seconds=1) == b"a,b\n1,2\n"

    chunked = io.BytesIO(b"12345")
    chunked.headers = {  # type: ignore[attr-defined]
        "Content-Length": "1000",
        "Transfer-Encoding": "chunked",
    }
    assert read_bounded(chunked, max_bytes=10_000, timeout_seconds=1) == b"12345"


def test_truncated_download_is_retried_then_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []
    monkeypatch.setattr("football.providers.base.sleep", delays.append)
    with server() as root:
        with pytest.raises(
            ProviderFetchError,
            match=r"attempt 4/4; exception=ProviderIncompleteBodyError; http_status=none",
        ):
            UrllibHttpTransport().get(root + "/truncated", timeout_seconds=1, max_bytes=10_000)
        assert root.requests == ["/truncated"] * 4
        assert delays == [1.0, 2.0, 4.0]

        assert (
            UrllibHttpTransport().get(root + "/recovers", timeout_seconds=1, max_bytes=10_000)
            == b"[]"
        )
        assert root.requests.count("/recovers") == 2


def test_benchmark_fetch_uses_the_bounded_reader() -> None:
    with server() as root:
        assert benchmark_http_get(root + "/valid", {}) == b"[]"
        with pytest.raises(ProviderIncompleteBodyError):
            benchmark_http_get(root + "/truncated", {})


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("7", 7.0),
        ("0", 0.0),
        ("-3", 0.0),
        ("999", 30.0),
        ("nan", None),
        ("Wed, 21 Oct 2026 07:28:00 GMT", None),
    ],
)
def test_retry_after_seconds_is_parsed_and_capped(
    header: str | None, expected: float | None
) -> None:
    assert retry_after_seconds(header) == expected


@pytest.mark.parametrize(("header", "expected"), [("7", [7.0]), ("soon", [1.0])])
def test_transport_waits_for_retry_after_on_a_retryable_status(
    monkeypatch: pytest.MonkeyPatch, header: str, expected: list[float]
) -> None:
    attempts = 0
    delays: list[float] = []

    class Response(io.BytesIO):
        headers = Message()
        status = 200

    def fetch(*_args: object, **_kwargs: object) -> Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            headers = Message()
            headers["Retry-After"] = header
            raise HTTPError("https://example.test/data.json", 429, "slow down", headers, None)
        return Response(b"[]")

    monkeypatch.setattr("football.providers.base.open_bounded", fetch)
    monkeypatch.setattr("football.providers.base.sleep", delays.append)

    assert (
        UrllibHttpTransport().get("https://example.test/data.json", timeout_seconds=1, max_bytes=4)
        == b"[]"
    )
    assert delays == expected


def test_transport_does_not_retry_a_certificate_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    delays: list[float] = []

    def untrusted(*_args: object, **_kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        raise URLError(SSLCertVerificationError("certificate verify failed"))

    monkeypatch.setattr("football.providers.base.open_bounded", untrusted)
    monkeypatch.setattr("football.providers.base.sleep", delays.append)

    with pytest.raises(ProviderFetchError, match="attempt 1/4; exception=URLError"):
        UrllibHttpTransport().get("https://example.test/data.json", timeout_seconds=1, max_bytes=4)
    assert attempts == 1
    assert delays == []
