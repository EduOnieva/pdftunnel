from tests.fakes.access import FakeKeys


async def test_off_without_token_or_access(client, deps):
    deps.api_token = None
    deps.source.verifier = None
    assert (await client.get("/api/status")).status_code == 404


async def test_unauthorised(client, deps):
    deps.api_token = "right"
    response = await client.get("/api/status")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert (
        await client.get("/api/status", headers={"Authorization": "Bearer wrong"})
    ).status_code == 401
    assert (
        await client.get("/api/status", headers={"Authorization": "Basic cmlnaHQ="})
    ).status_code == 401


async def test_status_with_bearer(client, deps):
    deps.api_token = "right"
    await client.get("/")
    response = await client.get("/api/status", headers={"Authorization": "Bearer right"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["version"] == "test"
    assert body["tunnel"]["state"] == "connected" and body["tunnel"]["connections"] == 2
    assert body["tunnel"]["cloudflared_version"] == "2026.10.7"
    assert body["tunnel"]["connected_since"] == "2026-01-01T00:00:00+00:00"
    assert body["config"] == {"routes": 7, "index": True, "access_configured": True, "error": None}
    routes = {r["path"]: r for r in body["routes"]}
    root = routes["/"]
    assert root["kind"] == "file" and root["target"] == "catalogue.pdf" and root["exists"]
    assert root["requests"] == 1 and root["size"] > 0 and root["modified"].endswith("+00:00")
    assert routes["/missing"]["exists"] is False and "size" not in routes["/missing"]
    docs = routes["/docs/"]
    assert docs["kind"] == "dir" and docs["exists"] and docs["files"] == 3
    assert routes["/private"]["access"] is True
    assert routes["/secret-k7f3q9x2"]["listed"] is False


async def test_status_with_access_login(client, deps, keys, caplog):
    deps.api_token = None
    ok = await client.get("/api/status", headers={"Cf-Access-Jwt-Assertion": keys.token()})
    assert ok.status_code == 200
    bad = await client.get("/api/status", headers={"Cf-Access-Jwt-Assertion": FakeKeys().token()})
    assert bad.status_code == 401
    assert "Status API refused" in caplog.text
    assert (await client.get("/api/status")).status_code == 401


async def test_status_reports_config_error_and_missing_dir(client, deps):
    from pdftunnel.config.schema import Route
    from tests.web.conftest import make_config

    deps.api_token = "t"
    deps.source.config_error = "config.yaml: routes[0].path: must start with /"
    deps.source.config = make_config(routes=[Route(path="/x/", dir="nowhere")])
    body = (await client.get("/api/status", headers={"Authorization": "Bearer t"})).json()
    assert body["config"]["error"].endswith("must start with /")
    assert body["routes"][0] == {
        "path": "/x/",
        "kind": "dir",
        "target": "nowhere",
        "listed": True,
        "access": False,
        "requests": 0,
        "exists": False,
        "files": 0,
    }
