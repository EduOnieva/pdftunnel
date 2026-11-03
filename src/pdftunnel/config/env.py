"""Environment variables: the process settings and the tunnel token.

`FILE__<VAR>` names a file whose contents become the value (the linuxserver convention for
Docker secrets) and beats a plain `<VAR>`. The token is the only secret, and it never lands
in `config.yaml`.
"""

import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
FILE_PREFIX = "FILE__"


class FileEnvSource(PydanticBaseSettingsSource):
    """Reads `FILE__<FIELD>` variables and substitutes the named file's contents."""

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        path = os.environ.get(FILE_PREFIX + field_name.upper())
        if path is None:
            return None, field_name, False
        try:
            value = Path(path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError(
                f"{FILE_PREFIX}{field_name.upper()} points to an unreadable file: {exc}"
            ) from exc
        return value, field_name, False

    def __call__(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            value, key, _ = self.get_field_value(field, field_name)
            if value is not None:
                values[key] = value
        return values


class EnvSettings(BaseSettings):
    """Everything the container reads from its environment."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    config_dir: Path = Path("/config")
    # Loopback by default: only cloudflared, in the same container, reaches the server. Binding
    # to 0.0.0.0 and mapping the port is for local testing, since it bypasses Cloudflare Access
    web_bind: str = "127.0.0.1"
    web_port: int = Field(8080, ge=0, le=65535)  # 0 lets the OS pick a port
    tunnel_token: SecretStr | None = None
    api_token: SecretStr | None = Field(None, description="Bearer token that enables /api/status")
    cloudflared_bin: Path = Path("/usr/local/bin/cloudflared")
    reload_seconds: float = Field(2.0, gt=0, description="How often config.yaml is checked")
    log_level: str = "INFO"
    tz: str = "Etc/UTC"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, FileEnvSource(settings_cls), env_settings)

    @field_validator("log_level")
    @classmethod
    def known_log_level(cls, value: str) -> str:
        upper = value.strip().upper()
        if upper not in LOG_LEVELS:
            raise ValueError(f"must be one of {', '.join(LOG_LEVELS)}")
        return upper

    @field_validator("tz")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("is not a known IANA timezone") from exc
        return value

    @field_validator("tunnel_token", "api_token")
    @classmethod
    def non_empty_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            return None
        return value
