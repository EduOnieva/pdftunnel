# Development

Python 3.13, FastAPI with uvicorn, pydantic for the configuration, PyJWT for the Access
token, jinja2 for the two pages. The package is `pdftunnel` under `src/`, installed into a
virtualenv with [uv](https://docs.astral.sh/uv/).

```bash
make install   # uv sync --frozen
make check     # lock check, ruff format and lint, mypy --strict, tests, coverage gate 85 %
make fmt       # ruff format and the auto-fixes
make build     # docker build -t pdftunnel:dev .
make smoke     # scripts/smoke.sh against that image
```

## Layout

```
src/pdftunnel/
  app.py          the service: wires the parts, owns the signal handling and the shutdown order
  cli.py          run, check-config, print-config, print-example-config, token, healthcheck
  paths.py        where files live under /config
  config/         schema.py (pydantic models, the path rules), env.py (variables, FILE__),
                  loader.py (parse, validate, the example text, the watcher for hot reload)
  serve/          routes.py (URL to file, the safety checks), responses.py (headers, 304),
                  counters.py (opens per route, persisted)
  access/         jwt.py (the Cloudflare Access token: key cache, verification)
  tunnel/         supervisor.py (cloudflared as a child process: start, relay, restart, stop)
  web/            app.py (the catch-all route), api.py, health.py, pages.py, middleware.py
                  (security headers, access log), templates/, static/app.css
tests/
  unit/           one module per source module; a fake cloudflared in tests/fakes/bin and a
                  fake Access key pair in tests/fakes/access.py
  web/            every endpoint through httpx against the ASGI app
scripts/smoke.sh  the built image, as the compose file runs it, with a bogus token
docs/wiki/        these pages; pushed to the GitHub wiki
```

Two rules shape it. Everything a request can reach goes through `RouteTable.match`, which is
the only place a URL becomes a path on disk, so the safety rules (under `files/`, no dotfiles,
regular files only, symlinks resolved) live in one function with its own tests. And anything
with a side effect (the child process, the key fetch, time) takes its dependency as a
parameter, so the unit tests run in seconds with fakes and the smoke test is the only place a
real image runs.

## Tests

- **Unit** (`tests/unit`): the schema's rules, the loader and the watcher, route matching
  against a folder with traversal attempts and symlinks in both directions, the counters, the
  Access verifier with tokens signed by a generated key, the supervisor against the fake
  binary (connect, exit with backoff, crash after connecting, a process that ignores SIGTERM),
  the CLI, and the application started on a free port, reloaded, and stopped with a real
  SIGTERM.
- **Web** (`tests/web`): files with every header, Range, conditional requests, folder routes,
  what must be 404, Access routes with and without a token, the counters, the pages and their
  escaping, the status API's authentication and payload, the health check.
- **Smoke** (`make smoke`): the image under the compose file's constraints with a bogus token.

`filterwarnings = error`, so a deprecation fails the test that triggers it. Coverage is
above 99 %; the gate is 85 %.

## CI and the images

Every push to `main`, `develop` and `wip` runs the quality job on Python 3.13 and 3.14 (the
latter informational), an amd64 image build with the smoke test, and an arm64 build. The
Release workflow publishes images on pushes to `main` and `develop` and on tags:

| Event | Tags published |
|---|---|
| push to `develop` | `develop` |
| push to `main` | `latest` |
| tag `vX.Y` | `X.Y` and `X` |
| every Monday, and on demand | `latest`, `X.Y` and `X` rebuilt from `main` without the layer cache |

Images go to Docker Hub and GHCR for amd64 and arm64, with provenance and an SBOM. The
runtime image is Alpine with tini and tzdata, the locked virtualenv, and cloudflared copied
from `cloudflare/cloudflared:<version>`, a stage of the Dockerfile that Dependabot bumps.
pip and the other interpreter tooling are removed. To scan a build without mounting the
Docker socket:

```bash
docker save pdftunnel:dev -o /tmp/pdftunnel.tar
docker run --rm -v /tmp:/scan:ro aquasec/trivy image --input /scan/pdftunnel.tar
```

Actions are pinned to commit SHAs; Dependabot keeps them, the Python lock file and the base
images current, grouped, with a 14-day cooldown after a release.

## Branches and releases

Work happens on `develop`. `wip` is the scratch branch ahead of it. A release:

1. Set `version` in `pyproject.toml` (two parts: after 1.0 comes 1.1) and turn the
   changelog's *Unreleased* section into the version with the date.
2. Commit on `develop`, merge `develop` into `main`, tag `vX.Y`, push both branches and the
   tag. The Release workflow refuses a tag that does not match the package version.
3. Create the GitHub release from the tag with the changelog section as its notes.

Commit messages are semantic (`fix:`, `feat:`, `docs:`, `ci:`, `build:`, `refactor:`,
`style:`, `chore:`) with a short title and one explanatory paragraph.

## The wiki

These pages live in `docs/wiki/` in the repository, so they are versioned with the code and
reviewed like it. Publishing them:

```bash
git clone git@github.com:EduOnieva/pdftunnel.wiki.git /tmp/wiki
cp docs/wiki/*.md /tmp/wiki/ && cd /tmp/wiki && git add -A && git commit -m "Sync from docs/wiki" && git push
```

## Contributing

Issues are disabled on the repository. A pull request against `develop` with a passing
`make check` is welcome; a security problem goes through the private channel in
[SECURITY.md](https://github.com/EduOnieva/pdftunnel/blob/main/SECURITY.md).
