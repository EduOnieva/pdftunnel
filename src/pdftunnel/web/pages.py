"""The HTML pages: the optional index at `/`, folder listings, and the stylesheet."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape

from pdftunnel.config.schema import Route
from pdftunnel.serve import PAGE_CSP
from pdftunnel.web.services import WebDeps

TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"
ASSET_PREFIX = "/_pdftunnel"

_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"  # pragma: no cover - the loop returns at GB


def _entry(label: str, href: str, path: Path | None, *, access: bool = False) -> dict[str, Any]:
    entry: dict[str, Any] = {"label": label, "href": href, "access": access}
    if path is not None and path.is_file():
        stat = path.stat()
        entry["size"] = human_size(stat.st_size)
        entry["modified"] = datetime.fromtimestamp(stat.st_mtime, UTC).strftime("%Y-%m-%d")
    return entry


def render(template: str, deps: WebDeps, **context: Any) -> HTMLResponse:
    html = _env.get_template(template).render(
        site=deps.source.config.site,
        asset_prefix=ASSET_PREFIX,
        custom_css=deps.custom_css is not None,
        version=deps.version,
        **context,
    )
    return HTMLResponse(
        html,
        headers={
            "content-security-policy": PAGE_CSP,
            "x-frame-options": "DENY",
            "cache-control": "no-cache",
        },
    )


def index_page(deps: WebDeps) -> HTMLResponse:
    source = deps.source
    entries = []
    for route in source.config.listed_routes:
        if route.is_dir:
            entries.append(_entry(route.label, route.path, None, access=route.access))
        else:
            entries.append(
                _entry(route.label, route.path, source.routes.file_for(route), access=route.access)
            )
    return render("index.html", deps, title=source.config.site.title, entries=entries)


def listing_page(deps: WebDeps, route: Route, directory: Path) -> HTMLResponse:
    entries = [
        _entry(file.name, f"{route.path}{file.name}", file)
        for file in deps.source.routes.listing(directory)
    ]
    return render("listing.html", deps, title=route.label, entries=entries, route=route)


def not_found() -> Response:
    return Response("Not found\n", status_code=404, media_type="text/plain; charset=utf-8")


def router(deps: WebDeps) -> APIRouter:
    api = APIRouter()

    @api.get(f"{ASSET_PREFIX}/app.css", include_in_schema=False)
    async def app_css(request: Request) -> Response:
        return FileResponse(STATIC / "app.css", media_type="text/css")

    @api.get(f"{ASSET_PREFIX}/custom.css", include_in_schema=False)
    async def custom_css(request: Request) -> Response:
        if deps.custom_css is None:
            return not_found()
        return FileResponse(
            deps.custom_css, media_type="text/css", headers={"cache-control": "no-cache"}
        )

    return api
