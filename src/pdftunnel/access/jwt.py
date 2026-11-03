"""Verification of the Cloudflare Access token.

Cloudflare puts the login's JWT in the `Cf-Access-Jwt-Assertion` header of every request
that passed an Access policy. Checking it here is the defence in depth for the case where a
request reaches the container some other way: a mapped port, or a hostname without a policy.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

import jwt
from jwt import PyJWK, PyJWKClient

from pdftunnel.config.schema import AccessConfig

log = logging.getLogger(__name__)

HEADER = "cf-access-jwt-assertion"
ALGORITHMS = ["RS256"]


class KeyProvider(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> PyJWK: ...


@dataclass(frozen=True)
class AccessIdentity:
    email: str | None
    subject: str | None


class AccessDeniedError(Exception):
    """The reason is logged, never shown to the visitor."""


class AccessVerifier:
    def __init__(self, config: AccessConfig, keys: KeyProvider | None = None) -> None:
        if not config.is_configured:
            raise ValueError("Access verification needs team_domain and audience")
        self._config = config
        # Cloudflare rotates the keys; the client caches them and refetches on an unknown kid
        self._keys: KeyProvider = keys or PyJWKClient(
            config.certs_url, cache_keys=True, lifespan=3600, timeout=10
        )

    @property
    def config(self) -> AccessConfig:
        return self._config

    def verify(self, token: str | None) -> AccessIdentity:
        """Blocking: the first call fetches the team's public keys. Call it in a thread."""
        if not token:
            raise AccessDeniedError("no Access token in the request")
        try:
            key = self._keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=self._config.audience,
                issuer=self._config.issuer,
                options={"require": ["exp", "iat", "aud", "iss"]},
                leeway=30,
            )
        except jwt.PyJWTError as exc:
            raise AccessDeniedError(f"invalid Access token: {exc}") from exc
        email = claims.get("email")
        subject = claims.get("sub")
        return AccessIdentity(
            email=email if isinstance(email, str) else None,
            subject=subject if isinstance(subject, str) else None,
        )
