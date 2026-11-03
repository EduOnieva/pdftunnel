# Installation

## The compose file

[`docker-compose.yaml`](https://github.com/EduOnieva/pdftunnel/blob/main/docker-compose.yaml)
in the repository is the reference. It publishes no port, runs the container read-only as an
unprivileged user with every capability dropped, mounts `./config` and reads the token from
`.env`.

```bash
mkdir -p pdftunnel/config/files && cd pdftunnel
curl -fsSLO https://raw.githubusercontent.com/EduOnieva/pdftunnel/main/docker-compose.yaml
printf 'TUNNEL_TOKEN=%s\n' 'eyJ...' > .env
docker compose up -d
```

The first start writes a commented `config/config.yaml`; the container is running but
answers 404 to everything until a route is added. Edits are picked up within two seconds.

## The folder and its owner

The image runs as uid 1000, gid 1000. The container needs to read `config/config.yaml` and
`config/files/`, and to write `config/state/` for the request counters (and `config.yaml`
itself, once, on the first start). Three ways to make that true:

- Create `config/` as a user whose uid is 1000, which is the first user on most Linux
  installs. Then nothing else is needed.
- Add `user: "<uid>:<gid>"` to the service with the ids of the user who owns the folder
  (`id -u`, `id -g`). Any ids work; the image has no files the user must own.
- Let Docker create the folder (root-owned) and `chown -R 1000:1000 config`.

A `config/` the container cannot write still serves files: the log says the counters are kept
in memory only, and the example `config.yaml` is not written, so write it yourself
(`docker run --rm eduonieva/pdftunnel print-example-config > config/config.yaml`).

Files dropped later must be readable by that user as well. A file copied as root with mode
600 is a 404 until `chmod a+r`.

## The token

`TUNNEL_TOKEN` in `environment:` is the simple way, and `.env` keeps it out of the compose
file. It is still visible to anyone who can run `docker inspect`. To keep it in a file:

```yaml
services:
  pdftunnel:
    environment:
      - FILE__TUNNEL_TOKEN=/run/secrets/tunnel_token
    secrets:
      - tunnel_token
secrets:
  tunnel_token:
    file: ./tunnel_token
```

Inside the container the token reaches cloudflared through its own environment variable,
never as a command-line argument, so `ps` on the host does not show it.

## The hardening, and what it costs

| Setting | Why | What it prevents you from doing |
|---|---|---|
| `read_only: true` | nothing in the image needs writing; `/config` is a volume and `/tmp` a tmpfs | nothing |
| `cap_drop: [ALL]` | an unprivileged user with no capabilities | nothing; the server binds a high port |
| `no-new-privileges` | no setuid binary is needed | nothing |
| no `ports:` | only cloudflared, inside the container, reaches the server | reaching the server from the LAN; see below |
| user 1000 | a compromise of the server is not root in the container | mounting files the user cannot read |

## Local testing without a tunnel

The server listens on `127.0.0.1` inside the container, so mapping a port does nothing until
`WEB_BIND=0.0.0.0` is also set:

```bash
docker run --rm -v "$PWD/config:/config" -e TUNNEL_TOKEN=bogus -e WEB_BIND=0.0.0.0 \
  -p 127.0.0.1:8080:8080 eduonieva/pdftunnel
```

A bogus token makes cloudflared exit and restart every few seconds; the files are served
regardless, `/healthz` says 503. Do not leave `WEB_BIND=0.0.0.0` with a published port in
production: a request that arrives that way did not pass through Cloudflare, so a route's
Access policy is not applied (pdftunnel still refuses `access: true` routes without a valid
token, which is why it verifies the token itself).

## Image tags and updating

| Tag | Tracks |
|---|---|
| `latest` | the `main` branch, which moves at releases |
| `1.0`, `1` | a release, and the newest release of that major |
| `develop` | the `develop` branch, where changes land first |

`docker compose pull && docker compose up -d` updates. The release tags are rebuilt every
Monday from the same code, so fixes in the Python base image and the Alpine packages arrive
without a new version, and so does cloudflared: every build copies, from Cloudflare's own
image, the newest release that has been on Docker Hub for at least 14 days. That grace
period is deliberate: a release that turns out to be broken or compromised is usually pulled
within days, and a tag that is quietly replaced gets a new date on Docker Hub and waits
again. Cloudflare publishes cloudflared about monthly, so an image is at most a few weeks
behind. To rebuild before Monday, open the repository's *Actions* tab, choose *Release*,
*Run workflow* on `main`, wait a few minutes and `pull`. `docker logs pdftunnel | head -1`
and `/api/status` name the cloudflared version in use, and the image label
`io.github.eduonieva.pdftunnel.cloudflared` carries it too. Images are published for amd64
and arm64, on
Docker Hub (`eduonieva/pdftunnel`) and GHCR (`ghcr.io/eduonieva/pdftunnel`), with provenance
and an SBOM.

## Portainer

Paste the compose file as a stack, set `TUNNEL_TOKEN` in the stack's environment variables,
and change `./config` to an absolute path on the host, since relative paths resolve against
Portainer's own data directory. The folder's owner rules above apply.
