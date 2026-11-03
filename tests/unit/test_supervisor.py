import asyncio
import logging
from pathlib import Path

import pytest
from pydantic import SecretStr

from pdftunnel.tunnel import TunnelState, TunnelSupervisor
from tests.conftest import FAKES_BIN

BIN = FAKES_BIN / "cloudflared"


class Sleeps:
    """Records the backoff delays and returns at once."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)
        await asyncio.sleep(0)


@pytest.fixture
def record(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    log = tmp_path / "calls.log"
    monkeypatch.setenv("FAKE_CLOUDFLARED_LOG", str(log))
    return log


async def test_connects_and_stops(record, monkeypatch):
    monkeypatch.setenv("FAKE_CLOUDFLARED_MODE", "connect")
    supervisor = TunnelSupervisor(BIN, SecretStr("tok-123"))
    task = asyncio.create_task(supervisor.run())
    async with asyncio.timeout(5):
        await supervisor.wait_connected()
    await asyncio.sleep(0.2)  # the second connection line
    status = supervisor.status
    assert status.state == TunnelState.CONNECTED and status.connections == 2
    assert status.connected_since is not None and supervisor.healthy
    await supervisor.stop()
    async with asyncio.timeout(5):
        await task
    assert supervisor.status.state == TunnelState.STOPPED
    calls = record.read_text()
    assert "argv: tunnel --no-autoupdate run" in calls
    assert "token: tok-123" in calls  # via the environment, never on the command line


async def test_restarts_with_backoff_after_exit(record, monkeypatch, caplog):
    monkeypatch.setenv("FAKE_CLOUDFLARED_MODE", "exit")
    sleeps = Sleeps()
    supervisor = TunnelSupervisor(BIN, SecretStr("bad"), sleep=sleeps, backoff=(0.01, 0.02))
    with caplog.at_level(logging.WARNING):
        task = asyncio.create_task(supervisor.run())
        async with asyncio.timeout(10):
            while supervisor.status.restarts < 3:
                await asyncio.sleep(0.05)
        await supervisor.stop()
        await task
    status = supervisor.status
    assert status.last_exit_code == 1
    assert status.last_error is not None and "not valid" in status.last_error
    assert sleeps.delays[:3] == [0.01, 0.02, 0.02]
    assert "restarting in" in caplog.text


async def test_crash_after_connect_goes_down_then_back(record, monkeypatch):
    monkeypatch.setenv("FAKE_CLOUDFLARED_MODE", "crash-after-connect")
    sleeps = Sleeps()
    supervisor = TunnelSupervisor(BIN, SecretStr("x"), sleep=sleeps, backoff=(0.01,))
    task = asyncio.create_task(supervisor.run())
    async with asyncio.timeout(5):
        await supervisor.wait_connected()
    async with asyncio.timeout(5):
        while supervisor.status.restarts < 1:
            await asyncio.sleep(0.05)
    assert supervisor.status.last_exit_code == 2
    await supervisor.stop()
    await task


async def test_missing_binary(tmp_path, caplog):
    sleeps = Sleeps()
    supervisor = TunnelSupervisor(tmp_path / "nope", SecretStr("x"), sleep=sleeps, backoff=(0.01,))
    with caplog.at_level(logging.ERROR):
        task = asyncio.create_task(supervisor.run())
        async with asyncio.timeout(5):
            while supervisor.status.restarts < 2:
                await asyncio.sleep(0.02)
        await supervisor.stop()
        await task
    assert supervisor.status.last_exit_code == -1
    assert "cannot start" in caplog.text


async def test_stop_before_start_and_twice():
    supervisor = TunnelSupervisor(BIN, SecretStr("x"))
    await supervisor.stop()
    await supervisor.stop()
    assert supervisor.status.state is TunnelState.STARTING


async def test_stop_kills_a_process_that_ignores_sigterm(tmp_path, monkeypatch):
    stubborn = tmp_path / "cloudflared"
    stubborn.write_text(
        "#!/bin/sh\ntrap '' TERM\necho 'INF Registered tunnel connection'\n"
        "while :; do sleep 0.1; done\n"
    )
    stubborn.chmod(0o755)
    monkeypatch.setattr("pdftunnel.tunnel.supervisor.STOP_GRACE_SECONDS", 0.3)
    supervisor = TunnelSupervisor(stubborn, SecretStr("x"))
    task = asyncio.create_task(supervisor.run())
    async with asyncio.timeout(5):
        await supervisor.wait_connected()
    async with asyncio.timeout(5):
        await supervisor.stop()
        await task
    assert supervisor.status.state is TunnelState.STOPPED


def test_line_parsing_levels_and_unregister(caplog):
    supervisor = TunnelSupervisor(BIN, SecretStr("x"))
    handle = supervisor._handle_line
    with caplog.at_level(logging.DEBUG, logger="cloudflared"):
        handle("2026 INF Registered tunnel connection connIndex=0")
        handle("2026 INF Registered tunnel connection connIndex=1")
        handle("2026 DBG something quiet")
        handle("2026 ERR something bad")
        handle("2026 INF Unregistered tunnel connection connIndex=1")
        assert supervisor.status.state is TunnelState.CONNECTED
        handle("2026 INF Unregistered tunnel connection connIndex=0")
    status = supervisor.status
    assert status.state is TunnelState.CONNECTING and status.connections == 0
    assert status.last_error == "2026 ERR something bad"
    levels = [r.levelname for r in caplog.records if r.name == "cloudflared"]
    assert "DEBUG" in levels and "ERROR" in levels
