"""The headers a published file goes out with."""

import mimetypes
from email.utils import parsedate_to_datetime
from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, Response

from pdftunnel.config.schema import Route
from pdftunnel.serve.routes import FileMatch

# Browser-neutral defaults, so a file saved as .pdf on a system without a mime database is
# still shown inline
mimetypes.add_type("application/pdf", ".pdf")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("font/woff2", ".woff2")

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
}
PAGE_CSP = "default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:"


def media_type_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def cache_control(route: Route, max_age: int) -> str:
    # A file behind Cloudflare Access must never sit in a shared cache, where the next
    # visitor would get it without a login
    if route.access:
        return "private, no-store"
    if max_age == 0:
        return "no-cache"
    return f"public, max-age={max_age}"


def _not_modified(request: Request, etag: str, last_modified: str) -> bool:
    """Whether the browser's copy is current. Starlette only evaluates If-Range, so the
    revalidation Cloudflare and browsers do with If-None-Match is answered here."""
    if "range" in request.headers:
        return False
    if_none_match = request.headers.get("if-none-match")
    if if_none_match is not None:
        tags = {tag.strip().removeprefix("W/") for tag in if_none_match.split(",")}
        return "*" in tags or etag in tags
    if_modified_since = request.headers.get("if-modified-since")
    if if_modified_since is not None:
        try:
            return parsedate_to_datetime(if_modified_since) >= parsedate_to_datetime(last_modified)
        except (TypeError, ValueError):
            return False
    return False


def file_response(match: FileMatch, request: Request, max_age: int) -> Response:
    # With the stat result given, the ETag and Last-Modified headers exist before sending
    response: Response = FileResponse(
        match.path,
        stat_result=match.path.stat(),
        media_type=media_type_for(match.path),
        filename=match.download_name,
        content_disposition_type=match.route.disposition.value,
    )
    etag = response.headers["etag"]
    last_modified = response.headers["last-modified"]
    if _not_modified(request, etag, last_modified):
        response = Response(status_code=304, headers={"etag": etag, "last-modified": last_modified})
    response.headers["cache-control"] = cache_control(match.route, max_age)
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response
