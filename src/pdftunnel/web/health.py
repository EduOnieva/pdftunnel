"""`/healthz`: 200 while the tunnel is connected, 503 otherwise, a word of explanation."""

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from pdftunnel.tunnel import TunnelState
from pdftunnel.web.services import WebDeps


def router(deps: WebDeps) -> APIRouter:
    api = APIRouter()

    @api.get("/healthz", include_in_schema=False)
    async def healthz(request: Request) -> PlainTextResponse:
        status = deps.tunnel.status
        if status.state is TunnelState.CONNECTED:
            return PlainTextResponse("ok\n", headers={"cache-control": "no-store"})
        return PlainTextResponse(
            f"tunnel {status.state.value}\n", status_code=503, headers={"cache-control": "no-store"}
        )

    return api
