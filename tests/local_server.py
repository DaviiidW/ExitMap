"""Local HTTP server for integration tests: no real network is used (plan §6).

The test gives a ``handler(request) -> Reply`` function; every request received is also
kept in ``server.requests`` so the test can check what the client sent.
"""

import json
import socket
import threading
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: Mapping[str, str]
    body: bytes

    @property
    def form(self) -> dict[str, str]:
        return dict(urllib.parse.parse_qsl(self.body.decode("ascii")))

    def param(self, name: str) -> str | None:
        values = self.query.get(name)
        return values[0] if values else None


@dataclass
class Reply:
    status: int = 200
    data: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    raw: bytes | None = None

    def encode(self) -> bytes:
        if self.raw is not None:
            return self.raw
        return b"" if self.data is None else json.dumps(self.data).encode("utf-8")


class LocalServer:
    def __init__(self, handler: Callable[[Request], Reply]) -> None:
        self.handler = handler
        self.requests: list[Request] = []
        owner = self

        class _Handler(BaseHTTPRequestHandler):
            def _serve(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                request = Request(
                    method=self.command,
                    path=parsed.path,
                    query=urllib.parse.parse_qs(parsed.query),
                    headers=dict(self.headers),
                    body=self.rfile.read(length),
                )
                owner.requests.append(request)
                reply = owner.handler(request)
                body = reply.encode()
                self.send_response(reply.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                for name, value in reply.headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            do_GET = _serve
            do_POST = _serve

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> "LocalServer":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()


def closed_port_url() -> str:
    """URL of a local port where nothing is listening (simulates no network)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"
