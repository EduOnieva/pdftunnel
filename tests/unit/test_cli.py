import http.server
import threading
from pathlib import Path

import pytest

from pdftunnel import __version__
from pdftunnel.cli import EXIT_CONFIG_ERROR, EXIT_START_ERROR, main, make_token
from pdftunnel.config.loader import EXAMPLE_TEXT
from tests.conftest import FAKES_BIN

pytestmark = pytest.mark.usefixtures("clean_env")

CONFIG = """
routes:
  - path: /
    file: catalogue.pdf
  - path: /docs/
    dir: docs
    access: true
  - path: /gone
    file: gone.pdf
    listed: false
  - path: /nodir/
    dir: nowhere
site:
  index: true
access:
  team_domain: t
  audience: aud
"""


def test_version(capsys):
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "check-config" in capsys.readouterr().out


def test_print_example_config(capsys):
    assert main(["print-example-config"]) == 0
    assert capsys.readouterr().out == EXAMPLE_TEXT


def test_token(capsys):
    assert main(["token"]) == 0
    token = capsys.readouterr().out.strip()
    assert len(token) == 12 and token.isalnum() and token.islower()
    assert main(["token", "--length", "20"]) == 0
    assert len(capsys.readouterr().out.strip()) == 20
    assert main(["token", "--length", "4"]) == EXIT_CONFIG_ERROR
    assert "guessed" in capsys.readouterr().err
    assert make_token(8) != make_token(8)


def test_environment_error(monkeypatch, capsys):
    monkeypatch.setenv("WEB_PORT", "abc")
    assert main(["check-config"]) == EXIT_CONFIG_ERROR
    assert "environment: web_port" in capsys.readouterr().err


def test_file_env_error(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("FILE__TUNNEL_TOKEN", str(tmp_path / "none"))
    assert main(["check-config"]) == EXIT_CONFIG_ERROR
    assert "unreadable file" in capsys.readouterr().err


def test_check_config_writes_the_example_first(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "cfg"))
    assert main(["check-config"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("OK: 0 route(s)") and "TUNNEL_TOKEN is not set" in out
    assert (tmp_path / "cfg" / "config.yaml").read_text() == EXAMPLE_TEXT
    assert (tmp_path / "cfg" / "files").is_dir()


def test_check_config_lists_routes(monkeypatch, paths, capsys):
    monkeypatch.setenv("CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("TUNNEL_TOKEN", "x")
    paths.config_file.write_text(CONFIG)
    assert main(["check-config"]) == 0
    out = capsys.readouterr().out
    assert "OK: 4 route(s), 2 with a missing file or folder: /gone, /nodir/" in out
    assert "index page on" in out and "Cloudflare Access via t.cloudflareaccess.com" in out
    assert "TUNNEL_TOKEN" not in out
    assert "  /  ->  files/catalogue.pdf\n" in out
    assert "  /docs/  ->  files/docs/  [access]\n" in out
    assert "  /gone  ->  files/gone.pdf  [unlisted]\n" in out


def test_check_config_invalid(monkeypatch, paths, capsys):
    monkeypatch.setenv("CONFIG_DIR", str(paths.config_dir))
    paths.config_file.write_text("routes: [{path: nope, file: a.pdf}]\n")
    assert main(["check-config"]) == EXIT_CONFIG_ERROR
    err = capsys.readouterr().err
    assert "Configuration error:" in err and "routes[0].path: must start with /" in err


def test_print_config(monkeypatch, paths, capsys):
    monkeypatch.setenv("CONFIG_DIR", str(paths.config_dir))
    paths.config_file.write_text(CONFIG)
    assert main(["print-config"]) == 0
    out = capsys.readouterr().out
    assert "path: /docs/" in out and "team_domain: t.cloudflareaccess.com" in out


def test_unwritable_config_dir_warns(monkeypatch, tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("")
    monkeypatch.setenv("CONFIG_DIR", str(blocker / "cfg"))
    assert main(["check-config"]) == EXIT_CONFIG_ERROR
    err = capsys.readouterr().err
    assert "Warning: cannot create" in err and "cannot read" in err


def test_run_without_token(monkeypatch, paths, capsys):
    monkeypatch.setenv("CONFIG_DIR", str(paths.config_dir))
    assert main(["run"]) == EXIT_CONFIG_ERROR
    assert "TUNNEL_TOKEN is not set" in capsys.readouterr().err


def test_run_port_in_use(monkeypatch, paths, capsys):
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    monkeypatch.setenv("CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("TUNNEL_TOKEN", "x")
    monkeypatch.setenv("WEB_PORT", str(port))
    monkeypatch.setenv("CLOUDFLARED_BIN", str(FAKES_BIN / "cloudflared"))
    try:
        assert main(["run"]) == EXIT_START_ERROR
    finally:
        sock.close()
    assert "Cannot start" in capsys.readouterr().err


class _Handler(http.server.BaseHTTPRequestHandler):
    status = 200
    body = b"ok\n"

    def do_GET(self):
        self.send_response(self.status)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_healthcheck(monkeypatch, fake_server, capsys):
    monkeypatch.setenv("WEB_PORT", str(fake_server.server_port))
    assert main(["healthcheck"]) == 0
    assert capsys.readouterr().out == "ok\n"
    _Handler.status, _Handler.body = 503, b"tunnel connecting\n"
    try:
        assert main(["healthcheck"]) == 1
        assert capsys.readouterr().out == "unhealthy: tunnel connecting\n"
    finally:
        _Handler.status, _Handler.body = 200, b"ok\n"


def test_healthcheck_nothing_listening(monkeypatch, capsys):
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    monkeypatch.setenv("WEB_PORT", str(port))
    assert main(["healthcheck"]) == 1
    assert capsys.readouterr().out.startswith("unhealthy:")


def test_paths_type() -> None:
    assert isinstance(FAKES_BIN, Path)
