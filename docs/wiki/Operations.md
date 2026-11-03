# Operations

## Replacing a file

Copy the new version over the old one, or copy it under a new name and change the route's
`file:`. Either way the next request serves the new file: the size and modification time
make a new ETag, and Cloudflare's cached copy expires after `cache.max_age` seconds (purge the
URL in the dashboard for an immediate change). Do not keep the old version in `config/files`
under a name you also route; an unrouted old version is harmless, nobody can reach it.

A file copied as root may not be readable by the container's user; the route is a 404 until
`chmod a+r`. `check-config` and `/api/status` show which routes point at a missing or
unreadable file.

## Logs

One line per request at `INFO`: the visitor's address as Cloudflare saw it
(`CF-Connecting-IP`), method, path, status, bytes sent, duration. Health checks are logged at
`DEBUG` only. cloudflared's lines are relayed with their level under the `cloudflared` logger;
the two that matter are `Registered tunnel connection` (one per connector) and the error that
precedes an exit.

```
10:41:05 INFO    pdftunnel.app: pdftunnel 1.0 serving 2 route(s) on 127.0.0.1:8080, config /config/config.yaml
10:41:05 INFO    cloudflared: Tunnel connecting
10:41:06 INFO    cloudflared: 2026-11-03T09:41:06Z INF Registered tunnel connection connIndex=0 ... location=mad01
10:41:06 INFO    cloudflared: Tunnel connected
10:42:17 INFO    pdftunnel.access: 203.0.113.9 GET / 200 32208295B 412ms
10:42:18 INFO    pdftunnel.access: 203.0.113.9 GET / 206 65536B 3ms
```

`docker logs pdftunnel`; the compose file rotates at three files of 10 MB.

## Counters

Each route counts its opens: a request without a `Range` header. The PDF viewer's partial
fetches, `HEAD` requests and 304 answers are not counted. The counts live in memory and are
written to `config/state/counters.json` once a minute and at shutdown; `/api/status` reports
them. To reset, stop the container and delete the file.

## The tunnel

cloudflared runs as a child of the application. If it exits (a revoked token, a network
change it did not recover from), the application logs the exit code, waits 1, 2, 5, 10 and
then 30 seconds between attempts, and starts it again; `/healthz` says 503 and `/api/status`
carries `restarts`, `last_exit_code` and `last_error` meanwhile. `docker stop` sends SIGTERM:
the web server stops accepting, cloudflared gets SIGTERM and ten seconds, the counters are
written, and the container exits 0.

## The CLI

```
docker exec pdftunnel pdftunnel check-config            # validate and list the routes
docker exec pdftunnel pdftunnel print-config            # the effective configuration as YAML
docker exec pdftunnel pdftunnel print-example-config    # the commented template
docker exec pdftunnel pdftunnel token [--length N]      # a random path segment for a secret link
docker exec pdftunnel pdftunnel healthcheck             # what Docker's HEALTHCHECK runs
```

`check-config` and `print-config` read the mounted `config.yaml` and the environment, so they
report the same problems the running container would.

## Backing up

`config/` is the whole state: `config.yaml`, `files/`, `state/` and `custom.css`. Copy it
anywhere; a new container with the same folder and token continues where the old one was,
counters included.
