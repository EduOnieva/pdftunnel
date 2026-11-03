# API

One endpoint for dashboards, and a health check for Docker. Both are reachable through the
tunnel like any route, so the status endpoint is authenticated.

## GET /healthz

`200 ok` while the tunnel has at least one registered connection; `503 tunnel <state>`
otherwise, where the state is `starting`, `connecting`, `down` (cloudflared exited and a
restart is scheduled) or `stopped`. Docker's `HEALTHCHECK` calls it every 30 seconds.

## GET /api/status

Needs `Authorization: Bearer <API_TOKEN>`, or a valid Cloudflare Access login when the
`access:` section is configured and the Access application covers `/api`. `404` when neither
is configured, `401` when the credential is missing or wrong.

```bash
curl -H "Authorization: Bearer $API_TOKEN" https://docs.example.com/api/status
```

```json
{
  "version": "1.0",
  "tunnel": {
    "state": "connected",
    "connections": 2,
    "restarts": 0,
    "last_exit_code": null,
    "last_error": null,
    "connected_since": "2026-11-03T09:41:06+00:00"
  },
  "config": {
    "routes": 2,
    "index": true,
    "access_configured": false,
    "error": null
  },
  "routes": [
    {
      "path": "/",
      "kind": "file",
      "target": "catalogue.pdf",
      "listed": true,
      "access": false,
      "requests": 1284,
      "exists": true,
      "size": 32208295,
      "modified": "2026-04-20T16:12:46+00:00"
    },
    {
      "path": "/docs/",
      "kind": "dir",
      "target": "docs",
      "listed": true,
      "access": false,
      "requests": 57,
      "exists": true,
      "files": 3
    }
  ]
}
```

- `tunnel.restarts` counts cloudflared restarts since the container started;
  `last_exit_code` and `last_error` describe the latest exit.
- `config.error` is the problem with the latest edit of `config.yaml` while the previous
  configuration is in use, `null` when the file is fine.
- `routes[].requests` is the number of opens, persisted across restarts. `exists` is `false`
  when the file or folder is missing; `size` and `modified` are then absent. `files` counts the
  files a listing would show.

Answers carry `Cache-Control: no-store`.

## Widgets

**Homepage** (`services.yaml`), the Custom API widget:

```yaml
- Catalogue:
    icon: mdi-file-pdf-box
    href: https://docs.example.com/
    widget:
      type: customapi
      url: https://docs.example.com/api/status
      headers:
        Authorization: Bearer {{HOMEPAGE_VAR_PDFTUNNEL_TOKEN}}
      mappings:
        - field: tunnel.state
          label: Tunnel
        - field:
            routes:
              0: requests
          label: Opens
          format: number
```

**Home Assistant** (`configuration.yaml`), a REST sensor:

```yaml
rest:
  - resource: https://docs.example.com/api/status
    headers:
      Authorization: !secret pdftunnel_bearer
    scan_interval: 300
    sensor:
      - name: Catalogue opens
        value_template: "{{ value_json.routes[0].requests }}"
      - name: Catalogue tunnel
        value_template: "{{ value_json.tunnel.state }}"
```
