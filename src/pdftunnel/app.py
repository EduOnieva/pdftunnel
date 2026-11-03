"""The service: the web server, the tunnel, the configuration watcher and the counters,
started together and stopped in order."""

import asyncio
import contextlib
import logging
import signal
from dataclasses import dataclass

import uvicorn

from pdftunnel import __version__
from pdftunnel.access import AccessVerifier
from pdftunnel.config import Config, ConfigError, ConfigWatcher, EnvSettings, load_config
from pdftunnel.paths import ConfigPaths
from pdftunnel.serve import Counters, RouteTable
from pdftunnel.tunnel import TunnelStatus, TunnelSupervisor
from pdftunnel.web import create_app

log = logging.getLogger(__name__)

COUNTERS_FLUSH_SECONDS = 60.0


class WebStartError(Exception):
    """The web server could not start, usually a port in use."""


class LiveConfig:
    """The configuration in use, swapped as a whole when the file changes."""

    def __init__(self, paths: ConfigPaths, config: Config) -> None:
        self._paths = paths
        self._config = config
        self._routes = RouteTable(config, paths.files_dir)
        self._verifier = self._build_verifier(config)
        self._error: str | None = None

    @staticmethod
    def _build_verifier(config: Config) -> AccessVerifier | None:
        return AccessVerifier(config.access) if config.access.is_configured else None

    def update(self, config: Config) -> None:
        if config.access != self._config.access:
            self._verifier = self._build_verifier(config)
        self._routes = RouteTable(config, self._paths.files_dir)
        self._config = config

    def set_error(self, message: str | None) -> None:
        self._error = message

    @property
    def config(self) -> Config:
        return self._config

    @property
    def routes(self) -> RouteTable:
        return self._routes

    @property
    def verifier(self) -> AccessVerifier | None:
        return self._verifier

    @property
    def config_error(self) -> str | None:
        return self._error


@dataclass
class Deps:
    source: LiveConfig
    tunnel: TunnelSupervisor
    counters: Counters
    version: str
    api_token: str | None
    paths: ConfigPaths

    @property
    def custom_css(self) -> str | None:
        return str(self.paths.custom_css) if self.paths.custom_css.is_file() else None


class _TunnelView:
    def __init__(self, supervisor: TunnelSupervisor) -> None:
        self._supervisor = supervisor

    @property
    def status(self) -> TunnelStatus:
        return self._supervisor.status


class Application:
    def __init__(self, env: EnvSettings, paths: ConfigPaths) -> None:
        self.env = env
        self.paths = paths

    async def run(self) -> int:
        env = self.env
        if env.tunnel_token is None:
            raise ConfigError(
                ["TUNNEL_TOKEN is not set: the token of the Cloudflare Tunnel is required"]
            )
        config = load_config(self.paths)
        if not config.routes:
            log.warning("No routes in %s: every request will be a 404", self.paths.config_file)
        live = LiveConfig(self.paths, config)
        watcher = ConfigWatcher(self.paths, config, on_change=live.update)
        counters = Counters(self.paths.counters_file)
        counters.load()
        supervisor = TunnelSupervisor(env.cloudflared_bin, env.tunnel_token)
        cloudflared_version = await supervisor.read_version()
        if env.api_token is None and not config.access.is_configured:
            log.info("Status API off: set API_TOKEN to enable /api/status")

        deps = Deps(
            source=live,
            tunnel=supervisor,
            counters=counters,
            version=__version__,
            api_token=env.api_token.get_secret_value() if env.api_token else None,
            paths=self.paths,
        )
        app = create_app(deps)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=env.web_bind,
                port=env.web_port,
                log_config=None,
                access_log=False,
                server_header=False,
                date_header=True,
                proxy_headers=False,
            )
        )
        log.info(
            "pdftunnel %s with cloudflared %s, serving %d route(s) on %s:%d, config %s",
            __version__,
            cloudflared_version or "(unknown version)",
            len(config.routes),
            env.web_bind,
            env.web_port,
            self.paths.config_file,
        )

        async def watch() -> None:
            while True:
                await asyncio.sleep(env.reload_seconds)
                watcher.poll()
                live.set_error(watcher.last_error)

        async def flush() -> None:
            while True:
                await asyncio.sleep(COUNTERS_FLUSH_SECONDS)
                counters.save()

        # uvicorn installs its own SIGTERM/SIGINT handlers while serving and re-raises the
        # signal afterwards with the previous handler restored. With these in place first, the
        # re-raised signal is ours and the shutdown below completes instead of killing us
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _note_signal, server, sig)

        tasks = [
            asyncio.create_task(coro, name=name)
            for name, coro in (
                ("tunnel", supervisor.run()),
                ("config-watch", watch()),
                ("counters", flush()),
            )
        ]
        try:
            await self._serve(server)
        finally:
            await supervisor.stop()
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            counters.save()
            log.info("Stopped")
        return 0

    @staticmethod
    async def _serve(server: uvicorn.Server) -> None:
        try:
            await server.serve()
        except SystemExit as exc:
            raise WebStartError(f"web server exited with {exc.code}") from exc


def _note_signal(server: uvicorn.Server, sig: int) -> None:
    log.debug("Signal %s", signal.Signals(sig).name)
    server.should_exit = True
