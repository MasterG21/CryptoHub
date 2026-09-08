"""Access control for the local dashboard.

The dashboard can flatten a book, change risk settings and store wallet keys, so
"it only listens on localhost" is not by itself a security model. Localhost is
reachable by every other program on the machine, and — the part that actually
bites — by every website loaded in your browser.

A demonstrated attack this defends against: a page on any other origin sends

    fetch("http://127.0.0.1:8787/api/control", {
      method: "POST", mode: "no-cors",
      headers: {"Content-Type": "text/plain"},
      body: '{"action":"panic"}'})

``text/plain`` makes that a CORS "simple request", so the browser sends it with
no preflight. The attacker cannot read the reply, but the action still runs —
enough to sell your entire book from a tab you did not know was open.

Four independent checks, because each covers a case the others miss:

``token``        a secret minted per run, required on every API call. Stops
                 other local programs, which have no way to learn it.
``origin``       state-changing calls must come from the dashboard's own origin.
                 Stops the cross-site attack above even without a token.
``host``         the Host header must name a loopback address. Stops DNS
                 rebinding, where an attacker's domain re-resolves to 127.0.0.1
                 and the browser then treats their page as same-origin.
``content-type`` POSTs must be ``application/json``, which is not a simple
                 request and so cannot be sent cross-origin without a preflight.
"""
from __future__ import annotations

import hmac
import ipaddress
import secrets
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

TOKEN_HEADER = "X-Desk-Token"
TOKEN_QUERY = "t"
TOKEN_BYTES = 32


def new_token() -> str:
    """A fresh secret for this run. Never written to disk."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def _is_loopback(hostname: str) -> bool:
    if hostname in ("localhost", "localhost.localdomain", ""):
        return True
    try:
        return ipaddress.ip_address(hostname.strip("[]")).is_loopback
    except ValueError:
        return False


@dataclass
class Guard:
    """Decides whether one request may proceed."""

    token: str
    port: int
    host: str = "127.0.0.1"
    require_token: bool = True

    @property
    def allowed_origins(self) -> set[str]:
        """Origins the dashboard may legitimately be loaded from."""
        origins = set()
        for name in ("127.0.0.1", "localhost", "[::1]"):
            origins.add(f"http://{name}:{self.port}")
        if not _is_loopback(self.host):
            # Bound to a real interface on purpose; that address is legitimate too.
            origins.add(f"http://{self.host}:{self.port}")
        return origins

    # ---------------------------------------------------------------- checks

    def check_host(self, host_header: Optional[str]) -> Optional[str]:
        """Reject a Host that is not this dashboard, defeating DNS rebinding."""
        if not host_header:
            return "missing Host header"
        hostname = host_header.rsplit(":", 1)[0] if ":" in host_header else host_header
        if hostname.startswith("[") and "]" in host_header:
            hostname = host_header[: host_header.index("]") + 1]
        if _is_loopback(hostname) or hostname == self.host:
            return None
        return f"unexpected Host header {host_header!r}"

    def check_origin(self, origin: Optional[str], referer: Optional[str]) -> Optional[str]:
        """Require a same-origin caller for anything that changes state.

        A missing Origin is allowed: command-line tools such as curl send none,
        and browsers always attach one to cross-origin requests — so absence
        cannot be a browser attack, while a *wrong* value certainly is.
        """
        if origin is None and referer is None:
            return None
        candidate = origin
        if candidate in (None, "null") and referer:
            parts = urlsplit(referer)
            candidate = f"{parts.scheme}://{parts.netloc}" if parts.netloc else None
        if candidate is None:
            return "request carried an opaque origin"
        if candidate in self.allowed_origins:
            return None
        return f"cross-origin request from {candidate}"

    def check_token(self, header_value: Optional[str], query_value: Optional[str]) -> Optional[str]:
        if not self.require_token:
            return None
        supplied = header_value or query_value or ""
        # Constant-time, so a wrong token cannot be recovered by timing.
        if hmac.compare_digest(supplied, self.token):
            return None
        return "missing or invalid access token"

    def check_content_type(self, content_type: Optional[str]) -> Optional[str]:
        """Require JSON, which browsers cannot send cross-origin unpreflighted."""
        base = (content_type or "").split(";", 1)[0].strip().lower()
        if base == "application/json":
            return None
        return f"expected application/json, got {base or 'nothing'}"

    # ------------------------------------------------------------------ urls

    def dashboard_url(self) -> str:
        display_host = self.host if self.host != "0.0.0.0" else "127.0.0.1"
        base = f"http://{display_host}:{self.port}/"
        return f"{base}?{TOKEN_QUERY}={self.token}" if self.require_token else base


SECURITY_HEADERS = {
    # The dashboard is never legitimately embedded, so refuse framing outright.
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    # Keep the token out of the Referer of any outbound navigation.
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store, max-age=0",
}
