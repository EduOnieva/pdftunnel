"""Requests per route, kept across restarts.

In memory while serving, written to `state/counters.json` every minute and at shutdown. A
read-only `/config` loses nothing but the persistence, and says so once.
"""

import json
import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)


class Counters:
    def __init__(self, file: Path) -> None:
        self._file = file
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}
        self._dirty = False
        self._warned = False

    def load(self) -> None:
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            log.warning("Ignoring %s: %s", self._file, exc)
            return
        if isinstance(data, dict):
            with self._lock:
                self._counts = {
                    str(k): int(v)
                    for k, v in data.items()
                    if isinstance(v, int) and not isinstance(v, bool)
                }

    def hit(self, route_path: str) -> None:
        with self._lock:
            self._counts[route_path] = self._counts.get(route_path, 0) + 1
            self._dirty = True

    def get(self, route_path: str) -> int:
        with self._lock:
            return self._counts.get(route_path, 0)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def save(self) -> bool:
        """Write the counts if they changed. Returns whether a write happened."""
        with self._lock:
            if not self._dirty:
                return False
            data = dict(self._counts)
            self._dirty = False
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, sort_keys=True, indent=1), encoding="utf-8")
            tmp.replace(self._file)
        except OSError as exc:
            if not self._warned:
                log.warning(
                    "Cannot write %s (%s); request counters are kept in memory only",
                    self._file,
                    exc.strerror or exc,
                )
                self._warned = True
            with self._lock:
                self._dirty = True
            return False
        return True
