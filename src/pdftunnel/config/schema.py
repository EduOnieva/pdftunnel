"""The shape of `config.yaml`.

A route maps a URL path to one file, or to a folder whose files are served under the path.
Everything else in `/config/files` stays unreachable, so an old version left next to the
published file is never served by accident.
"""

import re
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# The application's own URLs. A route on one of them would be shadowed, so it is refused.
RESERVED_PREFIXES = ("/healthz", "/api", "/_pdftunnel")
_FILENAME_FORBIDDEN = re.compile(r'[\x00-\x1f\x7f/\\"]')


class Disposition(StrEnum):
    INLINE = "inline"  # the browser shows the PDF, with a download button of its own
    ATTACHMENT = "attachment"  # the browser saves it


def normalise_url_path(raw: str, *, folder: bool) -> str:
    """Clean a configured URL path: one leading slash, no empty or dot segments, a trailing
    slash exactly when it names a folder."""
    if not raw.startswith("/"):
        raise ValueError("must start with /")
    if any(char in raw for char in "?#") or "\x00" in raw:
        raise ValueError("must not contain ?, # or control characters")
    segments = raw.strip("/").split("/") if raw.strip("/") else []
    for segment in segments:
        if segment in ("", ".", ".."):
            raise ValueError("must not contain empty, . or .. segments")
    path = "/" + "/".join(segments)
    if folder and path != "/":
        path += "/"
    return path


def check_relative_file_path(raw: str) -> str:
    """A path under `files/`: relative, no `..`, no dotfiles (they are never served)."""
    if not raw or raw.strip() != raw:
        raise ValueError("must not be empty or have surrounding spaces")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or "\\" in raw or "\x00" in raw:
        raise ValueError("must be a relative path under files/")
    for part in pure.parts:
        if part in (".", "..") or part.startswith("."):
            raise ValueError("must not contain . or .. segments or dotfiles")
    return str(pure)


class Route(BaseModel):
    """One published URL."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(description="URL path, e.g. / or /catalogue or /docs/")
    file: str | None = Field(None, description="A file under files/, served at `path`")
    dir: str | None = Field(None, description="A folder under files/, served under `path`")
    filename: str | None = Field(
        None, description="Name the browser shows and saves; default: the file's own name"
    )
    disposition: Disposition = Disposition.INLINE
    listing: bool = Field(False, description="Folder routes: list the files at `path`")
    listed: bool = Field(True, description="Show on the index page when it is enabled")
    access: bool = Field(False, description="Require a Cloudflare Access login")
    title: str | None = Field(None, description="Label on the index page; default: the path")

    @field_validator("path")
    @classmethod
    def clean_path(cls, value: str) -> str:
        path = normalise_url_path(value, folder=False)
        if any(path == p or path.startswith(p + "/") for p in RESERVED_PREFIXES):
            raise ValueError(f"{path} is reserved by pdftunnel")
        return path

    @field_validator("file", "dir")
    @classmethod
    def relative_under_files(cls, value: str | None) -> str | None:
        return None if value is None else check_relative_file_path(value)

    @field_validator("filename")
    @classmethod
    def plain_filename(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip() or _FILENAME_FORBIDDEN.search(value):
            raise ValueError(
                "must be a plain file name without slashes, quotes or control characters"
            )
        return value.strip()

    @model_validator(mode="after")
    def one_target(self) -> Self:
        if (self.file is None) == (self.dir is None):
            raise ValueError("needs exactly one of file: or dir:")
        if self.file is not None and self.listing:
            raise ValueError("listing: applies to dir: routes only")
        # Validators may run again when the route is embedded in a Config; stay idempotent
        if self.is_dir and not self.path.endswith("/"):
            object.__setattr__(self, "path", self.path + "/")
        return self

    @property
    def is_dir(self) -> bool:
        return self.dir is not None

    @property
    def label(self) -> str:
        if self.title:
            return self.title
        if self.filename:
            return self.filename
        return self.path if self.is_dir else PurePosixPath(self.file or "").name


class SiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = "pdftunnel"
    index: bool = Field(False, description="A page at / listing the routes marked listed")


class CacheConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_age: int = Field(300, ge=0, description="Seconds browsers and Cloudflare may cache a file")


class AccessConfig(BaseModel):
    """The Cloudflare Access application that protects routes with `access: true`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    team_domain: str | None = Field(None, description="e.g. myteam.cloudflareaccess.com")
    audience: str | None = Field(None, description="The application's AUD tag")

    @field_validator("team_domain")
    @classmethod
    def bare_domain(cls, value: str | None) -> str | None:
        if value is None:
            return None
        domain = value.strip().lower().removeprefix("https://").rstrip("/")
        if not domain:
            raise ValueError("must not be empty")
        if "." not in domain:
            domain += ".cloudflareaccess.com"
        if not re.fullmatch(r"[a-z0-9.-]+", domain):
            raise ValueError("must be a host name such as myteam.cloudflareaccess.com")
        return domain

    @property
    def is_configured(self) -> bool:
        return self.team_domain is not None and self.audience is not None

    @property
    def issuer(self) -> str:
        return f"https://{self.team_domain}"

    @property
    def certs_url(self) -> str:
        return f"https://{self.team_domain}/cdn-cgi/access/certs"


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    routes: list[Route] = Field(default_factory=list)
    site: SiteConfig = Field(default_factory=SiteConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    access: AccessConfig = Field(default_factory=AccessConfig)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        seen: set[str] = set()
        for route in self.routes:
            if route.path in seen:
                raise ValueError(f"routes: path {route.path} is configured twice")
            seen.add(route.path)
        if any(r.access for r in self.routes) and not self.access.is_configured:
            raise ValueError(
                "access: team_domain and audience are required when a route has access: true"
            )
        return self

    @property
    def listed_routes(self) -> list[Route]:
        return [r for r in self.routes if r.listed]
