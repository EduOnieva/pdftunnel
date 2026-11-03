import json
import logging
from pathlib import Path

from pdftunnel.serve.counters import Counters


def test_hit_and_snapshot(tmp_path):
    counters = Counters(tmp_path / "c.json")
    counters.hit("/")
    counters.hit("/")
    counters.hit("/docs/")
    assert counters.get("/") == 2 and counters.get("/none") == 0
    assert counters.snapshot() == {"/": 2, "/docs/": 1}


def test_save_and_load(tmp_path):
    file = tmp_path / "state" / "c.json"
    counters = Counters(file)
    assert not counters.save()  # nothing to write
    counters.hit("/a")
    assert counters.save()
    assert not counters.save()  # clean again
    assert json.loads(file.read_text()) == {"/a": 1}
    again = Counters(file)
    again.load()
    assert again.get("/a") == 1


def test_load_ignores_missing_and_broken(tmp_path, caplog):
    counters = Counters(tmp_path / "none.json")
    counters.load()
    broken = tmp_path / "broken.json"
    broken.write_text("{nope")
    with caplog.at_level(logging.WARNING):
        Counters(broken).load()
    assert "Ignoring" in caplog.text
    odd = tmp_path / "odd.json"
    odd.write_text('{"/a": "x", "/b": true, "/c": 3}')
    counters = Counters(odd)
    counters.load()
    assert counters.snapshot() == {"/c": 3}
    listy = tmp_path / "list.json"
    listy.write_text("[1, 2]")
    counters = Counters(listy)
    counters.load()
    assert counters.snapshot() == {}


def test_unwritable_warns_once_and_keeps_counting(tmp_path, caplog):
    blocked = tmp_path / "file-not-dir"
    blocked.write_text("")
    counters = Counters(blocked / "c.json")
    counters.hit("/")
    with caplog.at_level(logging.WARNING):
        assert not counters.save()
        assert not counters.save()
    assert caplog.text.count("Cannot write") == 1
    assert counters.get("/") == 1


def test_replace_is_atomic(tmp_path: Path):
    file = tmp_path / "c.json"
    counters = Counters(file)
    counters.hit("/")
    counters.save()
    assert not file.with_suffix(".tmp").exists()
