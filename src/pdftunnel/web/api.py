"""`/api/status`: the tunnel, the configuration and every route with its request count.

It names the published files, so it is not public: the caller shows `API_TOKEN` as a bearer
token, or a Cloudflare Access login when Access is configured. Without a token configured
the endpoint does not exist.
"""

import asyncio
import hmac
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from pdftunnel.access import HEADER, AccessDeniedError
from pdftunnel.web.services import WebDeps

log = logging.getLogger(__name__)


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


async def authorised(request: Request, deps: WebDeps) -> bool:
    token = deps.api_token
    bearer = _bearer(request)
    if token is not None and bearer is not None:
        return hmac.compare_digest(bearer.encode(), token.encode())
    verifier = deps.source.verifier
    if verifier is not None and request.headers.get(HEADER):
        try:
            await asyncio.to_thread(verifier.verify, request.headers.get(HEADER))
        except AccessDeniedError as exc:
            log.warning("Status API refused: %s", exc)
            return False
        return True
    return False


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat(timespec="seconds")


def status_payload(deps: WebDeps) -> dict[str, Any]:
    source = deps.source
    tunnel = deps.tunnel.status
    counts = deps.counters.snapshot()
    routes: list[dict[str, Any]] = []
    for route in source.config.routes:
        entry: dict[str, Any] = {
            "path": route.path,
            "kind": "dir" if route.is_dir else "file",
            "target": route.dir if route.is_dir else route.file,
            "listed": route.listed,
            "access": route.access,
            "requests": counts.get(route.path, 0),
        }
        if route.is_dir:
            directory = source.routes.files_dir / (route.dir or "")
            entry["exists"] = directory.is_dir()
            entry["files"] = len(source.routes.listing(directory)) if directory.is_dir() else 0
        else:
            file = source.routes.file_for(route)
            entry["exists"] = file is not None
            if file is not None:
                stat = file.stat()
                entry["size"] = stat.st_size
                entry["modified"] = _iso(stat.st_mtime)
        routes.append(entry)
    return {
        "version": deps.version,
        "tunnel": {
            "cloudflared_version": tunnel.version,
            "state": tunnel.state.value,
            "connections": tunnel.connections,
            "restarts": tunnel.restarts,
            "last_exit_code": tunnel.last_exit_code,
            "last_error": tunnel.last_error,
            "connected_since": (
                tunnel.connected_since.isoformat(timespec="seconds")
                if tunnel.connected_since
                else None
            ),
        },
        "config": {
            "routes": len(source.config.routes),
            "index": source.config.site.index,
            "access_configured": source.config.access.is_configured,
            "error": source.config_error,
        },
        "routes": routes,
    }


def router(deps: WebDeps) -> APIRouter:
    api = APIRouter()

    @api.get("/api/status", include_in_schema=False)
    async def status(request: Request) -> JSONResponse:
        if deps.api_token is None and deps.source.verifier is None:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if not await authorised(request, deps):
            return JSONResponse(
                {"detail": "Unauthorized"},
                status_code=401,
                headers={"www-authenticate": "Bearer", "cache-control": "no-store"},
            )
        return JSONResponse(status_payload(deps), headers={"cache-control": "no-store"})

    return api
