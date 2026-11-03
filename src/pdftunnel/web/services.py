"""What the web layer needs from the rest of the application, as protocols."""

from typing import Protocol

from pdftunnel.access import AccessVerifier
from pdftunnel.config.schema import Config
from pdftunnel.serve import Counters, RouteTable
from pdftunnel.tunnel import TunnelStatus


class ConfigSource(Protocol):
    """The configuration in use right now; it changes under hot reload."""

    @property
    def config(self) -> Config: ...
    @property
    def routes(self) -> RouteTable: ...
    @property
    def verifier(self) -> AccessVerifier | None: ...
    @property
    def config_error(self) -> str | None: ...


class TunnelSource(Protocol):
    @property
    def status(self) -> TunnelStatus: ...


class WebDeps(Protocol):
    @property
    def source(self) -> ConfigSource: ...
    @property
    def tunnel(self) -> TunnelSource: ...
    @property
    def counters(self) -> Counters: ...
    @property
    def version(self) -> str: ...
    @property
    def api_token(self) -> str | None: ...
    @property
    def custom_css(self) -> str | None:
        """Path of the operator's stylesheet, when the file exists."""
        ...
