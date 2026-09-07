"""Local HTTP server for the desk dashboard.

Standard library only — no Flask, no FastAPI. The dashboard is a read-mostly
JSON API plus one static page, which does not justify a dependency on a running
trading system.

**Binds to 127.0.0.1 by default and there is no authentication.** Anyone who can
reach this port can flatten your book. Do not expose it to the internet; if you
need it remotely, tunnel over SSH.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .runner import DeskRunner

STATIC_DIR = Path(__file__).parent / "static"
MAX_BODY_BYTES = 4096


class DeskHandler(BaseHTTPRequestHandler):
    runner: DeskRunner  # injected by make_server
    server_version = "TradingDesk"

    def log_message(self, fmt: str, *args: Any) -> None:
        """Silence per-request logging; the desk's own output is what matters."""

    # ---------------------------------------------------------------- routing

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's interface
        route = self.path.split("?", 1)[0]
        if route in ("/", "/index.html"):
            return self._send_page()
        if route == "/api/state":
            return self._send_json(self.runner.snapshot())
        if route == "/api/health":
            return self._send_json({"ok": True, "ticks": self.runner.snapshot()["tick"]["count"]})
        return self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route != "/api/control":
            return self._send_json({"error": "not found"}, status=404)

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._send_json({"error": "bad content length"}, status=400)
        if length > MAX_BODY_BYTES:
            return self._send_json({"error": "body too large"}, status=413)

        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._send_json({"error": "bad JSON"}, status=400)

        action = payload.get("action")
        actions = {
            "pause": self.runner.pause,
            "resume": self.runner.resume,
            "panic": self.runner.panic,
        }
        handler = actions.get(action)
        if handler is None:
            return self._send_json(
                {"error": f"unknown action {action!r}", "allowed": sorted(actions)}, status=400
            )
        return self._send_json({"status": handler()})

    # --------------------------------------------------------------- replies

    def _send_page(self) -> None:
        try:
            body = (STATIC_DIR / "index.html").read_bytes()
        except OSError:
            return self._send_json({"error": "dashboard asset missing"}, status=500)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # The page is entirely self-contained; refuse anything it did not ship with.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "connect-src 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(runner: DeskRunner, host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    handler = type("BoundDeskHandler", (DeskHandler,), {"runner": runner})
    return ThreadingHTTPServer((host, port), handler)


def serve(runner: DeskRunner, host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    """Start the desk thread and the HTTP server. Returns the running server."""
    runner.start()
    httpd = make_server(runner, host, port)
    threading.Thread(target=httpd.serve_forever, name="dashboard", daemon=True).start()
    return httpd
