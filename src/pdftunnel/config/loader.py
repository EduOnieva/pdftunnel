"""Read, validate and watch `config.yaml`.

The file is re-read while the container runs. A broken edit keeps the last good configuration
and is logged once, so a typo never takes a public page down; at startup it is an error.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from pdftunnel.config.schema import Config
from pdftunnel.paths import ConfigPaths

log = logging.getLogger(__name__)

EXAMPLE_TEXT = """\
# pdftunnel configuration. Re-read while the container runs: edit, save, done.
# Files live next to this file under files/. Only what a route names is served; anything
# else in files/ (an old version, a draft) stays unreachable.

routes:
  # The catalogue at the root of your hostname: https://docs.example.com/
  # - path: /
  #   file: catalogue.pdf
  #   filename: "Catalogue 2026.pdf"   # the name the browser shows and saves
  #   disposition: inline              # inline (open in the browser) | attachment (download)

  # A secret link: an unguessable path, no login. `pdftunnel token` prints one.
  # - path: /prices-k7f3q9x2
  #   file: prices.pdf
  #   listed: false                    # kept off the index page

  # A folder: every file under files/docs is served at /docs/<name>
  # - path: /docs/
  #   dir: docs
  #   listing: true                    # a file list at /docs/ (default: false)
  #   access: true                     # only through a Cloudflare Access login (see below)

site:
  title: pdftunnel
  index: false      # true: a page at / listing the routes marked `listed` (unless / is a route)

cache:
  max_age: 300      # seconds browsers and Cloudflare may cache a file. 0 disables caching

# Only for routes with access: true. The Access application in Zero Trust gives both values.
access:
  team_domain:      # myteam.cloudflareaccess.com
  audience:         # the application's AUD tag
"""


class ConfigError(Exception):
    """A configuration the application refuses to run with. `problems` lists them."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def format_validation_errors(exc: ValidationError) -> list[str]:
    """`routes[1].path: must start with /` instead of pydantic's multi-line report."""
    problems: list[str] = []
    for error in exc.errors():
        location = ""
        for part in error["loc"]:
            location += f"[{part}]" if isinstance(part, int) else (f".{part}" if location else part)
        message = error["msg"].removeprefix("Value error, ").removeprefix("Assertion failed, ")
        problems.append(f"{location}: {message}" if location else message)
    return problems


def ensure_config_files(paths: ConfigPaths) -> bool:
    """Write the commented example when there is no config file yet. Returns whether it did."""
    if paths.config_file.exists():
        return False
    try:
        paths.config_file.write_text(EXAMPLE_TEXT, encoding="utf-8")
    except OSError as exc:
        log.warning("Cannot write %s: %s", paths.config_file, exc.strerror or exc)
        return False
    return True


def parse_config_text(text: str, source: str = "config.yaml") -> Config:
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError([f"{source}: not valid YAML: {exc}"]) from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError([f"{source}: the top level must be a mapping"])
    # A section whose entries are all commented out, or an empty `team_domain:`, parse as
    # None; they mean "not given"
    data = {k: v for k, v in data.items() if v is not None}
    access = data.get("access")
    if isinstance(access, dict):
        data["access"] = {k: v for k, v in access.items() if v is not None}
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError([f"{source}: {p}" for p in format_validation_errors(exc)]) from exc


def load_config(paths: ConfigPaths) -> Config:
    try:
        text = paths.config_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Config()
    except OSError as exc:
        raise ConfigError([f"cannot read {paths.config_file}: {exc.strerror or exc}"]) from exc
    return parse_config_text(text, str(paths.config_file))


def dump_config(config: Config) -> str:
    return yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False, allow_unicode=True)


def _signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


class ConfigWatcher:
    """Holds the current configuration and re-reads the file when it changes."""

    def __init__(
        self,
        paths: ConfigPaths,
        initial: Config,
        on_change: Callable[[Config], None] | None = None,
    ) -> None:
        self._paths = paths
        self._config = initial
        self._on_change = on_change
        self._signature = _signature(paths.config_file)
        self._last_error: str | None = None

    @property
    def config(self) -> Config:
        return self._config

    @property
    def last_error(self) -> str | None:
        """The problem with the latest edit, while the last good configuration is in use."""
        return self._last_error

    def poll(self) -> bool:
        """Re-read the file if it changed. Returns True when a new configuration is in use."""
        signature = _signature(self._paths.config_file)
        if signature == self._signature:
            return False
        self._signature = signature
        try:
            config = load_config(self._paths)
        except ConfigError as exc:
            message = "; ".join(exc.problems)
            if message != self._last_error:
                log.error("config.yaml not reloaded, keeping the previous one: %s", message)
            self._last_error = message
            return False
        if self._last_error is not None:
            log.info("config.yaml is valid again")
        self._last_error = None
        self._config = config
        log.info("Configuration reloaded: %d route(s)", len(config.routes))
        if self._on_change is not None:
            self._on_change(config)
        return True
