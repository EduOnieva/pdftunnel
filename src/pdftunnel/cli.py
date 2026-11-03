"""Command-line entry point.

`run` is what the container executes; the other subcommands help configure and check it.
"""

import argparse
import asyncio
import secrets
import string
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence

from pydantic import ValidationError

from pdftunnel import __version__
from pdftunnel.app import Application, WebStartError
from pdftunnel.config import (
    EXAMPLE_TEXT,
    ConfigError,
    EnvSettings,
    dump_config,
    ensure_config_files,
    format_validation_errors,
    load_config,
)
from pdftunnel.logging_setup import configure_logging
from pdftunnel.paths import ConfigPaths
from pdftunnel.serve import RouteTable

EXIT_CONFIG_ERROR = 2
EXIT_START_ERROR = 3
TOKEN_ALPHABET = string.ascii_lowercase + string.digits


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdftunnel",
        description="Publish PDFs and other files from a folder through a Cloudflare Tunnel.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("run", help="serve the routes and run the tunnel (the container default)")
    commands.add_parser("check-config", help="validate config.yaml and list the routes")
    commands.add_parser("print-config", help="print the effective configuration as YAML")
    commands.add_parser("print-example-config", help="print the commented example config.yaml")
    commands.add_parser("healthcheck", help="exit 0 when the local server reports healthy")
    token = commands.add_parser("token", help="print a random token for a secret link")
    token.add_argument("--length", type=int, default=12, help="characters (default 12)")
    return parser


def make_token(length: int) -> str:
    if length < 8:
        raise ValueError("a token shorter than 8 characters can be guessed")
    return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(length))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None:
        build_parser().print_help()
        return 0
    if args.command == "print-example-config":
        print(EXAMPLE_TEXT, end="")
        return 0
    if args.command == "token":
        try:
            print(make_token(args.length))
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return EXIT_CONFIG_ERROR
        return 0

    try:
        env = EnvSettings()
    except ValueError as exc:
        # Field problems arrive wrapped; a FILE__ variable pointing nowhere is a bare ValueError
        problems = format_validation_errors(exc) if isinstance(exc, ValidationError) else [str(exc)]
        return _report(ConfigError([f"environment: {p}" for p in problems]))
    if args.command == "healthcheck":
        return healthcheck(env.web_port)

    configure_logging(env.log_level)
    paths = ConfigPaths(config_dir=env.config_dir)
    for problem in paths.ensure():
        print(f"Warning: {problem}", file=sys.stderr)
    ensure_config_files(paths)
    try:
        config = load_config(paths)
    except ConfigError as exc:
        return _report(exc)

    if args.command == "check-config":
        table = RouteTable(config, paths.files_dir)
        missing = [r.path for r in config.routes if not r.is_dir and table.file_for(r) is None]
        missing += [
            r.path
            for r in config.routes
            if r.is_dir and not (paths.files_dir / (r.dir or "")).is_dir()
        ]
        summary = f"OK: {len(config.routes)} route(s)"
        if missing:
            summary += f", {len(missing)} with a missing file or folder: {', '.join(missing)}"
        if config.site.index:
            summary += ", index page on"
        if config.access.is_configured:
            summary += f", Cloudflare Access via {config.access.team_domain}"
        if env.tunnel_token is None:
            summary += "; TUNNEL_TOKEN is not set, `run` would refuse to start"
        print(summary)
        for route in config.routes:
            target = f"{route.dir}/" if route.is_dir else route.file
            flags = [
                f for f, on in (("access", route.access), ("unlisted", not route.listed)) if on
            ]
            print(
                f"  {route.path}  ->  files/{target}" + (f"  [{', '.join(flags)}]" if flags else "")
            )
        return 0
    if args.command == "print-config":
        print(dump_config(config), end="")
        return 0
    try:
        return asyncio.run(Application(env, paths).run())
    except ConfigError as exc:
        return _report(exc)
    except WebStartError as exc:
        print(f"Cannot start: {exc}", file=sys.stderr)
        return EXIT_START_ERROR


def healthcheck(port: int) -> int:
    url = f"http://127.0.0.1:{port}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=4) as response:
            body = response.read().decode("utf-8", "replace").strip()
    except urllib.error.HTTPError as exc:
        print(f"unhealthy: {exc.read().decode('utf-8', 'replace').strip() or exc.code}")
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"unhealthy: {exc}")
        return 1
    print(body)
    return 0


def _report(exc: ConfigError) -> int:
    print("Configuration error:", file=sys.stderr)
    for problem in exc.problems:
        print(f"  - {problem}", file=sys.stderr)
    return EXIT_CONFIG_ERROR
