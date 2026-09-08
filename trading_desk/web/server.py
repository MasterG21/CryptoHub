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
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit

log = logging.getLogger("trading_desk.web")

from .runner import DeskRunner
from .security import SECURITY_HEADERS, TOKEN_QUERY, Guard, new_token
from .settings import read_settings, write_settings

STATIC_DIR = Path(__file__).parent / "static"
MAX_BODY_BYTES = 8192


class DeskHandler(BaseHTTPRequestHandler):
    runner: DeskRunner  # injected by make_server
    config_path: Path
    env_path: Path
    guard: Guard
    server_version = "TradingDesk"

    def log_message(self, fmt: str, *args: Any) -> None:
        """Silence per-request logging; the desk's own output is what matters."""

    # ---------------------------------------------------------------- routing

    # ----------------------------------------------------------------- guard

    def _query_token(self) -> Optional[str]:
        query = parse_qs(urlsplit(self.path).query)
        values = query.get(TOKEN_QUERY)
        return values[0] if values else None

    def _reject(self, reason: str) -> None:
        # Deliberately terse and identical for every failure: a caller that is
        # not allowed in learns nothing about which check stopped it.
        self._send_json({"error": "forbidden"}, status=403)
        log.warning("refused %s %s: %s", self.command, self.path.split("?", 1)[0], reason)

    def _authorise(self, mutating: bool) -> bool:
        """Run every applicable check. Any failure ends the request."""
        guard = self.guard
        problems = [
            guard.check_host(self.headers.get("Host")),
            guard.check_origin(self.headers.get("Origin"), self.headers.get("Referer")),
            guard.check_token(self.headers.get("X-Desk-Token"), self._query_token()),
        ]
        if mutating:
            problems.append(guard.check_content_type(self.headers.get("Content-Type")))
        reason = next((p for p in problems if p), None)
        if reason:
            self._reject(reason)
            return False
        return True

    # --------------------------------------------------------------- routing

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's interface
        route = self.path.split("?", 1)[0]
        if route in ("/", "/index.html"):
            # The page itself is unauthenticated so the browser can load it; it
            # holds no data, and every API call it makes is checked.
            if self.guard.check_host(self.headers.get("Host")):
                return self._reject("bad host on page request")
            return self._send_page()
        if not route.startswith("/api/"):
            return self._send_json({"error": "not found"}, status=404)
        if not self._authorise(mutating=False):
            return
        if route == "/api/state":
            return self._send_json(self.runner.snapshot())
        if route == "/api/health":
            return self._send_json({"ok": True, "ticks": self.runner.snapshot()["tick"]["count"]})
        if route == "/api/settings":
            return self._send_json(
                read_settings(self.runner.desk.config, self.config_path, self.env_path)
            )
        return self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route not in ("/api/control", "/api/settings"):
            return self._send_json({"error": "not found"}, status=404)
        if not self._authorise(mutating=True):
            return

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

        if route == "/api/settings":
            result = write_settings(
                payload,
                self.runner.desk.config,
                self.config_path,
                self.env_path,
                desk=self.runner.desk,
            )
            return self._send_json(result, status=200 if result.get("ok") else 400)

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
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
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
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


def make_server(
    runner: DeskRunner,
    host: str = "127.0.0.1",
    port: int = 8787,
    config_path: Optional[Path] = None,
    env_path: Optional[Path] = None,
    token: Optional[str] = None,
    require_token: bool = True,
) -> ThreadingHTTPServer:
    root = Path.cwd()
    guard = Guard(
        token=token or new_token(),
        port=port,
        host=host,
        require_token=require_token,
    )
    handler = type(
        "BoundDeskHandler",
        (DeskHandler,),
        {
            "runner": runner,
            "config_path": Path(config_path) if config_path else root / "desk.config.json",
            "env_path": Path(env_path) if env_path else root / ".env",
            "guard": guard,
        },
    )
    server = ThreadingHTTPServer((host, port), handler)
    server.guard = guard  # type: ignore[attr-defined]
    return server


def serve(
    runner: DeskRunner,
    host: str = "127.0.0.1",
    port: int = 8787,
    config_path: Optional[Path] = None,
    env_path: Optional[Path] = None,
    port_attempts: int = 8,
    token: Optional[str] = None,
    require_token: bool = True,
) -> ThreadingHTTPServer:
    """Start the desk thread and the HTTP server. Returns the running server.

    If the port is already taken — usually a previous run still holding it, or
    one that crashed without releasing it — the next few ports are tried rather
    than crashing. A dashboard on 8788 is fine; a traceback is not.
    """
    # One token for the run, whichever port it lands on.
    token = token or new_token()
    last_error: Optional[OSError] = None
    for candidate in range(port, port + max(1, port_attempts)):
        try:
            httpd = make_server(
                runner, host, candidate, config_path, env_path,
                token=token, require_token=require_token,
            )
        except OSError as exc:
            last_error = exc
            continue
        runner.start()
        threading.Thread(target=httpd.serve_forever, name="dashboard", daemon=True).start()
        return httpd
    raise OSError(
        f"could not bind any port between {port} and {port + port_attempts - 1} "
        f"on {host}: {last_error}"
    )
