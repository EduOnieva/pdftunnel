"""Security headers on every response, and one access-log line per request."""

import logging
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from pdftunnel.serve import SECURITY_HEADERS

log = logging.getLogger("pdftunnel.access")

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

QUIET_PATHS = frozenset({"/healthz"})


def client_ip(scope: Scope) -> str:
    """The visitor's address as Cloudflare saw it, or the socket peer when not behind it."""
    for name, value in scope.get("headers", []):
        if name == b"cf-connecting-ip":
            return str(value.decode("latin-1"))
    client = scope.get("client")
    return str(client[0]) if client else "-"


class HeadersAndAccessLog:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        status = 0
        sent = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status, sent
            if message["type"] == "http.response.start":
                status = int(message["status"])
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                for name, value in SECURITY_HEADERS.items():
                    if name.encode() not in present:
                        headers.append((name.encode(), value.encode()))
                message["headers"] = headers
            elif message["type"] == "http.response.body":
                sent += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            level = logging.DEBUG if path in QUIET_PATHS else logging.INFO
            log.log(
                level,
                "%s %s %s %d %dB %.0fms",
                client_ip(scope),
                scope.get("method", "-"),
                path,
                status,
                sent,
                (time.monotonic() - started) * 1000,
            )
