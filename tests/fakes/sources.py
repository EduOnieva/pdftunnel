"""Fakes for the web layer's protocols."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from pdftunnel.access import AccessVerifier
from pdftunnel.config.schema import Config
from pdftunnel.paths import ConfigPaths
from pdftunnel.serve import Counters, RouteTable
from pdftunnel.tunnel import TunnelState, TunnelStatus


class FakeTunnel:
    def __init__(self, state: TunnelState = TunnelState.CONNECTED) -> None:
        self.state = state

    @property
    def status(self) -> TunnelStatus:
        connected = self.state is TunnelState.CONNECTED
        return TunnelStatus(
            state=self.state,
            connections=2 if connected else 0,
            restarts=0,
            last_exit_code=None,
            last_error=None,
            connected_since=datetime(2026, 1, 1, tzinfo=UTC) if connected else None,
        )


class FakeSource:
    def __init__(
        self, paths: ConfigPaths, config: Config, verifier: AccessVerifier | None = None
    ) -> None:
        self.paths = paths
        self.config = config
        self.routes = RouteTable(config, paths.files_dir)
        self.verifier = verifier
        self.config_error: str | None = None

    def reconfigure(self, config: Config) -> None:
        self.config = config
        self.routes = RouteTable(config, self.paths.files_dir)


@dataclass
class FakeDeps:
    source: FakeSource
    tunnel: FakeTunnel
    counters: Counters
    version: str = "test"
    api_token: str | None = None
    custom_css: str | None = None
    extra: dict[str, str] = field(default_factory=dict)
