"""The ASGI application: a few fixed URLs of its own, then every other path is a route."""

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.responses import Response

from pdftunnel.access import HEADER, AccessDeniedError
from pdftunnel.serve import ListingMatch, file_response
from pdftunnel.web import api, health, pages
from pdftunnel.web.middleware import HeadersAndAccessLog
from pdftunnel.web.services import WebDeps

log = logging.getLogger(__name__)


def create_app(deps: WebDeps) -> FastAPI:
    app = FastAPI(
        title="pdftunnel",
        version=deps.version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    app.include_router(health.router(deps))
    app.include_router(api.router(deps))
    app.include_router(pages.router(deps))

    @app.api_route("/{_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve(request: Request, _path: str) -> Response:
        source = deps.source
        url_path = request.url.path
        match = source.routes.match(url_path)
        if match is None:
            if url_path == "/" and source.config.site.index:
                return pages.index_page(deps)
            return pages.not_found()
        if match.route.access and not await _access_granted(request, deps):
            return Response(
                "Forbidden\n",
                status_code=403,
                media_type="text/plain; charset=utf-8",
                headers={"cache-control": "private, no-store"},
            )
        if isinstance(match, ListingMatch):
            return pages.listing_page(deps, match.route, match.directory)
        # One open is one request without a Range: a PDF viewer then fetches pieces
        if request.method == "GET" and "range" not in request.headers:
            deps.counters.hit(match.route.path)
        return file_response(match, request, source.config.cache.max_age)

    app.add_middleware(HeadersAndAccessLog)
    return app


async def _access_granted(request: Request, deps: WebDeps) -> bool:
    verifier = deps.source.verifier
    if verifier is None:
        log.warning("%s needs Cloudflare Access but access: is not configured", request.url.path)
        return False
    try:
        identity = await asyncio.to_thread(verifier.verify, request.headers.get(HEADER))
    except AccessDeniedError as exc:
        log.warning("%s refused: %s", request.url.path, exc)
        return False
    log.debug("%s opened by %s", request.url.path, identity.email or identity.subject or "?")
    return True
