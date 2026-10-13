import io
from contextlib import contextmanager
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.request import Request

import pytest
from football.providers.base import (
    ProviderFetchError,
    UrllibHttpTransport,
    _ClosedRedirectBodyHandler,
    read_bounded,
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


@contextmanager
def server() -> Any:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_GET(self) -> None:
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
        yield f"http://127.0.0.1:{listener.server_port}"
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
