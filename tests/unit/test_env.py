from pathlib import Path

import pytest
from pydantic import ValidationError

from pdftunnel.config.env import EnvSettings

pytestmark = pytest.mark.usefixtures("clean_env")


def test_defaults():
    env = EnvSettings()
    assert env.config_dir == Path("/config")
    assert env.web_bind == "127.0.0.1" and env.web_port == 8080
    assert env.tunnel_token is None and env.api_token is None
    assert env.cloudflared_bin == Path("/usr/local/bin/cloudflared")
    assert env.log_level == "INFO" and env.tz == "Etc/UTC"


def test_values_from_environment(monkeypatch):
    monkeypatch.setenv("TUNNEL_TOKEN", "abc")
    monkeypatch.setenv("API_TOKEN", "xyz")
    monkeypatch.setenv("WEB_PORT", "0")
    monkeypatch.setenv("log_level", "debug")
    monkeypatch.setenv("TZ", "Europe/Madrid")
    env = EnvSettings()
    assert env.tunnel_token is not None and env.tunnel_token.get_secret_value() == "abc"
    assert env.api_token is not None and env.api_token.get_secret_value() == "xyz"
    assert env.web_port == 0 and env.log_level == "DEBUG" and env.tz == "Europe/Madrid"


def test_blank_tokens_count_as_unset(monkeypatch):
    monkeypatch.setenv("TUNNEL_TOKEN", "   ")
    monkeypatch.setenv("API_TOKEN", "")
    env = EnvSettings()
    assert env.tunnel_token is None and env.api_token is None


def test_file_variable_wins(monkeypatch, tmp_path):
    secret = tmp_path / "token"
    secret.write_text("from-file\n")
    monkeypatch.setenv("TUNNEL_TOKEN", "from-env")
    monkeypatch.setenv("FILE__TUNNEL_TOKEN", str(secret))
    env = EnvSettings()
    assert env.tunnel_token is not None and env.tunnel_token.get_secret_value() == "from-file"


def test_file_variable_unreadable(monkeypatch, tmp_path):
    monkeypatch.setenv("FILE__TUNNEL_TOKEN", str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="unreadable file"):
        EnvSettings()


@pytest.mark.parametrize(
    ("name", "value"),
    [("LOG_LEVEL", "LOUD"), ("TZ", "Mars/Olympus"), ("WEB_PORT", "70000"), ("RELOAD_SECONDS", "0")],
)
def test_invalid_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        EnvSettings()


def test_secret_is_not_printed(monkeypatch):
    monkeypatch.setenv("TUNNEL_TOKEN", "abc")
    assert "abc" not in repr(EnvSettings())
