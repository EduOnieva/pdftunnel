import asyncio
import json
import logging
import os
import signal
import socket

import httpx
import pytest

from pdftunnel.app import Application, LiveConfig
from pdftunnel.config import EnvSettings, parse_config_text
from pdftunnel.config.schema import AccessConfig, Config, Route
from tests.conftest import FAKES_BIN

pytestmark = pytest.mark.usefixtures("clean_env")


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port: int = sock.getsockname()[1]
    sock.close()
    return port


WITH_ACCESS = Config(
    routes=[Route(path="/a", file="catalogue.pdf", access=True)],
    access=AccessConfig(team_domain="t", audience="aud"),
)


class TestLiveConfig:
    def test_without_access(self, paths):
        live = LiveConfig(paths, Config(routes=[Route(path="/", file="catalogue.pdf")]))
        assert live.verifier is None and live.routes.match("/") is not None
        assert live.config_error is None
        live.set_error("broken")
        assert live.config_error == "broken"

    def test_update_swaps_routes_and_builds_a_verifier(self, paths):
        live = LiveConfig(paths, Config(routes=[Route(path="/", file="catalogue.pdf")]))
        live.update(WITH_ACCESS)
        assert live.verifier is not None and live.routes.match("/") is None

    def test_same_access_config_keeps_the_verifier(self, paths):
        live = LiveConfig(paths, WITH_ACCESS)
        verifier = live.verifier
        live.update(WITH_ACCESS.model_copy(update={"routes": []}))
        assert live.verifier is verifier  # and with it the cached keys

    def test_dropping_access_drops_the_verifier(self, paths):
        live = LiveConfig(paths, WITH_ACCESS)
        live.update(Config())
        assert live.verifier is None


async def test_run_serves_reloads_and_stops_on_sigterm(paths, monkeypatch, caplog):
    port = free_port()
    monkeypatch.setenv("CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("TUNNEL_TOKEN", "x")
    monkeypatch.setenv("API_TOKEN", "api")
    monkeypatch.setenv("WEB_PORT", str(port))
    monkeypatch.setenv("RELOAD_SECONDS", "0.05")
    monkeypatch.setenv("CLOUDFLARED_BIN", str(FAKES_BIN / "cloudflared"))
    monkeypatch.setenv("FAKE_CLOUDFLARED_MODE", "connect")
    monkeypatch.setattr("pdftunnel.app.COUNTERS_FLUSH_SECONDS", 0.05)
    paths.config_file.write_text("routes:\n  - path: /\n    file: catalogue.pdf\n")
    caplog.set_level(logging.INFO)

    task = asyncio.create_task(Application(EnvSettings(), paths).run())
    base = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient(base_url=base) as client:
        async with asyncio.timeout(10):
            while True:
                try:
                    if (await client.get("/healthz")).status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.05)
        assert (await client.get("/")).headers["content-type"] == "application/pdf"
        assert (await client.get("/docs/a.pdf")).status_code == 404

        # Hot reload: a new route appears, a broken edit is ignored
        paths.config_file.write_text(
            "routes:\n  - path: /\n    file: catalogue.pdf\n  - path: /docs/\n    dir: docs\n"
        )
        async with asyncio.timeout(5):
            while (await client.get("/docs/a.pdf")).status_code != 200:
                await asyncio.sleep(0.05)
        paths.config_file.write_text("routes: [{path: nope}]\n")
        async with asyncio.timeout(5):
            while "not reloaded" not in caplog.text:
                await asyncio.sleep(0.05)
        assert (await client.get("/docs/a.pdf")).status_code == 200
        status = (await client.get("/api/status", headers={"Authorization": "Bearer api"})).json()
        assert status["config"]["error"] is not None and status["config"]["routes"] == 2
        async with asyncio.timeout(5):
            while not paths.counters_file.exists():
                await asyncio.sleep(0.05)

    os.kill(os.getpid(), signal.SIGTERM)
    async with asyncio.timeout(10):
        assert await task == 0
    assert "Stopping cloudflared" in caplog.text and "Stopped" in caplog.text
    assert "with cloudflared 2026.10.7" in caplog.text
    assert status["tunnel"]["cloudflared_version"] == "2026.10.7"
    assert json.loads(paths.counters_file.read_text()) == {"/": 1, "/docs/": 2}


async def test_run_warns_without_routes(paths, monkeypatch, caplog):
    monkeypatch.setenv("CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("TUNNEL_TOKEN", "x")
    monkeypatch.setenv("WEB_PORT", str(free_port()))
    monkeypatch.setenv("CLOUDFLARED_BIN", str(FAKES_BIN / "cloudflared"))
    caplog.set_level(logging.INFO)
    task = asyncio.create_task(Application(EnvSettings(), paths).run())
    async with asyncio.timeout(10):
        while "Uvicorn running" not in caplog.text:
            await asyncio.sleep(0.05)
    os.kill(os.getpid(), signal.SIGTERM)
    async with asyncio.timeout(10):
        await task
    assert "No routes" in caplog.text and "Status API off" in caplog.text


def test_parse_helper_is_exported():
    assert parse_config_text("") == Config()
