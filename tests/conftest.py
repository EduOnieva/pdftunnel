from pathlib import Path

import pytest

from pdftunnel.paths import ConfigPaths

FAKES_BIN = Path(__file__).parent / "fakes" / "bin"
PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture
def paths(tmp_path: Path) -> ConfigPaths:
    """A config folder with a few files: catalogue.pdf, docs/a.pdf, docs/b.txt, an old
    version nothing routes to, a dotfile and a symlink that escapes the folder."""
    config = ConfigPaths(tmp_path / "config")
    assert config.ensure() == []
    files = config.files_dir
    (files / "catalogue.pdf").write_bytes(PDF)
    (files / "old.pdf").write_bytes(PDF)
    (files / ".secret.pdf").write_bytes(PDF)
    (files / "docs").mkdir()
    (files / "docs" / "a.pdf").write_bytes(PDF)
    (files / "docs" / "b.txt").write_text("hello\n")
    (files / "docs" / ".hidden").write_text("no\n")
    (files / "docs" / "sub").mkdir()
    (files / "docs" / "sub" / "deep.pdf").write_bytes(PDF)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n")
    (files / "escape.txt").symlink_to(outside)
    (files / "docs" / "alias.pdf").symlink_to(files / "catalogue.pdf")
    return config


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(__import__("os").environ):
        if name.startswith("FILE__") or name in {
            "CONFIG_DIR",
            "WEB_BIND",
            "WEB_PORT",
            "TUNNEL_TOKEN",
            "API_TOKEN",
            "CLOUDFLARED_BIN",
            "RELOAD_SECONDS",
            "LOG_LEVEL",
            "TZ",
        }:
            monkeypatch.delenv(name, raising=False)
