from pdftunnel.tunnel import TunnelState


async def test_healthy(client):
    response = await client.get("/healthz")
    assert response.status_code == 200 and response.text == "ok\n"
    assert response.headers["cache-control"] == "no-store"


async def test_unhealthy_while_connecting(client, deps):
    deps.tunnel.state = TunnelState.CONNECTING
    response = await client.get("/healthz")
    assert response.status_code == 503 and response.text == "tunnel connecting\n"
