# Configuration

Two sources: environment variables for the process and the token, `config.yaml` for what
visitors see. The file is re-read within `RELOAD_SECONDS` of a change; a broken edit keeps the
previous configuration in use and is reported once in the log (`config.yaml not reloaded,
keeping the previous one: ...`) and in `/api/status` under `config.error`, until the next
valid save. At startup a broken file is a refusal with exit code 2 and the problems listed
one per line, each with its location: `routes[1].path: must start with /`.

`pdftunnel check-config` validates and lists the routes; `pdftunnel print-config` shows the
effective configuration; `pdftunnel print-example-config` prints the commented template the
first start writes.

## Environment variables

| Variable | Default | Detail |
|---|---|---|
| `TUNNEL_TOKEN` | required | The tunnel's token. Blank counts as unset |
| `API_TOKEN` | | Enables `/api/status`; the caller sends `Authorization: Bearer <token>`. Without it the endpoint is only reachable with a Cloudflare Access login, and 404 when Access is not configured either |
| `TZ` | `Etc/UTC` | IANA name; timestamps in the log |
| `LOG_LEVEL` | `INFO` | `DEBUG` adds who opened an Access route and the health checks to the log |
| `WEB_BIND` | `127.0.0.1` | The interface uvicorn listens on. Only cloudflared needs to reach it; `0.0.0.0` is for mapping the port while testing |
| `WEB_PORT` | `8080` | Must match the public hostname's service URL |
| `RELOAD_SECONDS` | `2` | Polling interval for `config.yaml` |
| `CONFIG_DIR` | `/config` | Where the volume is mounted. Change the volume, not this |
| `CLOUDFLARED_BIN` | `/usr/local/bin/cloudflared` | For the test suite |
| `FILE__<VAR>` | | Read `<VAR>` from the named file, trailing newline stripped. Wins over a plain `<VAR>` |

## config.yaml

```yaml
routes:
  - path: /
    file: catalogue.pdf
    filename: "Catalogue 2026.pdf"
    disposition: inline
    listed: true
    access: false
    title: Catalogue
  - path: /docs/
    dir: docs
    listing: false
site:
  title: pdftunnel
  index: false
cache:
  max_age: 300
access:
  team_domain:
  audience:
```

### routes

A list; order does not matter, except that a longer folder path wins over a shorter one
(`/docs/manuals/` over `/docs/`), and a file route always wins over a folder route at the
same URL.

| Key | Required | Detail |
|---|---|---|
| `path` | yes | The URL path. Starts with `/`; no `..`, `.`, empty segments, `?` or `#`. A folder route gets a trailing slash added; a file route loses one. `/healthz`, `/api`, `/_pdftunnel` and anything under them are reserved |
| `file` | one of the two | A file under `config/files`, relative, no `..`, no dotfile in the path |
| `dir` | one of the two | A folder under `config/files`, same rules. Every regular file under it is served at `path` + its relative path |
| `filename` | | The name in `Content-Disposition`, shown by the viewer and used when saving. Any characters but `/`, `\`, `"` and control characters. Default: the file's own name. Ignored for folder routes |
| `disposition` | | `inline` (default): the browser opens it, PDFs in the viewer with a download button. `attachment`: the browser saves it |
| `listing` | | Folder routes only. `true`: a request for the folder's own path answers an HTML list of its files (not sub-folders). Default `false`: 404 |
| `listed` | | `true` (default): shown on the index page. `false`: left off it, the usual choice for a secret link |
| `access` | | `true`: served only with a valid Cloudflare Access token, and sent with `Cache-Control: private, no-store`. Needs the `access:` section |
| `title` | | The label on the index page. Default: `filename`, then the file's name, then the path |

Two routes may serve the same file. The same path twice is an error.

### site

| Key | Default | Detail |
|---|---|---|
| `title` | `pdftunnel` | The index page's title |
| `index` | `false` | `true`: `GET /` answers a page listing the `listed` routes, with size and date for files. If `/` is itself a route, the route wins and there is no index |

The pages load `/_pdftunnel/app.css` and, if `config/custom.css` exists, that file after it.
Colours are CSS variables (`--bg`, `--fg`, `--muted`, `--card`, `--line`, `--accent`), with a
dark variant under `prefers-color-scheme: dark`.

### cache

| Key | Default | Detail |
|---|---|---|
| `max_age` | `300` | Seconds in `Cache-Control: public, max-age=N` for files. `0` sends `no-cache`: every request is revalidated with a conditional request, answered 304 when the file has not changed |

### access

| Key | Detail |
|---|---|
| `team_domain` | `myteam.cloudflareaccess.com`, or just `myteam`. The token's issuer must be `https://<team_domain>` and the keys are fetched from it |
| `audience` | The Access application's AUD tag, 64 hex characters |

Both are required as soon as any route has `access: true`; otherwise the section may be left
empty.
