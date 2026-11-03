"""cloudflared as a child process: started, watched, restarted, stopped.

The token reaches cloudflared through its `TUNNEL_TOKEN` environment variable, never on the
command line where `ps` would show it. Its log lines are relayed to ours, and the ones that
announce a connection to Cloudflare's edge are what the health check is based on.
"""

import asyncio
import contextlib
import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import SecretStr

log = logging.getLogger("cloudflared")

_REGISTERED = re.compile(r"Registered tunnel connection")
_UNREGISTERED = re.compile(r"Unregistered tunnel connection")
_LEVEL = re.compile(r"\b(ERR|WRN|INF|DBG)\b")
STOP_GRACE_SECONDS = 10.0
BACKOFF_SECONDS = (1.0, 2.0, 5.0, 10.0, 30.0)


class TunnelState(StrEnum):
    STARTING = "starting"  # the process is not up yet
    CONNECTING = "connecting"  # up, no connection to the edge registered yet
    CONNECTED = "connected"  # at least one connection registered
    DOWN = "down"  # the process exited; a restart is scheduled
    STOPPED = "stopped"  # we stopped it


@dataclass(frozen=True)
class TunnelStatus:
    state: TunnelState
    connections: int
    restarts: int
    last_exit_code: int | None
    last_error: str | None
    connected_since: datetime | None


SleepFn = Callable[[float], Awaitable[None]]


class TunnelSupervisor:
    def __init__(
        self,
        binary: Path,
        token: SecretStr,
        *,
        sleep: SleepFn | None = None,
        backoff: tuple[float, ...] = BACKOFF_SECONDS,
    ) -> None:
        self._binary = binary
        self._token = token
        self._sleep: SleepFn = sleep or asyncio.sleep
        self._backoff = backoff
        self._process: asyncio.subprocess.Process | None = None
        self._state = TunnelState.STARTING
        self._connections = 0
        self._restarts = 0
        self._last_exit_code: int | None = None
        self._last_error: str | None = None
        self._connected_since: datetime | None = None
        self._stop = asyncio.Event()
        self._connected_event = asyncio.Event()

    @property
    def status(self) -> TunnelStatus:
        return TunnelStatus(
            state=self._state,
            connections=self._connections,
            restarts=self._restarts,
            last_exit_code=self._last_exit_code,
            last_error=self._last_error,
            connected_since=self._connected_since,
        )

    @property
    def healthy(self) -> bool:
        return self._state is TunnelState.CONNECTED

    async def wait_connected(self) -> None:
        """Returns once a connection has registered; wrap it in `asyncio.timeout`."""
        await self._connected_event.wait()

    def _set_state(self, state: TunnelState) -> None:
        if state is not self._state:
            log.info("Tunnel %s", state.value)
        self._state = state

    def _handle_line(self, line: str) -> None:
        match = _LEVEL.search(line)
        level = {"ERR": logging.ERROR, "WRN": logging.WARNING, "DBG": logging.DEBUG}.get(
            match.group(1) if match else "INF", logging.INFO
        )
        log.log(level, "%s", line)
        if level >= logging.ERROR:
            self._last_error = line
        if _REGISTERED.search(line):
            self._connections += 1
            if self._connected_since is None:
                self._connected_since = datetime.now(UTC)
            self._set_state(TunnelState.CONNECTED)
            self._connected_event.set()
        elif _UNREGISTERED.search(line):
            self._connections = max(0, self._connections - 1)
            if self._connections == 0:
                self._connected_since = None
                self._set_state(TunnelState.CONNECTING)

    async def _run_once(self) -> int:
        env = {**os.environ, "TUNNEL_TOKEN": self._token.get_secret_value()}
        # The argv is fixed and the binary path comes from the operator's environment
        process = await asyncio.create_subprocess_exec(
            str(self._binary),
            "tunnel",
            "--no-autoupdate",
            "run",
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._process = process
        self._connections = 0
        self._connected_since = None
        self._set_state(TunnelState.CONNECTING)
        assert process.stdout is not None  # PIPE above guarantees it
        while True:
            raw = await process.stdout.readline()
            if not raw:
                break
            self._handle_line(raw.decode("utf-8", "replace").rstrip())
        code = await process.wait()
        self._process = None
        return code

    async def run(self) -> None:
        """Keep cloudflared running until `stop()`."""
        attempt = 0
        while not self._stop.is_set():
            try:
                code = await self._run_once()
            except OSError as exc:
                code = -1
                self._last_error = f"cannot start {self._binary}: {exc.strerror or exc}"
                log.error("%s", self._last_error)
            self._last_exit_code = code
            self._connections = 0
            self._connected_since = None
            if self._stop.is_set():
                break
            delay = self._backoff[min(attempt, len(self._backoff) - 1)]
            attempt += 1
            self._restarts += 1
            self._set_state(TunnelState.DOWN)
            log.warning("cloudflared exited with code %s; restarting in %.0fs", code, delay)
            await self._sleep(delay)
        self._set_state(TunnelState.STOPPED)

    async def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process is None or process.returncode is not None:
            return
        log.info("Stopping cloudflared")
        with contextlib.suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), STOP_GRACE_SECONDS)
        except TimeoutError:
            log.warning("cloudflared ignored SIGTERM for %.0fs; killing it", STOP_GRACE_SECONDS)
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
