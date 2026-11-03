"""From a request path to a file on disk, or to nothing.

The rules that keep the folder private: a request only ever reaches a file a route names,
every candidate is resolved (symlinks followed) and must still lie under `files/`, dotfiles
are invisible, and only regular files are served.
"""

from dataclasses import dataclass
from pathlib import Path

from pdftunnel.config.schema import Config, Route


@dataclass(frozen=True)
class FileMatch:
    """A file to send."""

    route: Route
    path: Path
    relative: str  # the file's path under files/, for logs and the status API

    @property
    def download_name(self) -> str:
        return self.route.filename or self.path.name


@dataclass(frozen=True)
class ListingMatch:
    """A folder route asked at its own path, with listing on."""

    route: Route
    directory: Path


Match = FileMatch | ListingMatch


def _safe_segments(rest: str) -> list[str] | None:
    """The segments of a path under a folder route, or None when one is unsafe."""
    segments = rest.split("/")
    for segment in segments:
        if segment in ("", ".", "..") or segment.startswith(".") or "\x00" in segment:
            return None
    return segments


def _resolve_under(base: Path, candidate: Path) -> Path | None:
    """`candidate` resolved, if it is a regular file inside the resolved `base`."""
    try:
        resolved = candidate.resolve(strict=True)
        root = base.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_relative_to(root) or not resolved.is_file():
        return None
    return resolved


class RouteTable:
    """The routes of one configuration, ready to answer requests."""

    def __init__(self, config: Config, files_dir: Path) -> None:
        self.files_dir = files_dir
        self._files: dict[str, Route] = {r.path: r for r in config.routes if not r.is_dir}
        # Longest prefix first, so /docs/manuals/ wins over /docs/
        self._dirs: list[Route] = sorted(
            (r for r in config.routes if r.is_dir), key=lambda r: len(r.path), reverse=True
        )

    @property
    def routes(self) -> list[Route]:
        return [*self._files.values(), *self._dirs]

    def match(self, url_path: str) -> Match | None:
        if "\x00" in url_path:
            return None
        route = self._files.get(url_path)
        if route is not None and route.file is not None:
            path = _resolve_under(self.files_dir, self.files_dir / route.file)
            return None if path is None else FileMatch(route, path, route.file)
        for route in self._dirs:
            if route.dir is None or not url_path.startswith(route.path):
                continue
            base = self.files_dir / route.dir
            rest = url_path.removeprefix(route.path)
            if rest == "":
                if not route.listing or not base.is_dir():
                    return None
                return ListingMatch(route, base)
            segments = _safe_segments(rest)
            if segments is None:
                return None
            # Under files/, not under the route's folder: a symlink to a sibling is deliberate
            path = _resolve_under(self.files_dir, base.joinpath(*segments))
            if path is None:
                return None
            return FileMatch(route, path, f"{route.dir}/{'/'.join(segments)}")
        return None

    def file_for(self, route: Route) -> Path | None:
        """The file a file route serves, or None when it is missing. For the status API."""
        if route.file is None:
            return None
        return _resolve_under(self.files_dir, self.files_dir / route.file)

    def listing(self, directory: Path) -> list[Path]:
        """The files a listing shows: regular files, no dotfiles, sorted by name."""
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return []
        return [
            p
            for p in entries
            if not p.name.startswith(".") and _resolve_under(self.files_dir, p) is not None
        ]
