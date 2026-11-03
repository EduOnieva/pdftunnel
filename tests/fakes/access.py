"""A Cloudflare Access look-alike: an RSA key pair and the tokens it would issue."""

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm

TEAM = "example.cloudflareaccess.com"
AUD = "a" * 64


class FakeKeys:
    """Stands in for PyJWKClient: always returns the one key."""

    def __init__(self) -> None:
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = RSAAlgorithm.to_jwk(self.private.public_key(), as_dict=True)
        public["kid"] = "test-key"
        self.jwk = PyJWK(public, algorithm="RS256")
        self.calls = 0

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        self.calls += 1
        return self.jwk

    def token(self, **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "aud": [AUD],
            "iss": f"https://{TEAM}",
            "iat": now,
            "exp": now + 600,
            "email": "someone@example.com",
            "sub": "user-1",
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self.private, algorithm="RS256", headers={"kid": "test-key"})
