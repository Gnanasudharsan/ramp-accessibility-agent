"""A tiny threaded static HTTP server for serving benchmark pages locally and deterministically."""

from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import TracebackType


class _QuietHandler(SimpleHTTPRequestHandler):
    log: list[tuple[str, str]]

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        self.log.append(("GET", self.path))
        super().do_GET()

    def do_POST(self) -> None:  # recorded so tests can prove nothing was ever posted
        self.log.append(("POST", self.path))
        self.send_response(204)
        self.end_headers()


class StaticServer:
    """``with StaticServer(root) as s: s.url`` serves ``root`` on 127.0.0.1 at a free port."""

    def __init__(self, root: Path) -> None:
        self.requests: list[tuple[str, str]] = []
        handler = type("Handler", (_QuietHandler,), {"log": self.requests})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(handler, directory=str(root)))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host!s}:{port}"

    def __enter__(self) -> StaticServer:
        self.thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
