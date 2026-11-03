import time

import pytest

from pdftunnel.access import AccessDeniedError, AccessVerifier
from pdftunnel.config.schema import AccessConfig
from tests.fakes.access import AUD, TEAM, FakeKeys


@pytest.fixture
def keys() -> FakeKeys:
    return FakeKeys()


@pytest.fixture
def verifier(keys) -> AccessVerifier:
    return AccessVerifier(AccessConfig(team_domain=TEAM, audience=AUD), keys=keys)


def test_needs_configuration():
    with pytest.raises(ValueError, match="team_domain and audience"):
        AccessVerifier(AccessConfig())


def test_valid_token(verifier, keys):
    identity = verifier.verify(keys.token())
    assert identity.email == "someone@example.com" and identity.subject == "user-1"


def test_identity_fields_may_be_missing(verifier, keys):
    identity = verifier.verify(keys.token(email=None, sub=None))
    assert identity.email is None and identity.subject is None


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"aud": ["b" * 64]}, "Audience"),
        ({"iss": "https://other.cloudflareaccess.com"}, "Invalid issuer"),
        ({"exp": int(time.time()) - 120}, "expired"),
        ({"exp": None}, "exp"),
        ({"iat": None}, "iat"),
    ],
)
def test_rejected_claims(verifier, keys, overrides, reason):
    with pytest.raises(AccessDeniedError, match=reason):
        verifier.verify(keys.token(**overrides))


def test_missing_or_garbage_token(verifier):
    with pytest.raises(AccessDeniedError, match="no Access token"):
        verifier.verify(None)
    with pytest.raises(AccessDeniedError, match="no Access token"):
        verifier.verify("")
    with pytest.raises(AccessDeniedError, match="invalid Access token"):
        verifier.verify("not.a.jwt")


def test_wrong_key(verifier):
    other = FakeKeys()
    with pytest.raises(AccessDeniedError, match="invalid Access token"):
        verifier.verify(other.token())


def test_default_key_client_targets_the_team_certs():
    verifier = AccessVerifier(AccessConfig(team_domain="t", audience="x"))
    assert verifier.config.certs_url == "https://t.cloudflareaccess.com/cdn-cgi/access/certs"
