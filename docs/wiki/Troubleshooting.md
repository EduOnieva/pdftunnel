# Troubleshooting

Start with `docker logs pdftunnel`. The lines below are the ones people ask about.

## At startup

**`Configuration error: TUNNEL_TOKEN is not set`**
The variable is empty or missing. With `.env`, the file must sit next to the compose file and
the line must be `TUNNEL_TOKEN=eyJ...` with no quotes needed. `docker compose config` shows
what Compose resolved.

**`Configuration error: config.yaml: routes[0].path: must start with /`**
Every problem is listed with its location in the file. Fix and `docker compose up -d` again.
While running, the same mistake is logged as `config.yaml not reloaded, keeping the previous
one` and the previous routes stay up.

**`Cannot start: web server exited with 1`**
The port is in use inside the container's network namespace, which only happens with
`network_mode: host` or a shared namespace. Change `WEB_PORT` and the public hostname's
service URL together.

**`Warning: cannot create /config/files: Permission denied`**, **`Cannot write
/config/state/counters.json`**
The container's user (1000) cannot write the volume. See *The folder and its owner* in
[[Installation]]. Files are still served.

## The tunnel

**`ERR Provided Tunnel token is not valid`** then **`cloudflared exited with code 1;
restarting in 1s`**
The token is wrong or was refreshed in the dashboard. Copy it again from the tunnel's install
command.

**`Tunnel connecting`** for a long time, no `Registered tunnel connection`
cloudflared cannot reach Cloudflare's edge: outbound 7844/udp and 7844/tcp (QUIC, then HTTP/2
as a fallback) and 443/tcp must be allowed. A corporate firewall or a DNS that resolves
nothing inside the container are the usual causes; `docker exec pdftunnel cloudflared
--version` at least proves the binary runs.

**The hostname shows Cloudflare's error 1033 or 502**
1033: the tunnel is not connected; see the lines above. 502 (`Bad gateway`): cloudflared is
connected but cannot reach the service. The public hostname's service must be
`http://localhost:8080` (or `WEB_PORT`), and `WEB_BIND` must not have been changed to
something that excludes the loopback.

**`/healthz` says 503, Docker says unhealthy, but the files work**
The health check follows the tunnel's connection, not the web server. If the files work
through Cloudflare, the connection is there and the state will say `connected` within
seconds; if they work only through a mapped port, the tunnel is down and the lines above
apply.

## The files

**A route answers 404**
In order: the path in the browser is exactly the route's `path` (a folder route needs the
trailing slash, a file route must not have one); the file exists under `config/files` at the
`file:` or `dir:` given; the container's user can read it (`chmod a+r`); it is not a dotfile;
if it is a symlink, the target is inside `config/files`. `docker exec pdftunnel pdftunnel
check-config` lists routes whose file or folder is missing.

**The browser downloads the PDF instead of showing it**
`disposition: attachment` is set, or the file is not a PDF (the type comes from the extension:
a `.PDF` works, a file with no extension is sent as `application/octet-stream`, which browsers
save). Rename it or set `filename:` with the extension.

**The old file keeps showing after a replacement**
Cloudflare's cache, for up to `cache.max_age` seconds (300 by default). Purge the URL in the
dashboard, or set `max_age: 0` for revalidation on every request. A browser's own cache is
cleared with a hard reload.

**The name shows wrongly, or as `Cat%C3%A1logo.pdf`**
Accented names are sent in the RFC 5987 form (`filename*=utf-8''...`), which every current
browser decodes. A tool that shows the encoded form is reading the raw header.

## Access

**A route with `access: true` answers 403 after the Cloudflare login**
The log says why: `invalid Access token: Audience doesn't match` means `access.audience` is
not this application's AUD tag; `Invalid issuer` means `team_domain` is wrong; `no Access
token in the request` means the Access application does not cover this path, so Cloudflare
never added the token. The application's path and the `access: true` routes must cover the
same URLs.

**`/api/status` answers 404**
Neither `API_TOKEN` nor an Access configuration is set, so the endpoint is off. Set the token.
