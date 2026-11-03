# pdftunnel

Publish PDFs and other files from a folder through a Cloudflare Tunnel.
Source, releases and changelog: https://github.com/EduOnieva/pdftunnel.
The [wiki](https://github.com/EduOnieva/pdftunnel/wiki) has the longer guides: the Cloudflare
side step by step, every configuration key, troubleshooting, the API.

One container, one volume. Drop a file under `config/files/`, give it a URL in
`config/config.yaml`, and it is on your hostname: `https://docs.example.com/` opens the
catalogue in the browser, with its download button. Your server publishes nothing on the LAN
or the internet; cloudflared, inside the container, connects out to Cloudflare, and Cloudflare
serves the visitors, with its cache and HTTPS in front.

- **Files are routes, not a folder listing.** Only what `config.yaml` names is reachable. The
  old version you left next to the published one, the draft, the dotfile: all 404.
- **Edit and done.** The configuration is re-read while the container runs. Replace the file,
  change the route, no restart.
- **The right headers.** PDFs open inline with the name you choose, accented characters
  included; Range requests for the browser's viewer, ETag and Last-Modified for Cloudflare's
  cache, `Cache-Control` you set.
- **Secret links, folders, an index.** An unguessable path shares a document with whoever has
  the link, no login. A folder route serves everything under it, with an optional file list.
  An optional index page at `/` lists what you publish.
- **Cloudflare Access aware.** A route with `access: true` is served only with a valid
  Access login: the token Cloudflare adds to the request is verified against your team's keys.
- **Honest status.** `/healthz` reflects the tunnel's connection, `/api/status` gives
  dashboards every route with its size, date and how many times it was opened.
- **Safe defaults.** Unprivileged user, read-only container, no capabilities, the token
  handed to cloudflared through its environment and never on a command line, the web server
  bound to the loopback so only the tunnel reaches it, no pip in the image.

## Quick start

1. **Create the tunnel.** In [Zero Trust](https://one.dash.cloudflare.com/), *Networks* >
   *Tunnels* > *Create a tunnel*, type *Cloudflared*, give it a name. Copy the token from the
   install command (the long string after `--token`). Then add a *Public hostname*: the
   subdomain you want, and as service **HTTP** `localhost:8080`.

2. **Create the folder and the compose file.**

   ```bash
   mkdir -p pdftunnel/config/files && cd pdftunnel
   printf 'TUNNEL_TOKEN=%s\n' 'eyJ...' > .env
   ```

   ```yaml
   services:
     pdftunnel:
       image: eduonieva/pdftunnel:latest
       container_name: pdftunnel
       restart: unless-stopped
       security_opt:
         - no-new-privileges:true
       cap_drop: [ALL]
       read_only: true
       tmpfs:
         - /tmp
       volumes:
         - ./config:/config
       environment:
         - TUNNEL_TOKEN=${TUNNEL_TOKEN}
         - TZ=Europe/Madrid
   ```

   The container runs as user 1000. Create `config/` as yourself before the first start, or
   add `user: "<your uid>:<your gid>"`; the
   [Installation](https://github.com/EduOnieva/pdftunnel/wiki/Installation) page has the
   details and the secrets-file alternative to `.env`.

3. **Drop the file and route it.** Copy `catalogue.pdf` into `config/files/`, start with
   `docker compose up -d`, and edit the `config/config.yaml` that the first start wrote:

   ```yaml
   routes:
     - path: /
       file: catalogue.pdf
       filename: "Catalogue 2026.pdf"
   ```

4. Open `https://docs.example.com/`. The log (`docker logs pdftunnel`) shows the tunnel
   connecting and every request.

## Routes

```yaml
routes:
  - path: /                              # the URL
    file: catalogue.pdf                  # under config/files
    filename: "Catalogue 2026.pdf"       # the name the browser shows and saves (default: the file's)
    disposition: inline                  # inline (open in the browser) | attachment (download)

  - path: /prices-k7f3q9x2               # a secret link: an unguessable path, no login
    file: prices.pdf
    listed: false                        # kept off the index page

  - path: /docs/                         # a folder: config/files/docs/* at /docs/<name>
    dir: docs
    listing: true                        # a file list at /docs/ (default: false)
    title: Documents                     # label on the index page

  - path: /internal/                     # only through a Cloudflare Access login
    dir: internal
    access: true
```

- A file route answers one exact path. A folder route answers every regular file under its
  folder, including sub-folders; dotfiles are never served, and a symlink is followed only
  while it stays inside `config/files`.
- `pdftunnel token` prints a random string for a secret link. Twelve lowercase characters
  and digits is 4.7 quintillion possibilities; nobody guesses it, but anyone the link is
  forwarded to can open it, which is the point.
- `/healthz`, `/api/...` and `/_pdftunnel/...` belong to the application and cannot be routes.
- A missing file is a 404 until it appears; the status API and `check-config` say which routes
  point nowhere.

## Configuration

Settings come from two places: the environment for the process and the token, `config.yaml`
for everything the visitors see. `config.yaml` is re-read within two seconds of a change. A
broken edit is logged and ignored, the previous configuration stays in use and the status API
carries the error; at startup a broken file is a refusal. Every key is described in the wiki's
[Configuration](https://github.com/EduOnieva/pdftunnel/wiki/Configuration) page.

### Environment variables

| Variable | Default | Detail |
|---|---|---|
| `TUNNEL_TOKEN` | required | The tunnel's token from Zero Trust |
| `API_TOKEN` | | Bearer token that enables `/api/status` |
| `TZ` | `Etc/UTC` | Timestamps in the log |
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `WEB_BIND` | `127.0.0.1` | The interface the server listens on. `0.0.0.0` only to map the port for local testing: it bypasses Cloudflare and Access |
| `WEB_PORT` | `8080` | The port cloudflared's public hostname points at (`localhost:8080`) |
| `RELOAD_SECONDS` | `2` | How often `config.yaml` is checked |
| `FILE__<VAR>` | | Read `<VAR>` from a file instead, e.g. `FILE__TUNNEL_TOKEN=/run/secrets/tunnel_token` |

A value in `environment:` is readable by anyone who can run `docker inspect`. The `FILE__`
form with a file mounted read-only, or declared under Compose's `secrets:`, keeps the token out
of it.

### config.yaml

```yaml
routes: []          # see above
site:
  title: pdftunnel  # the index page's title
  index: false      # true: a page at / listing the routes marked `listed`, unless / is a route
cache:
  max_age: 300      # seconds browsers and Cloudflare may cache a file. 0 disables caching
access:             # only for routes with access: true
  team_domain: myteam.cloudflareaccess.com
  audience: "<the Access application's AUD tag>"
```

A file behind Access is always sent with `Cache-Control: private, no-store`, whatever
`max_age` says, so a shared cache never hands it to the next visitor.

## Cloudflare

- **The tunnel** is the only way in. The public hostname's service is `http://localhost:8080`;
  cloudflared and the server share the container's loopback. No port is published, and the
  compose file has none.
- **The cache.** Cloudflare caches PDFs by default and honours `Cache-Control`. After replacing
  a file, visitors see the new one within `max_age` seconds; to be immediate, purge the URL in
  the dashboard (*Caching* > *Configuration* > *Purge by URL*).
- **Access.** For a document that must sit behind a login, create an Access application for
  the hostname (or a path on it) in Zero Trust, copy its *Application Audience (AUD) Tag* into
  `access.audience`, your team domain into `access.team_domain`, and mark the routes
  `access: true`. Cloudflare enforces the login; pdftunnel verifies the token it adds to each
  request, so the file is not served if the policy is missing or the container is reached
  another way.
- The wiki's [Cloudflare](https://github.com/EduOnieva/pdftunnel/wiki/Cloudflare) page walks
  through each screen.

## Endpoints

| Endpoint | What it does |
|---|---|
| `GET /healthz` | 200 while the tunnel is connected, 503 with the state otherwise (Docker's HEALTHCHECK) |
| `GET /api/status` | Version, cloudflared version, tunnel state and connections, every route with size, date, existence and open count; needs `Authorization: Bearer <API_TOKEN>` or a Cloudflare Access login |
| `GET /` | The index page when `site.index` is on and `/` is not a route |
| `GET /_pdftunnel/app.css` | The pages' stylesheet; `custom.css` in the config folder is loaded after it |

A route is "opened" once per request without a `Range` header; a browser's PDF viewer then
fetches pieces, which are not counted again. Counts persist in `config/state/counters.json`.
The wiki's [API](https://github.com/EduOnieva/pdftunnel/wiki/API) page has examples for
Homepage and Home Assistant.

## Operations

- **Logs.** The application logs to stdout: one line per request with the visitor's address as
  Cloudflare saw it, cloudflared's own lines, and the configuration reloads. `docker logs
  pdftunnel`; the compose file rotates them.
- **State.** Everything is under `config/`: `config.yaml`, `files/`, `state/counters.json`
  and the optional `custom.css`. Back that folder up and the container is disposable.
- **Updating.** `docker compose pull && docker compose up -d`. Image tags follow the
  branches: `latest` is `main`, which moves at releases; `1.0` pins a release and `1` its
  newest; `develop` is the `develop` branch. On Docker Hub (`eduonieva/pdftunnel`) and GHCR
  (`ghcr.io/eduonieva/pdftunnel`), for amd64 and arm64. The release tags are rebuilt every
  Monday from the same code, so fixes in the Python base image and Alpine packages arrive with
  a `pull`, and so does cloudflared: each build bundles the newest release that has been out
  for at least 7 days, a grace period so that a release pulled or found compromised in its
  first days never reaches an image, short enough that cloudflared's own fixes are not held
  back for long. To
  rebuild on a day other than Monday, run the *Release* workflow by hand in the repository's
  *Actions* tab, then `pull`. The startup log and `/api/status` say which cloudflared version
  is running.
- **CLI.** `docker exec pdftunnel pdftunnel check-config | print-config |
  print-example-config | token [--length N] | healthcheck`.
- **Something wrong.** The wiki's
  [Troubleshooting](https://github.com/EduOnieva/pdftunnel/wiki/Troubleshooting) page goes
  message by message.

## Security

The container runs as an unprivileged user, read-only, with every capability dropped and
`no-new-privileges`. The web server binds to the loopback, so the only way in is the tunnel.
Every served path is resolved and checked to stay under `config/files`; dotfiles and
unrouted files are invisible. Responses carry `X-Content-Type-Options: nosniff` and a
referrer policy; the HTML pages carry a strict Content-Security-Policy and refuse framing. The
status API is off unless a token enables it, since it names your files. Security reports go
through [`SECURITY.md`](https://github.com/EduOnieva/pdftunnel/blob/main/SECURITY.md).

What it does not do: there is no login of its own. Public documents are public; a secret link
is as private as the people who have it; anything that must require a login goes behind
Cloudflare Access.

## Development

```bash
make install   # uv sync
make check     # lock check, ruff, mypy --strict, tests (coverage gate 85 %)
make build     # docker build -t pdftunnel:dev .
make smoke     # the image with a bogus token: files, headers, 404s, endpoints, a clean stop
```

Work happens on the `develop` branch, which publishes the `develop` image on every push; a
release merges into `main` and tags `vX.Y`. The code layout, the tests, CI and the release
steps are in the wiki's [Development](https://github.com/EduOnieva/pdftunnel/wiki/Development)
page.

## AI assistance

pdftunnel was written with an AI coding assistant (Claude Code). I decided what it does, what
it refuses to do and what is safe, from the route model to the single way in; the assistant
wrote the code, the tests and the documentation to that design, and I read every change
before it lands. Nothing is merged on the assistant's word: the test suite, the image smoke
test and the vulnerability scan run on every push, and the deployment this repository serves
is my own.

## License

[MIT](https://github.com/EduOnieva/pdftunnel/blob/main/LICENSE)
