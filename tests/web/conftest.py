from collections.abc import AsyncIterator

import httpx
import pytest

from pdftunnel.access import AccessVerifier
from pdftunnel.config.schema import AccessConfig, Config, Disposition, Route, SiteConfig
from pdftunnel.serve import Counters
from pdftunnel.web import create_app
from tests.fakes.access import AUD, TEAM, FakeKeys
from tests.fakes.sources import FakeDeps, FakeSource, FakeTunnel


def make_config(**overrides) -> Config:
    base = {
        "routes": [
            Route(path="/", file="catalogue.pdf", filename="Catálogo 2026.pdf"),
            Route(path="/download", file="catalogue.pdf", disposition=Disposition.ATTACHMENT),
            Route(path="/secret-k7f3q9x2", file="catalogue.pdf", listed=False),
            Route(path="/docs/", dir="docs", listing=True, title="Documents"),
            Route(path="/plain/", dir="docs"),
            Route(path="/private", file="catalogue.pdf", access=True),
            Route(path="/missing", file="gone.pdf"),
        ],
        "site": SiteConfig(title="Test site", index=True),
        "access": AccessConfig(team_domain=TEAM, audience=AUD),
    }
    base.update(overrides)
    return Config(**base)


@pytest.fixture
def keys() -> FakeKeys:
    return FakeKeys()


@pytest.fixture
def deps(paths, keys, tmp_path) -> FakeDeps:
    config = make_config()
    verifier = AccessVerifier(config.access, keys=keys)
    return FakeDeps(
        source=FakeSource(paths, config, verifier),
        tunnel=FakeTunnel(),
        counters=Counters(tmp_path / "counters.json"),
    )


@pytest.fixture
async def client(deps) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(deps))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
