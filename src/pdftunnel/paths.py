"""Where files live inside the container.

Everything the operator touches is under one volume, `/config`: the configuration file,
the published files and the state the application writes.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConfigPaths:
    config_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.yaml"

    @property
    def files_dir(self) -> Path:
        """The published files. Only what a route names is served."""
        return self.config_dir / "files"

    @property
    def state_dir(self) -> Path:
        return self.config_dir / "state"

    @property
    def counters_file(self) -> Path:
        return self.state_dir / "counters.json"

    @property
    def custom_css(self) -> Path:
        """Optional stylesheet loaded after the index page's own, so the look can be changed."""
        return self.config_dir / "custom.css"

    def ensure(self) -> list[str]:
        """Create the folders. Returns the problems met instead of raising: a read-only
        `/config` still serves files, it only loses the counters."""
        problems: list[str] = []
        for folder in (self.config_dir, self.files_dir, self.state_dir):
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                problems.append(f"cannot create {folder}: {exc.strerror or exc}")
        return problems
