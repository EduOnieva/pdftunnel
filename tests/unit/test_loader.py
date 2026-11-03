import logging

import pytest

from pdftunnel.config.loader import (
    EXAMPLE_TEXT,
    ConfigError,
    ConfigWatcher,
    dump_config,
    ensure_config_files,
    load_config,
    parse_config_text,
)
from pdftunnel.config.schema import Config
from pdftunnel.paths import ConfigPaths

VALID = """
routes:
  - path: /
    file: catalogue.pdf
  - path: /docs/
    dir: docs
site:
  index: true
"""


def test_example_parses_to_an_empty_config():
    config = parse_config_text(EXAMPLE_TEXT)
    assert config.routes == [] and not config.site.index and not config.access.is_configured


def test_valid_text():
    config = parse_config_text(VALID)
    assert [r.path for r in config.routes] == ["/", "/docs/"]


def test_empty_text_is_an_empty_config():
    assert parse_config_text("") == Config()


def test_invalid_yaml():
    with pytest.raises(ConfigError, match="not valid YAML"):
        parse_config_text("routes: [")


def test_top_level_must_be_a_mapping():
    with pytest.raises(ConfigError, match="top level must be a mapping"):
        parse_config_text("- a\n- b\n")


def test_errors_carry_their_path():
    with pytest.raises(ConfigError) as info:
        parse_config_text("routes:\n  - path: nope\n    file: a.pdf\n  - path: /b\n")
    assert info.value.problems == [
        "config.yaml: routes[0].path: must start with /",
        "config.yaml: routes[1]: needs exactly one of file: or dir:",
    ]


def test_empty_access_keys_are_ignored():
    config = parse_config_text("access:\n  team_domain:\n  audience:\n")
    assert not config.access.is_configured


def test_ensure_config_files_writes_the_example_once(paths):
    assert ensure_config_files(paths)
    assert paths.config_file.read_text() == EXAMPLE_TEXT
    paths.config_file.write_text("site: {title: mine}\n")
    assert not ensure_config_files(paths)
    assert "mine" in paths.config_file.read_text()


def test_ensure_config_files_cannot_write(tmp_path, caplog):
    nowhere = ConfigPaths(tmp_path / "nowhere")  # the folder does not exist
    with caplog.at_level(logging.WARNING):
        assert not ensure_config_files(nowhere)
    assert "Cannot write" in caplog.text


def test_load_config_missing_file_is_empty(paths):
    assert load_config(paths) == Config()


def test_load_config_reads_the_file(paths):
    paths.config_file.write_text(VALID)
    assert len(load_config(paths).routes) == 2


def test_load_config_unreadable(paths):
    paths.config_file.mkdir()
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(paths)


def test_dump_round_trips():
    config = parse_config_text(VALID)
    again = parse_config_text(dump_config(config))
    assert again == config


class TestWatcher:
    def test_reloads_on_change(self, paths):
        paths.config_file.write_text(VALID)
        seen: list[Config] = []
        watcher = ConfigWatcher(paths, load_config(paths), on_change=seen.append)
        assert not watcher.poll()
        paths.config_file.write_text("site: {index: false}\n")
        _touch_later(paths)
        assert watcher.poll()
        assert watcher.config.routes == [] and seen and watcher.last_error is None

    def test_broken_edit_keeps_the_previous_config(self, paths, caplog):
        paths.config_file.write_text(VALID)
        watcher = ConfigWatcher(paths, load_config(paths))
        paths.config_file.write_text("routes: [{path: nope}]\n")
        _touch_later(paths)
        with caplog.at_level(logging.ERROR):
            assert not watcher.poll()
            assert not watcher.poll()  # same error: not logged again
        assert len(watcher.config.routes) == 2
        error = watcher.last_error
        assert error is not None and "must start with /" in error
        assert caplog.text.count("not reloaded") == 1
        paths.config_file.write_text(VALID)
        _touch_later(paths, 2)
        with caplog.at_level(logging.INFO):
            assert watcher.poll()
        assert watcher.last_error is None
        assert "valid again" in caplog.text

    def test_deleted_file_is_an_empty_config(self, paths):
        paths.config_file.write_text(VALID)
        watcher = ConfigWatcher(paths, load_config(paths))
        paths.config_file.unlink()
        assert watcher.poll()
        assert watcher.config.routes == []


def _touch_later(paths, seconds: int = 1) -> None:
    """Advance the file's mtime so the poll sees a change even inside the same second."""
    import os

    stat = paths.config_file.stat()
    os.utime(paths.config_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + seconds * 10**9))
